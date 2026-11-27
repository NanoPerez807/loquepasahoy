#!/usr/bin/env python3
"""Robot de cobros de loquepasahoy.es: apunta en la web los pagos de Stripe (tuneos, pueblos de oro y vecinos de honor).

Lo usa el robot de GitHub (.github/workflows/cobros.yml) cada 10 minutos y también se puede usar a mano. Escribe dos archivos:
  data/cobros-libro.json   el libro: un apunte por pago, con la huella del pago (no el pago: un resumen sha256) y lo que se compró.
  data/cobros.json         lo que lee la web: apoyos, vecinos y tuneos sumados (se rehace entero desde el libro cada vez).
NUNCA guarda ni enseña datos de quien paga (nombre, correo, dirección): solo el código del pueblo, la cosa y la cantidad.
Los nombres de los vecinos de honor no se publican solos: su apoyo de oro cuenta al momento, y el nombre espera a que alguien lo revise.
Una compra puede llevar varias cosas para el mismo pueblo (en la página de pago se cambia la cantidad y se añaden cosas: así se paga una
sola comisión): el robot lee cada línea de la compra por su precio de Stripe (PRECIO_ID) y apunta una cosa por línea.

uso (desde la raíz del repo de la web):
  python3 .github/cobros.py --stripe              lee de Stripe los pagos nuevos (necesita la variable STRIPE_KEY, una clave restringida
                                                  de solo lectura de «Checkout Sessions») y los apunta
  python3 .github/cobros.py --json sesiones.json  lo mismo, con las sesiones de Checkout guardadas en un archivo (lista, o {"data": [...]})
  python3 .github/cobros.py --resumen             cómo va todo
  python3 .github/cobros.py --pendientes          vecinos de honor a la espera de nombre
  python3 .github/cobros.py --nombre HUELLA "Marta G."    pone el nombre (revisado) de un vecino de honor
  python3 .github/cobros.py --sin-nombre HUELLA   vecino de honor cuyo nombre no se publica (su apoyo de oro sigue contando)
  python3 .github/cobros.py --devuelto ID_O_HUELLA     pago devuelto: deja de contar
  python3 .github/cobros.py --ya ID [ID…]         pagos apuntados por otro camino (a mano): el robot no los vuelve a contar
"""
import hashlib, json, os, re, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

RAIZ = os.environ.get('COBROS_RAIZ') or os.getcwd()
F_LIBRO = os.path.join(RAIZ, 'data', 'cobros-libro.json')
F_WEB = os.path.join(RAIZ, 'data', 'cobros.json')
F_PUEBLOS = os.path.join(RAIZ, 'data', 'pueblos.json')
PRECIO = {'TUN': 100, 'ORO': 300, 'VEC': 1000, 'PRI': 500, 'PKT': 400, 'PKO': 800, 'PNV': 300, 'FLO': 100, 'NEG': 5000}   # céntimos, IVA incluido (PKT: pack de 5 tuneos · PKO: pack de 3 oros · PRI: primer plano · PNV: pack Navidad · FLO: flores · NEG: apoyo de negocio)
PRIMER = {'inicio': '2026-11-27', 'fin': '2026-12-31', 'cupo': 10, 'cierre_h': 14}   # primer plano: 10 por episodio; lo pagado antes de las 14:00 (Madrid) va al de ese día
COSAS = ['gorro', 'luces', 'gafas', 'bigote', 'vaca', 'corona', 'boina', 'ciguena', 'paraguas', 'flotador', 'limon', 'nieve', 'arbol', 'estrella']   # el orden de la tienda
NAVIDAD = ['luces', 'nieve', 'arbol', 'estrella']   # lo que lleva el pack Navidad (un voto de cada por pack)
PRECIO_ID = {   # precio de Stripe → tipo (los precios se ven en la página de pago: no son secretos)
    'price_1UfpeN1p5e7gGFT3skohqbja': 'TUN', 'price_1Ufimc1p5e7gGFT3U79as1fQ': 'ORO', 'price_1Ufimg1p5e7gGFT3iGIFB8H7': 'VEC',
    'price_1UgB5f1p5e7gGFT3OTb4r2OM': 'PRI', 'price_1UgB5j1p5e7gGFT3y0CET0Lr': 'PKT', 'price_1UgB5l1p5e7gGFT39g5i9Psq': 'PKO',
    'price_1UgCSz1p5e7gGFT3gTogCtth': 'PNV', 'price_1UgCT11p5e7gGFT3fqAtnh06': 'FLO', 'price_1UgE7m1p5e7gGFT3x2uRNCpX': 'NEG'}
