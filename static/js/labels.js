// Oznake poteza: naziv, rečenica za objašnjenje, boja i ikonica (kao na Chess.com-u)

const SVG = {
  star: '<svg viewBox="0 0 24 24"><path fill="#fff" d="M12 2.5l2.9 6.3 6.9.7-5.2 4.7 1.5 6.8L12 17.5 5.9 21l1.5-6.8L2.2 9.5l6.9-.7z"/></svg>',
  thumb: '<svg viewBox="0 0 24 24"><path fill="#fff" d="M3 10h3.5v10H3zM8.5 20h8.3a2 2 0 0 0 2-1.6l1.4-6.6A2 2 0 0 0 18.2 9.3H14l.8-3.7a1.7 1.7 0 0 0-3.1-1.2L8.5 9.8z"/></svg>',
  check: '<svg viewBox="0 0 24 24"><path fill="none" stroke="#fff" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" d="M5.5 12.5l4.2 4.2 8.8-9.4"/></svg>',
  book: '<svg viewBox="0 0 24 24"><path fill="#fff" d="M3 5.2c2.8-1.3 5.8-1.2 8.4.6v13.4c-2.6-1.6-5.6-1.8-8.4-.6zM21 5.2c-2.8-1.3-5.8-1.2-8.4.6v13.4c2.6-1.6 5.6-1.8 8.4-.6z"/></svg>',
  cross: '<svg viewBox="0 0 24 24"><path fill="none" stroke="#fff" stroke-width="3.4" stroke-linecap="round" d="M6.5 6.5l11 11M17.5 6.5l-11 11"/></svg>',
};

export const LABELS = {
  brilliant:  { name: "Briljantno",   phrase: "je briljantan potez",  color: "#26c2a3", glyph: "!!" },
  great:      { name: "Sjajno",       phrase: "je sjajan potez",      color: "#5c8bb0", glyph: "!" },
  best:       { name: "Najbolje",     phrase: "je najbolji potez",    color: "#81b64c", svg: SVG.star },
  excellent:  { name: "Odlično",      phrase: "je odličan potez",     color: "#96bc4b", svg: SVG.thumb },
  good:       { name: "Dobro",        phrase: "je dobar potez",       color: "#96af8b", svg: SVG.check },
  book:       { name: "Teorija",      phrase: "je potez iz teorije",  color: "#a88865", svg: SVG.book },
  inaccuracy: { name: "Nepreciznost", phrase: "je nepreciznost",      color: "#f0b93a", glyph: "?!" },
  mistake:    { name: "Greška",       phrase: "je greška",            color: "#ff9a3d", glyph: "?" },
  miss:       { name: "Propušteno",   phrase: "je propuštena prilika", color: "#ff7769", svg: SVG.cross },
  blunder:    { name: "Gruba greška", phrase: "je gruba greška",      color: "#e8402f", glyph: "??" },
};

export const LABEL_ORDER = Object.keys(LABELS);

// Greške: posle mog poteza sa ovom oznakom prikazuje se strelica najboljeg poteza
export const BAD_LABELS = new Set(["inaccuracy", "mistake", "miss", "blunder"]);

// Okrugla ikonica u boji oznake
export function icon(label) {
  const spec = LABELS[label];
  const span = document.createElement("span");
  span.className = "cls-icon";
  if (!spec) return span;
  span.style.background = spec.color;
  span.title = spec.name;
  if (spec.svg) span.innerHTML = spec.svg;  // naš statički SVG, ne podaci sa servera
  else span.textContent = spec.glyph;
  return span;
}
