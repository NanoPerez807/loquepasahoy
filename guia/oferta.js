/* La oferta de la guía: precio de lanzamiento hasta el domingo 29-11-2026 a las 23:59 (hora de Madrid = 22:59 UTC) y,
   después, el precio normal. Lo usan la página de la guía (guia/) y la portada de la web: precios y enlaces, solo aquí.

   En la página:
     [data-precio]        el precio de ahora («25 €»)
     [data-comprar]       botón de compra: texto «Comprar la guía por 25 €» y enlace de Stripe
     [data-que]           «Lanzamiento por Black Friday…» / «Precio de la guía»
     [data-luego]         «El lunes sube a 39 €» / «Impuestos incluidos»
     [data-cuenta]        cuenta atrás en cajas: [data-d] [data-h] [data-m] [data-s] [data-ms]
     [data-cuenta-linea]  cuenta atrás en una línea («2 d 13:39:12.345»)
     [data-solo-oferta]   solo se ve mientras dura el lanzamiento
     [data-sin-oferta]    solo se ve cuando ya ha acabado
   La barra de abajo (.barra-oferta) sale sola; en la página de la guía, solo cuando el botón grande no se ve. */
(() => {
'use strict';
const OFERTA = {
  fin: Date.UTC(2026, 10, 29, 22, 59, 0),
  lanzamiento: { precio: 25, enlace: 'https://buy.stripe.com/00w7sD7mB3GZ0f11lfdnW0b' },   // plink_1UgLOx1p5e7gGFT3H4nMmkj1
  normal: { precio: 39, enlace: 'https://buy.stripe.com/fZubITeP3fpH1j59RLdnW0d' },        // plink_1UgLRv1p5e7gGFT3CNXyfsXt
};
const NB = ' ';
const quieto = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
const $$ = s => document.querySelectorAll(s);
const dos = n => String(n).padStart(2, '0');
const tres = n => String(n).padStart(3, '0');
const euros = n => n + NB + '€';
let estado = null;

function textos(lanz) {
  const p = lanz ? OFERTA.lanzamiento : OFERTA.normal;
  $$('[data-precio]').forEach(e => { e.textContent = euros(p.precio); });
  $$('[data-comprar]').forEach(e => { e.textContent = 'Comprar la guía por ' + euros(p.precio); e.href = p.enlace; });
  $$('[data-comprar-enlace]').forEach(e => { e.href = p.enlace; });
  $$('[data-que]').forEach(e => { e.textContent = lanz ? 'Lanzamiento por Black Friday: solo este fin de semana' : 'Precio de la guía'; });
  $$('[data-luego]').forEach(e => { e.textContent = lanz ? 'El lunes sube a ' + euros(OFERTA.normal.precio) : 'Impuestos incluidos'; });
  $$('[data-solo-oferta]').forEach(e => { e.hidden = !lanz; });
  $$('[data-sin-oferta]').forEach(e => { e.hidden = lanz; });
  document.documentElement.classList.toggle('con-oferta', lanz);
}

function cuenta() {
  const queda = OFERTA.fin - Date.now();
  const lanz = queda > 0;
  if (lanz !== estado) { estado = lanz; textos(lanz); }
  if (!lanz) return false;
  const ms = queda % 1000, s = Math.floor(queda / 1000);
  const d = Math.floor(s / 86400), h = Math.floor(s / 3600) % 24, m = Math.floor(s / 60) % 60, sg = s % 60;
  $$('[data-cuenta]').forEach(c => {
    const pon = (k, v) => { const e = c.querySelector(k); if (e) e.textContent = v; };
    pon('[data-d]', d); pon('[data-h]', dos(h)); pon('[data-m]', dos(m)); pon('[data-s]', dos(sg)); pon('[data-ms]', tres(ms));
  });
  const linea = d + NB + 'd ' + dos(h) + ':' + dos(m) + ':' + dos(sg) + (quieto ? '' : '.' + tres(ms));
  $$('[data-cuenta-linea]').forEach(e => { e.textContent = linea; });
  return true;
}

function bucle() { if (cuenta() && !quieto) requestAnimationFrame(bucle); }
if (quieto) { $$('[data-ms]').forEach(e => { const caja = e.parentElement; if (caja) caja.hidden = true; }); setInterval(cuenta, 1000); }
cuenta();
if (!quieto) requestAnimationFrame(bucle);

/* ---- barra de abajo ---- */
const css = document.createElement('style');
css.textContent = `
.barra-oferta{position:fixed;left:10px;right:10px;bottom:10px;z-index:60;display:flex;align-items:center;gap:12px;max-width:560px;margin:0 auto;
  background:#0b1736;color:#fff;border:3px solid #0b1736;border-radius:16px;padding:9px 9px 9px 15px;box-shadow:0 6px 0 rgba(3,10,30,.35),0 12px 30px rgba(3,10,30,.35);
  font-family:'Montserrat','Avenir Next','Segoe UI',system-ui,sans-serif;transform:translateY(0);transition:transform .25s ease,opacity .25s ease}
.barra-oferta.fuera{transform:translateY(140%);opacity:0;pointer-events:none}
.barra-oferta[hidden]{display:none!important}
.barra-oferta .bo-t{flex:1;min-width:0;line-height:1.15}
.barra-oferta .bo-t > b{display:block;font-weight:900;font-size:16px;white-space:nowrap}
.barra-oferta .bo-t > span{display:block;margin-top:2px;font-weight:700;font-size:13.5px;color:#ffd43b;font-variant-numeric:tabular-nums;white-space:nowrap}
.barra-oferta i{font-style:normal}
.barra-oferta a{flex:none;display:inline-flex;align-items:center;justify-content:center;min-height:46px;padding:0 16px;border:3px solid #fff;border-radius:12px;
  background:#ffd43b;color:#0b1736;font-weight:800;font-size:15px;text-decoration:none;white-space:nowrap}
.con-oferta body{padding-bottom:84px}
@media (prefers-reduced-motion:reduce){.barra-oferta{transition:none}}`;
document.head.appendChild(css);

const enGuia = !!document.querySelector('[data-pagina-guia]');
const barra = document.createElement('div');
barra.className = 'barra-oferta';
barra.setAttribute('data-solo-oferta', '');
barra.setAttribute('role', 'region');
barra.setAttribute('aria-label', 'Oferta de la guía');
barra.innerHTML = '<div class="bo-t"><b>La guía a <i data-precio></i></b><span>Acaba en <i data-cuenta-linea></i></span></div>' +
  (enGuia ? '<a data-comprar-enlace href="#">Comprar</a>' : '<a href="guia/">Ver la guía</a>');
document.body.appendChild(barra);
estado = null; cuenta();

/* que no tape lo importante: en la página de la guía sale cuando ya has pasado el botón grande (y se esconde mientras
   se ve el de abajo); en la portada, siempre, salvo mientras se ve la sección de la guía */
const tapar = [...document.querySelectorAll(enGuia ? '.precio [data-comprar]' : '#guia')];
if ('IntersectionObserver' in window && tapar.length) {
  const vistos = new Set();
  const actualiza = () => {
    const pasado = !enGuia || tapar[0].getBoundingClientRect().bottom < 0;
    barra.classList.toggle('fuera', vistos.size > 0 || !pasado);
  };
  const io = new IntersectionObserver(es => {
    es.forEach(e => { if (e.isIntersecting) vistos.add(e.target); else vistos.delete(e.target); });
    actualiza();
  }, { threshold: 0.2 });
  tapar.forEach(t => io.observe(t));
  if (enGuia) addEventListener('scroll', actualiza, { passive: true });
  actualiza();
}
/* ---- casilla obligatoria: en la página de la guía, ningún botón de compra (tampoco el de la barra) lleva a Stripe
   si no se ha marcado «He leído… y acepto las condiciones…»; si no está marcada, te lleva a la casilla y la sacude ---- */
document.documentElement.classList.add('js');
if (enGuia) {
  const cajas = [...document.querySelectorAll('[data-acepto]')];
  const pon = v => {
    cajas.forEach(c => { c.checked = v; const l = c.closest('.acepto'); if (l && v) l.classList.remove('avisa'); });
    document.documentElement.classList.toggle('aceptado', v);
  };
  cajas.forEach(c => c.addEventListener('change', () => pon(c.checked)));
  pon(cajas.some(c => c.checked));
  document.addEventListener('click', e => {
    const a = e.target.closest('[data-comprar],[data-comprar-enlace]');
    if (!a || !cajas.length || document.documentElement.classList.contains('aceptado')) return;
    e.preventDefault();
    const c = (a.closest('.precio') && a.closest('.precio').querySelector('[data-acepto]')) || cajas[0];
    const l = c.closest('.acepto');
    l.scrollIntoView({ behavior: quieto ? 'auto' : 'smooth', block: 'center' });
    l.classList.remove('avisa'); void l.offsetWidth; l.classList.add('avisa');
    setTimeout(() => c.focus({ preventScroll: true }), 400);
  }, true);
  const abre = () => {
    const d = document.querySelector('[data-condiciones]'); if (!d) return;
    d.open = true;
    requestAnimationFrame(() => { const sec = document.getElementById('condiciones'); if (sec) sec.scrollIntoView({ behavior: quieto ? 'auto' : 'smooth', block: 'start' }); });
  };
  document.querySelectorAll('a[href="#condiciones"]').forEach(a => a.addEventListener('click', abre));
  if (location.hash === '#condiciones') abre();
  addEventListener('hashchange', () => { if (location.hash === '#condiciones') abre(); });
}
})();