GUIA = 'guia'   # las compras de la guía (su enlace de pago lleva metadata tipo «guia») no son del juego: no se apuntan
VENTANA = 7 * 86400                                       # se miran los pagos de los últimos 7 días (una sesión de pago caduca a las 24 h)


class Mal(Exception):
    pass


def todos_los_pueblos(D):
    """código → nombre de TODOS los pueblos que juegan: los municipios (data/pueblos.json, 5 cifras) y las aldeas, pedanías,
    parroquias y núcleos (data/aldeas.json, 11 cifras = municipio + 6 cifras de su unidad poblacional; ver web-src/aldeas.py)."""
    M = json.load(open(os.path.join(D, 'pueblos.json'), encoding='utf-8'))
    P = {p[0]: p[1] for p in M}
    fa = os.path.join(D, 'aldeas.json')
    if os.path.exists(fa):
        A = json.load(open(fa, encoding='utf-8')); nom = A['nom'].split('|'); i = 0
        for k, n in enumerate(A['mun']):
            suf = 0
            for r in range(n):
                suf = suf + A['cod'][i] if r else A['cod'][i]
                P[M[k][0] + str(suf).zfill(6)] = nom[i] + ' (' + M[k][1] + ')'; i += 1
    return P


def huella(id_pago):
    return hashlib.sha256(id_pago.encode()).hexdigest()[:24]


def norm(s):
    return re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn').lower()).strip()


def limpia_nombre(s):
    s = re.sub(r'[\x00-\x1f<>{}]', ' ', str(s))
    return re.sub(r'\s+', ' ', s).strip()[:30].strip()


def lee_libro():
    if not os.path.exists(F_LIBRO):
        return {'pagos': []}
    L = json.load(open(F_LIBRO, encoding='utf-8'))
    L.setdefault('pagos', [])
    return L


def escribe(L):
    """Guarda el libro y rehace lo que lee la web. Solo escribe si algo cambia (así el robot no hace commits vacíos)."""
    W = suma(L)
    libro = json.dumps(L, ensure_ascii=False, indent=1) + '\n'
    viejo = open(F_LIBRO, encoding='utf-8').read() if os.path.exists(F_LIBRO) else ''
    web_viejo = json.load(open(F_WEB, encoding='utf-8')) if os.path.exists(F_WEB) else None
    cambia = libro != viejo or not web_viejo or {k: v for k, v in web_viejo.items() if k != 'actualizado'} != W
    if not cambia:
        return False
    W = dict(actualizado=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), **W)
    os.makedirs(os.path.dirname(F_LIBRO), exist_ok=True)
    open(F_LIBRO, 'w', encoding='utf-8').write(libro)
    open(F_WEB, 'w', encoding='utf-8').write(json.dumps(W, ensure_ascii=False, separators=(',', ':')) + '\n')
    return True


def suma(L):
    apoyos, vecinos, tuneos, flores, negocios = {}, {}, {}, {}, []
    for p in L['pagos']:
        if p.get('devuelto') or p['t'] in ('YA', 'RARO'):
            continue
        c, n = p['c'], int(p.get('n', 1))
        if p['t'] == 'TUN':
            d = tuneos.setdefault(c, {})
            d[p['k']] = d.get(p['k'], 0) + n
        elif p['t'] == 'PNV':                       # pack Navidad: un voto para cada cosa de Navidad
            d = tuneos.setdefault(c, {})
            for k in NAVIDAD:
                d[k] = d.get(k, 0) + n
        elif p['t'] == 'FLO':
            flores[c] = flores.get(c, 0) + n
        elif p['t'] == 'ORO':
            apoyos[c] = apoyos.get(c, 0) + n
        elif p['t'] == 'NEG':                       # apoyo de negocio: sus puntos los suma la web desde el libro; el cartel, cuando el nombre esté revisado
            if p.get('nombre'):
                negocios.append({'c': c, 'n': p['nombre'], 'k': n})
        elif p['t'] == 'VEC':                       # con nombre revisado sale como vecino (y la web le suma su apoyo); si no, cuenta como apoyo suelto
            if p.get('nombre'):                     # 3 vecinos de una vez = el nombre 3 veces (la web lo enseña «×3»)
                vecinos.setdefault(c, []).extend([p['nombre']] * n)
            else:
                apoyos[c] = apoyos.get(c, 0) + n
    tuneos = {c: {k: d[k] for k in COSAS if k in d} for c, d in sorted(tuneos.items())}
    return {'apoyos': dict(sorted(apoyos.items())), 'vecinos': dict(sorted(vecinos.items())), 'tuneos': tuneos, 'flores': dict(sorted(flores.items())), 'negocios': negocios, 'primeros': primeros(L)}


