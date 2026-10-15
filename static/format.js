// Prikaz ocena i poteza na Review ekranu

export function hasEval(pos) {
  return Boolean(pos) && (pos.cp !== null || pos.mate !== null);
}

// Ocena za prikaz: "+1.2", "M3", "-M2"; na mat-poziciji rezultat ("1-0", "0-1").
// Bez znaka (signed = false) za eval bar, gde se vidi na čijoj je strani broj.
export function evalText(pos, signed = true) {
  if (!hasEval(pos)) return "";
  if (pos.mate !== null) {
    if (pos.mate === 0) return pos.turn === "white" ? "0-1" : "1-0";
    return `${pos.mate < 0 && signed ? "-" : ""}M${Math.abs(pos.mate)}`;
  }
  const v = pos.cp / 100;
  if (!signed) return Math.abs(v).toFixed(1);
  return `${v > 0 ? "+" : ""}${v.toFixed(1)}`;
}

// Bez ocene (analiza nije gotova) beli se računa kao "bolji", da eval bar stoji na sredini
export function whiteIsBetter(pos) {
  return pos.win === null ? true : pos.win >= 50;
}

// "12. Nf3" ili "12... Nf6"
export function moveLabel(move) {
  return `${move.move_number}${move.color === "white" ? "." : "..."} ${move.san}`;
}
