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

/* ─── Compartir con imagen del juego (Web Share API Level 2) ─── */
async function nookShareWithImage(txt, gameSlug) {
  nookTrackShare(gameSlug);
  const url = nookSpaceUrl();
  if (gameSlug && navigator.canShare) {
    try {
      const resp = await fetch(`/static/games/${gameSlug}.webp`);
      const blob = await resp.blob();
      const file = new File([blob], 'nookplay.webp', { type: blob.type });
      if (navigator.canShare({ files: [file], text: txt })) {
        await navigator.share({ files: [file], text: txt });
        return;
      }
    } catch (e) { /* fallback abajo */ }
  }
  if (navigator.share) {
    navigator.share({ text: txt }).catch(() => {});
  } else {
    navigator.clipboard.writeText(txt).then(() => alert('¡Copiado! Compártelo donde quieras.')).catch(() => {});
  }
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
