/* ─────────────────────────────────────────────────────────────────────────────
   Nookplay — Compartir (estándar orientado al receptor)
   Formato: {emoji} {título} · {espacio}
            {resultado visual}
            {gancho para quien lo recibe}
            👉 nookplay.app/{espacio}
───────────────────────────────────────────────────────────────────────────── */

function nookSpaceSlug() { return (typeof BAR_SLUG !== 'undefined' && BAR_SLUG) ? BAR_SLUG : ''; }
function nookSpaceName() { return (typeof BAR_NAME !== 'undefined' && BAR_NAME) ? BAR_NAME : 'Nookplay'; }
function nookSpaceUrl() { const s = nookSpaceSlug(); return 'https://nookplay.app' + (s ? '/' + s : ''); }

function nookShareText({ emoji, titulo, resultado, gancho }) {
  const lineas = [`${emoji || '🎲'} ${titulo} · ${nookSpaceName()}`];
  if (resultado) lineas.push(resultado);
  lineas.push(gancho || '¿Te atreves tú?');
  lineas.push(`👉 ${nookSpaceUrl().replace('https://', '')}`);
  return lineas.join('\n');
}

/* Registro del compartido (best-effort: nunca bloquea) */
function nookTrackShare(gameSlug) {
  try {
    let did = '';
    try { did = localStorage.getItem('nook_did') || ''; } catch (e) {}
    const body = JSON.stringify({ bar_slug: nookSpaceSlug(), game_type: gameSlug || '', device_id: did });
    if (navigator.sendBeacon) {
      navigator.sendBeacon('/api/share', new Blob([body], { type: 'application/json' }));
    } else {
      fetch('/api/share', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, keepalive: true }).catch(() => {});
    }
  } catch (e) {}
}

/* Compartir genérico de acierto/fallo — SIN spoilers para quien lo recibe */
function shareGame({ correct, gameTitle, pct, gameSlug, gancho, emoji }) {
  const resultado = (correct ? '✅ Lo conseguí' : '❌ Me ha ganado') + (pct ? ` · solo el ${pct} acertó hoy` : '');
  const txt = nookShareText({ emoji: emoji || '🎲', titulo: gameTitle, resultado, gancho: gancho || '¿Puedes tú?' });
  nookShareWithImage(txt, gameSlug);
}

/* ─── Compartir con imagen del juego (Web Share API Level 2) ───
   iOS Safari solo permite navigator.share() DENTRO del gesto del usuario: un
   await previo (descargar la imagen) consume la activación y el share falla en
   silencio. Por eso la imagen se precarga al abrir la página y el handler
   llama a share() de forma síncrona. Si no hay imagen lista, se comparte
   solo texto; si share() no existe, se copia al portapapeles. */
var _nookImg = { slug: '', file: null };

function nookPrecargarImagen(slug) {
  if (!slug || !window.File || !window.fetch) return;
  if (_nookImg.slug === slug && _nookImg.file) return;
  _nookImg.slug = slug;
  fetch('/static/games/' + slug + '.webp')
    .then(function (r) { return r.ok ? r.blob() : null; })
    .then(function (b) { if (b && _nookImg.slug === slug) _nookImg.file = new File([b], 'nookplay.webp', { type: b.type || 'image/webp' }); })
    .catch(function () {});
}

function nookSlugDePagina() {
  try {
    var p = location.pathname.split('/').filter(Boolean);
    return p.length >= 2 ? p[p.length - 1] : '';
  } catch (e) { return ''; }
}

function nookAvisoCopiado() {
  try {
    var d = document.createElement('div');
    d.textContent = 'Texto copiado. Pégalo donde quieras.';
    d.style.cssText = 'position:fixed;left:50%;bottom:28px;transform:translateX(-50%);background:#1A1A1A;color:#fff;padding:10px 16px;border-radius:999px;font-size:14px;z-index:9999;opacity:0;transition:opacity .2s';
    document.body.appendChild(d);
    requestAnimationFrame(function () { d.style.opacity = '1'; });
    setTimeout(function () { d.style.opacity = '0'; setTimeout(function () { d.remove(); }, 250); }, 2200);
  } catch (e) {}
}

function nookShareWithImage(txt, gameSlug) {
  nookTrackShare(gameSlug);
  var file = (gameSlug && _nookImg.slug === gameSlug) ? _nookImg.file : null;
  var conImagen = !!(file && navigator.canShare && navigator.canShare({ files: [file], text: txt }));
  if (navigator.share) {
    var p = conImagen ? navigator.share({ files: [file], text: txt }) : navigator.share({ text: txt });
    p.catch(function (e) {
      // Cancelado por el usuario: nada. Otro fallo con imagen: reintento solo texto
      // (ya fuera del gesto, puede no abrirse; si no, portapapeles).
      if (e && e.name === 'AbortError') return;
      if (conImagen) {
        navigator.share({ text: txt }).catch(function () { nookCopiar(txt); });
      } else {
        nookCopiar(txt);
      }
    });
    return;
  }
  nookCopiar(txt);
}

function nookCopiar(txt) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(txt).then(nookAvisoCopiado).catch(function () {});
  }
}

// Precarga de la imagen del juego actual en cuanto carga la página
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', function () { nookPrecargarImagen(nookSlugDePagina()); });
} else {
  nookPrecargarImagen(nookSlugDePagina());
}

/* ─── Celebración de victoria (puzzles) ─── */
function nookCelebrate(message, callback, delay = 1700) {
  const overlay = document.createElement('div');
  overlay.style.cssText = `
    position: fixed; inset: 0; z-index: 9999;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    background: rgba(255,255,255,0.92);
    opacity: 0; transition: opacity 0.3s ease;
  `;
  overlay.innerHTML = `
    <div style="font-size: 64px; animation: nookPop 0.5s cubic-bezier(0.34,1.56,0.64,1);">🎉</div>
    <div style="font-size: 24px; font-weight: 800; color: var(--bar-accent-dark, #1A1A1A); margin-top: 12px; animation: nookPop 0.5s 0.1s cubic-bezier(0.34,1.56,0.64,1) both;">${message}</div>
  `;
  if (!document.getElementById('nook-celebrate-style')) {
    const style = document.createElement('style');
    style.id = 'nook-celebrate-style';
    style.textContent = '@keyframes nookPop { 0% { transform: scale(0.3); opacity: 0; } 100% { transform: scale(1); opacity: 1; } }';
    document.head.appendChild(style);
  }
  document.body.appendChild(overlay);
  requestAnimationFrame(() => overlay.style.opacity = '1');
  setTimeout(() => {
    overlay.style.opacity = '0';
    setTimeout(() => { overlay.remove(); if (callback) callback(); }, 300);
  }, delay);
}