def primeros(L):
    """Primer plano: cada pago, por orden de llegada, al primer episodio con hueco (10 por episodio) desde el de su día (si se pagó antes de las 14:00 de Madrid) o el siguiente.
    Si un pago lleva varios, van a episodios seguidos."""
    from datetime import date, timedelta
    ini, fin = date.fromisoformat(PRIMER['inicio']), date.fromisoformat(PRIMER['fin']); usados = {}
    pagos = sorted((p for p in L['pagos'] if p['t'] == 'PRI' and not p.get('devuelto')), key=lambda p: (p['creado'], p['h']))
    for p in pagos:
        loc = datetime.fromtimestamp(p['creado'], timezone.utc) + timedelta(hours=1)          # Madrid en noviembre y diciembre: UTC+1
        d = max(ini, loc.date() + timedelta(days=0 if loc.hour < PRIMER['cierre_h'] else 1))
        for _ in range(int(p.get('n', 1))):
            while d <= fin and len(usados.get(d.isoformat(), [])) >= PRIMER['cupo']:
                d += timedelta(days=1)
            if d > fin:
                break
            usados.setdefault(d.isoformat(), []).append(p['c'])
            d += timedelta(days=1)                  # 3 primeros planos de una vez: tres episodios seguidos, no tres veces en el mismo
    return dict(sorted(usados.items()))


def euros_cent(s):
    if (s.get('currency') or '').lower() == 'eur':
        return int(s.get('amount_total') or 0)
    cc = s.get('currency_conversion') or {}
    return int(cc.get('amount_total') or 0) if (cc.get('source_currency') or '').lower() == 'eur' else 0


def cantidad(s, tipo):
    """Cuántas unidades, por el importe (cuando no se tienen las líneas de la compra)."""
    eur = None
    if (s.get('currency') or '').lower() == 'eur':
        eur = s.get('amount_total')
    else:
        cc = s.get('currency_conversion') or {}
        if (cc.get('source_currency') or '').lower() == 'eur':
            eur = cc.get('amount_total')
    if not eur:
        raise Mal('no sé cuánto se pagó en euros')
    return max(1, round(int(eur) / PRECIO[tipo]))


def lineas_de(s, lineas=None):
    """[(tipo, cantidad)] de cada línea de la compra (tipo None si el precio no está en PRECIO_ID), o None si no se tienen."""
    if lineas is None:
        li = s.get('line_items')
        lineas = li.get('data') if isinstance(li, dict) else None
    if not lineas:
        return None
    sal = []
    for x in lineas:
        pr = x.get('price')
        pid = (pr.get('id') if isinstance(pr, dict) else pr) or ''
        sal.append((PRECIO_ID.get(pid), max(1, int(x.get('quantity') or 1))))
    return sal


def cosa_top(L, c):
    """El tuneo más pedido de un pueblo (para un tuneo añadido en la página de pago sin decir cuál): «lleva lo que más se pida»."""
    d = {}
    for p in (L or {}).get('pagos', []):
        if p.get('t') == 'TUN' and p.get('c') == c and not p.get('devuelto'):
            d[p['k']] = d.get(p['k'], 0) + int(p.get('n', 1))
    return max(COSAS, key=lambda k: (d.get(k, 0), -COSAS.index(k)))


