/* ─────────────────────────────────────────────────────────────────────────────
   Nookplay — Shared Share Component
   Usage: shareGame({ correct, barName, gameTitle, detail, pct })
───────────────────────────────────────────────────────────────────────────── */

function shareGame({ correct, barName, gameTitle, detail, pct }) {
  const emoji = correct ? '✅' : '❌';
  const result = correct ? 'Lo conseguí' : 'Me ha ganado';
  const pctText = pct ? ` · Solo el ${pct} acertó hoy` : '';

  const txt = `${emoji} ${gameTitle} — ${barName}\n\n${result}${pctText}\n\n"${detail}"\n\n¿Puedes tú? → nookplay.app`;

  if (navigator.share) {
    navigator.share({ text: txt, url: 'https://nookplay.app' });
  } else {
    navigator.clipboard.writeText(txt)
      .then(() => alert('¡Copiado! Compártelo donde quieras.'));
  }
}
