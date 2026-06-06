/* ─────────────────────────────────────────────────────────────────────────────
   Nookplay — Shared Stats Component
   Usage: initStats(barSlug, gameType)
───────────────────────────────────────────────────────────────────────────── */

const CIRCUM = 2 * Math.PI * 28;

async function loadStats(barSlug, gameType) {
  try {
    const res = await fetch(`/api/stats/${barSlug}/${gameType}`);
    const stats = await res.json();
    if (stats.total >= 1) renderStats(stats);
  } catch(e) {}
}

function renderStats(stats) {
  const wrap = document.getElementById('stats-block');
  if (!wrap) return;

  const pct = Math.round((stats.correct / stats.total) * 100);

  // Fill grid values
  const jugEl = document.getElementById('stat-jugadores');
  const tiempoEl = document.getElementById('stat-tiempo');
  if (jugEl) jugEl.textContent = stats.total;
  if (tiempoEl) tiempoEl.textContent = stats.avg_elapsed ? stats.avg_elapsed + 's' : '—';

  // Donut
  const pctEl = document.getElementById('donut-pct');
  const textEl = document.getElementById('donut-text');
  const descEl = document.getElementById('donut-desc');
  const arc = document.getElementById('donut-arc');

  if (pctEl) pctEl.textContent = pct + '%';
  if (textEl) textEl.textContent = pct + '%';
  if (descEl) {
    descEl.textContent = pct >= 70
      ? 'Hoy la mayoría lo encontró.'
      : pct >= 40
      ? 'Está costando. Engaña bien.'
      : 'Casi nadie lo ha pillado hoy.';
  }
  if (arc) {
    const offset = CIRCUM * (1 - pct / 100);
    setTimeout(() => {
      arc.style.transition = 'stroke-dashoffset 1s ease';
      arc.setAttribute('stroke-dashoffset', offset.toFixed(1));
    }, 300);
  }

  wrap.classList.add('visible');
}