def uno(base, t, c, resto, n):
    """Un apunte del libro: n unidades de la cosa t para el pueblo c."""
    if t == 'PKT':                                   # pack de 5 tuneos: 5 votos por pack
        k = norm(resto).replace(' ', '')
        if k not in COSAS:
            return dict(base, t='RARO', c=c, nota=f'pack de tuneos «{k}» que no está en la tienda: revisar a mano')
        return dict(base, t='TUN', c=c, k=k, n=5 * n, pack='PKT')
    if t == 'PKO':                                   # pack de 3 oros
        return dict(base, t='ORO', c=c, n=3 * n, pack='PKO')
    if t in ('PRI', 'PNV', 'FLO', 'ORO'):            # primer plano · pack Navidad · flores para un pueblo caído · oro
        return dict(base, t=t, c=c, n=n)
    if t == 'NEG':                                   # apoyo de negocio (50 € cada uno): el nombre del cartel espera a que alguien lo revise
        return dict(base, t='NEG', c=c, n=n, revisar=True)
    if t == 'TUN':
        k = norm(resto).replace(' ', '')
        if k not in COSAS:
            return dict(base, t='RARO', c=c, nota=f'tuneo «{k}» que no está en la tienda: revisar a mano')
        return dict(base, t='TUN', c=c, k=k, n=n)
    return dict(base, t='VEC', c=c, n=n, revisar=True)


def apuntes(s, P, lineas=None, L=None):
    """Una sesión de Checkout pagada → sus apuntes del libro (sin datos de quien paga): lo de la referencia y, si en la página
    de pago se añadieron otras cosas, un apunte más por cada una (huella de la compra + «+TIPO»), todo para el mismo pueblo."""
    ref = (s.get('client_reference_id') or '').strip()
    h = huella(s['id'])
    base = {'h': h, 'creado': int(s.get('created') or 0)}
    m = re.match(r'^(TUN|ORO|VEC|PRI|PKT|PKO|PNV|FLO|NEG)-(\d{11}|\d{5})(?:-([A-Za-z0-9_]+))?$', ref)      # 5 cifras: municipio · 11: aldea, pedanía, parroquia…
    if not m or m[2] not in P:
        return [dict(base, t='RARO', nota='referencia sin pueblo: revisar a mano en Stripe')]
    t, c, resto = m[1], m[2], m[3] or ''
    ls, extra = lineas_de(s, lineas), {}
    if ls is None:
        n = cantidad(s, t)
    else:
        n = sum(q for k, q in ls if k in (None, t)) or 1                 # las líneas de lo de la referencia (o de un precio que no conozco)
        for k, q in ls:
            if k and k != t:
                extra[k] = extra.get(k, 0) + q
    cent = euros_cent(s)
    if cent and not extra:
        base['cent'] = cent
    elif extra:
        base['cent'] = n * PRECIO[t]
    sal = [uno(base, t, c, resto, n)]
    for k, q in sorted(extra.items(), key=lambda kv: list(PRECIO).index(kv[0])):
        r = resto if t in ('TUN', 'PKT') else cosa_top(L, c)            # un tuneo añadido: el de la referencia, o lo que más se pida en ese pueblo
        sal.append(uno({'h': h + '+' + k, 'creado': base['creado'], 'cent': q * PRECIO[k], 'anadido': True}, k, c, r, q))
    return sal


def stripe(ruta, clave, **q):
    url = os.environ.get('STRIPE_API', 'https://api.stripe.com/v1/') + ruta + ('?' + urllib.parse.urlencode(q) if q else '')
    pet = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + clave, 'Stripe-Version': '2024-06-20'})
    for intento in range(3):
        try:
            with urllib.request.urlopen(pet, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and intento < 2:
                time.sleep(2 + 3 * intento); continue
            raise Mal(f'Stripe respondió {e.code} en {ruta.split("/")[0]}' + (' (¿la clave restringida tiene permiso de lectura de Checkout Sessions?)' if e.code in (401, 403) else ''))
        except urllib.error.URLError as e:
            if intento < 2:
                time.sleep(3); continue
            raise Mal(f'no se puede hablar con Stripe: {e.reason}')


def sesiones_stripe(clave, desde):
    q, sal = {'status': 'complete', 'limit': 100, 'created[gte]': desde}, []
    while True:
        r = stripe('checkout/sessions', clave, **q)
        sal += r.get('data') or []
        if not r.get('has_more') or not r.get('data'):
            return sal
        q['starting_after'] = r['data'][-1]['id']


def nuevos(sesiones, L, P, clave=None):
    hechas = {p['h'] for p in L['pagos']}
    dichos, n = [], 0
    for s in sorted(sesiones, key=lambda s: s.get('created') or 0):
        if not str(s.get('id', '')).startswith('cs_') or s.get('payment_status') != 'paid' or s.get('status') not in (None, 'complete'):
            continue
        if huella(s['id']) in hechas:
            continue
        if (s.get('metadata') or {}).get('tipo') == GUIA:   # la guía: se vende aparte, no es del juego
            continue
        lineas = None
        if clave:                                    # de cada línea solo se usa el precio y la cantidad
            li = stripe(f'checkout/sessions/{s["id"]}/line_items', clave, limit=20)
            lineas = [{'price': (x.get('price') or {}).get('id'), 'quantity': x.get('quantity')} for x in li.get('data') or []]
        try:
            aa = apuntes(s, P, lineas, L)
        except Mal as e:
            aa = [{'h': huella(s['id']), 'creado': int(s.get('created') or 0), 't': 'RARO', 'nota': str(e)}]
        for a in aa:
            L['pagos'].append(a); hechas.add(a['h']); n += 1
            dichos.append(describe(a, P))
    return n, dichos


def describe(a, P):
    if a.get('anadido'):
        return describe(dict(a, anadido=False), P) + ' · añadido en la página de pago'
    if a['t'] == 'RARO':
        return f'RARO {a["h"][:8]} · {a.get("nota", "")}'
    pueblo = f'{P.get(a["c"], "?")} ({a["c"]})'
    if a['t'] == 'TUN':
        return f'{"PACK DE 5 TUNEOS" if a.get("pack") else "TUNEO"} {a["k"]} x{a["n"]} → {pueblo}'
    if a['t'] == 'ORO':
        return f'{"PACK DE 3 OROS" if a.get("pack") else "ORO"} x{a["n"]} → {pueblo}'
    if a['t'] == 'PRI':
        return f'PRIMER PLANO x{a["n"]} → {pueblo}'
    if a['t'] == 'PNV':
        return f'PACK NAVIDAD x{a["n"]} (luces, nieve, árbol y estrella) → {pueblo}'
    if a['t'] == 'FLO':
        return f'FLORES x{a["n"]} → {pueblo}'
    if a['t'] == 'NEG':
        return f'APOYO DE NEGOCIO x{a["n"]} ({a["n"] * 50} €) → {pueblo} · sus puntos ya cuentan; el cartel, cuando se revise el nombre (huella {corta(a["h"])})'
    return f'VECINO DE HONOR{" x" + str(a["n"]) if int(a.get("n", 1)) > 1 else ""} → {pueblo} · su apoyo de oro ya cuenta; el nombre, cuando se revise (huella {corta(a["h"])})'


def corta(h):
    return h[:12] + h[24:] if '+' in h else h[:12]


def busca(L, clave, vale=None):
    clave = clave.strip()
    h = huella(clave) if clave.startswith('cs_') else clave
    hay = [p for p in L['pagos'] if p['h'] == h]
    if not hay:
        b, _, k = h.partition('+')
        hay = [p for p in L['pagos'] if p['h'].startswith(b) and (p['h'].partition('+')[2] == k if k else True)]
        if len(hay) > 1 and vale:
            hay = [p for p in hay if vale(p)] or hay
        if len(hay) > 1 and not k:
            hay = [p for p in hay if '+' not in p['h']] or hay
    if len(hay) != 1:
        raise Mal(f'{"ningún" if not hay else "más de un"} pago con la huella {h[:12]}…')
    return hay[0]


def resumen(L, P):
    W = suma(L)
    cuenta = {}
    for p in L['pagos']:
        k = p['t'] + (' devuelto' if p.get('devuelto') else '')
        cuenta[k] = cuenta.get(k, 0) + 1
    euros = sum(p.get('cent') or int(p.get('n', 1)) * PRECIO[p['t']] for p in L['pagos'] if p['t'] in PRECIO and not p.get('devuelto')) / 100
    print(f'apuntes: {len(L["pagos"])} · ' + ', '.join(f'{k} {v}' for k, v in sorted(cuenta.items())) + f' · cobrado por el robot: unos {euros:.0f} € (IVA incluido, sin comisiones)')
    T = W['tuneos']
    print(f'tuneos: {sum(sum(d.values()) for d in T.values())} votos en {len(T)} pueblos · oro suelto: {sum(W["apoyos"].values())} en {len(W["apoyos"])} pueblos · vecinos con nombre: {sum(len(v) for v in W["vecinos"].values())}')
    for c, d in sorted(T.items(), key=lambda kv: -sum(kv[1].values()))[:10]:
        print(f'  {P.get(c, "?")} ({c}): ' + ', '.join(f'{k} {n}' for k, n in sorted(d.items(), key=lambda kv: -kv[1])))
    pend = [p for p in L['pagos'] if p['t'] in ('VEC', 'NEG') and p.get('revisar') and not p.get('devuelto')]
    if pend:
        print(f'vecinos de honor a la espera de nombre: {len(pend)} (python3 .github/cobros.py --pendientes)')
    raros = [p for p in L['pagos'] if p['t'] == 'RARO']
    if raros:
        print(f'pagos RAROS (sin pueblo o con algo que no está en la tienda): {len(raros)} → revisarlos a mano en Stripe')


def main(a):
    if not a or a[0] in ('-h', '--help'):
        print(__doc__); return 0
    P = todos_los_pueblos(os.path.dirname(F_PUEBLOS))
    L = lee_libro()
    try:
        if a[0] == '--stripe':
            clave = os.environ.get('STRIPE_KEY', '').strip()
            if not clave:
                print('Falta STRIPE_KEY: no hago nada.'); return 0
            if clave.startswith('sk_'):
                print('ojo: es una clave secreta completa; basta (y es más seguro) una restringida de solo lectura (rk_…).')
            desde = max(int(L.get('desde') or 0), int(time.time()) - VENTANA)
            n, dichos = nuevos(sesiones_stripe(clave, desde), L, P, clave)
        elif a[0] == '--json':
            datos = json.load(open(a[1], encoding='utf-8'))
            n, dichos = nuevos(datos['data'] if isinstance(datos, dict) else datos, L, P)
        elif a[0] == '--resumen':
            resumen(L, P); return 0
        elif a[0] == '--pendientes':
            for p in L['pagos']:
                if p['t'] in ('VEC', 'NEG') and p.get('revisar') and not p.get('devuelto'):
                    print(f'  {p["h"]} · {"NEGOCIO" if p["t"] == "NEG" else "vecino"} · {P.get(p["c"], "?")} ({p["c"]}) · pagado el {datetime.fromtimestamp(p["creado"], timezone.utc):%d-%m %H:%M} UTC')
            return 0
        elif a[0] in ('--nombre', '--sin-nombre'):
            p = busca(L, a[1], lambda p: p['t'] in ('VEC', 'NEG') and (p.get('revisar') or a[0] == '--sin-nombre'))
            if p['t'] not in ('VEC', 'NEG'):
                raise Mal('ese pago no es de un vecino de honor ni de un negocio')
            if a[0] == '--nombre':
                nombre = limpia_nombre(' '.join(a[2:]))
                if len(nombre) < 2:
                    raise Mal('falta el nombre')
                p['nombre'] = nombre
            else:
                p.pop('nombre', None); p['sin_nombre'] = True
            p.pop('revisar', None)
            n, dichos = 1, [f'{"negocio que apoya a" if p["t"] == "NEG" else "vecino de honor de"} {P.get(p["c"], "?")}: ' + (f'«{p["nombre"]}»' if p.get('nombre') else 'sin nombre publicado')]
        elif a[0] == '--devuelto':
            p = busca(L, a[1]); b = p['h'].partition('+')[0]
            grupo = [q for q in L['pagos'] if q['h'].partition('+')[0] == b] if '+' not in a[1] else [p]
            for q in grupo:
                q['devuelto'] = True
            n, dichos = len(grupo), ['devuelto: ' + describe(q, P) for q in grupo]
        elif a[0] == '--ya':
            hechas = {p['h'] for p in L['pagos']}
            nuevos_ya = [x for x in a[1:] if x.startswith('cs_') and huella(x) not in hechas]
            for x in nuevos_ya:
                L['pagos'].append({'h': huella(x), 't': 'YA', 'nota': 'apuntado a mano en juego.json'})
            n, dichos = len(nuevos_ya), [f'{len(nuevos_ya)} pagos marcados como ya apuntados a mano']
        else:
            raise Mal(f'no conozco «{a[0]}» (mira --help)')
    except Mal as e:
        print('MAL:', e); return 1
    for d in dichos:
        print(d)
    if escribe(L):
        print(f'{n} apunte(s) nuevo(s). Guardado en data/cobros-libro.json y data/cobros.json.')
    else:
        print('Nada nuevo.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
