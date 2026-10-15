// Review jedne partije: tabla (chessground), eval bar, grafikon (Chart.js), lista poteza
import { Chessground } from "/static/vendor/chessground/chessground.min.js";
import { isMuted, playSound, setMuted } from "/static/sounds.js";

const POLL_MS = 5000;  // dok analiza nije gotova

// ------------------------------------------------------------ oznake poteza

const SVG = {
  star: '<svg viewBox="0 0 24 24"><path fill="#fff" d="M12 2.5l2.9 6.3 6.9.7-5.2 4.7 1.5 6.8L12 17.5 5.9 21l1.5-6.8L2.2 9.5l6.9-.7z"/></svg>',
  thumb: '<svg viewBox="0 0 24 24"><path fill="#fff" d="M3 10h3.5v10H3zM8.5 20h8.3a2 2 0 0 0 2-1.6l1.4-6.6A2 2 0 0 0 18.2 9.3H14l.8-3.7a1.7 1.7 0 0 0-3.1-1.2L8.5 9.8z"/></svg>',
  check: '<svg viewBox="0 0 24 24"><path fill="none" stroke="#fff" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" d="M5.5 12.5l4.2 4.2 8.8-9.4"/></svg>',
  book: '<svg viewBox="0 0 24 24"><path fill="#fff" d="M3 5.2c2.8-1.3 5.8-1.2 8.4.6v13.4c-2.6-1.6-5.6-1.8-8.4-.6zM21 5.2c-2.8-1.3-5.8-1.2-8.4.6v13.4c2.6-1.6 5.6-1.8 8.4-.6z"/></svg>',
  cross: '<svg viewBox="0 0 24 24"><path fill="none" stroke="#fff" stroke-width="3.4" stroke-linecap="round" d="M6.5 6.5l11 11M17.5 6.5l-11 11"/></svg>',
};

const LABELS = {
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
const LABEL_ORDER = Object.keys(LABELS);
// Moji potezi sa ovim oznakama dobijaju strelicu najboljeg poteza
const BAD = new Set(["inaccuracy", "mistake", "miss", "blunder"]);
// Tačke na grafikonu
const CHART_MARKS = new Set(["brilliant", "great", "miss", "mistake", "blunder"]);

function icon(label) {
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

// ------------------------------------------------------------ pomoćne funkcije

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

function hasEval(pos) {
  return pos && (pos.cp !== null || pos.mate !== null);
}

// Ocena za prikaz: "+1.2", "M3", "-M2"; na mat-poziciji rezultat
function evalText(pos, signed = true) {
  if (!hasEval(pos)) return "";
  if (pos.mate !== null) {
    if (pos.mate === 0) return pos.turn === "white" ? "0-1" : "1-0";
    return `${pos.mate < 0 && signed ? "-" : ""}M${Math.abs(pos.mate)}`;
  }
  const v = pos.cp / 100;
  if (!signed) return Math.abs(v).toFixed(1);
  return `${v > 0 ? "+" : ""}${v.toFixed(1)}`;
}

function whiteIsBetter(pos) {
  return pos.win === null ? true : pos.win >= 50;
}

function moveLabel(move) {
  return `${move.move_number}${move.color === "white" ? "." : "..."} ${move.san}`;
}

// ------------------------------------------------------------ stanje

const gid = decodeURIComponent(location.pathname.split("/").filter(Boolean).pop());
const state = {
  data: null,
  ply: 0,
  orientation: "white",
};

let cg = null;
let chart = null;

const $ = (id) => document.getElementById(id);

// ------------------------------------------------------------ prikaz

function renderPlayers() {
  const { game } = state.data;
  const top = state.orientation === "white" ? "black" : "white";
  const bottom = state.orientation;
  for (const [slot, color] of [["player-top", top], ["player-bottom", bottom]]) {
    const box = $(slot);
    box.replaceChildren();
    box.append(el("span", `color-dot ${color}`));
    box.append(el("span", null, game[color]));
    if (game[`${color}_rating`]) box.append(el("span", "rating muted", `(${game[`${color}_rating`]})`));
    const acc = game[`${color}_accuracy`];
    if (acc !== null) box.append(el("span", "player-acc", `Tačnost ${acc.toFixed(1)}`));
  }
}

function renderAccuracy() {
  const { game } = state.data;
  const box = $("accuracy");
  box.replaceChildren();
  for (const color of ["white", "black"]) {
    const wrap = el("div", "acc-player");
    const name = el("div", `acc-name${color === game.my_color ? " me" : ""}`, game[color]);
    const acc = game[`${color}_accuracy`];
    wrap.append(name, el("div", `acc-box ${color}`, acc === null ? "—" : acc.toFixed(1)));
    wrap.append(el("div", "acc-label", "Tačnost"));
    box.append(wrap);
  }
}

function renderCounts() {
  const { moves } = state.data;
  const table = $("counts");
  table.replaceChildren();
  const head = el("tr");
  head.append(el("td"), el("td", "n muted", "Beli"), el("td", "n muted", "Crni"));
  table.append(head);
  for (const label of LABEL_ORDER) {
    const count = (color) => moves.filter((m) => m.color === color && m.classification === label).length;
    const tr = el("tr");
    const cell = el("td");
    const inner = el("div", "label-cell");
    inner.append(icon(label), el("span", null, LABELS[label].name));
    cell.append(inner);
    tr.append(cell, el("td", "n", String(count("white"))), el("td", "n", String(count("black"))));
    table.append(tr);
  }
}

function renderMoveList() {
  const { moves } = state.data;
  const box = $("moves");
  box.replaceChildren();
  let row = null;
  for (const move of moves) {
    if (move.color === "white" || !row) {
      row = el("div", "move-row");
      row.append(el("span", "move-no", `${move.move_number}.`));
      if (move.color === "black") row.append(el("span"));  // partija počinje crnim
      box.append(row);
    }
    const btn = el("button", "move");
    btn.type = "button";
    btn.dataset.ply = move.ply;
    if (move.classification) btn.append(icon(move.classification));
    btn.append(el("span", null, move.san));
    btn.addEventListener("click", () => goTo(move.ply));
    row.append(btn);
  }
}

function renderCoach() {
  const { moves, positions, game } = state.data;
  const box = $("coach");
  box.replaceChildren();
  const pos = positions[state.ply];

  if (game.status !== "done") {
    box.append(el("div", "muted", game.status === "error"
      ? "Analiza ove partije nije uspela."
      : "Analiza je u toku… ocene i oznake će se pojaviti kad bude gotova."));
    return;
  }
  if (state.ply === 0) {
    box.append(el("div", "coach-head", "Početna pozicija"));
    box.append(el("div", "coach-best", "Koristi ← → ili dugmad ispod za kretanje kroz partiju."));
    return;
  }

  const move = moves[state.ply - 1];
  const spec = LABELS[move.classification];
  const head = el("div", "coach-head");
  if (spec) head.append(icon(move.classification));
  head.append(el("span", null, spec ? `${move.san} ${spec.phrase}` : move.san));
  if (spec) head.querySelector("span:last-child").style.color = spec.color;
  if (hasEval(pos)) head.append(el("span", `eval-chip ${whiteIsBetter(pos) ? "white" : "black"}`, evalText(pos)));
  box.append(head);

  const notBest = move.best_san && move.uci !== move.best_uci && !["book", "brilliant", "great"].includes(move.classification);
  if (notBest) {
    const best = el("div", "coach-best");
    best.append(document.createTextNode("Najbolji potez je bio "), el("strong", null, move.best_san));
    box.append(best);
  }
}

function renderEvalBar() {
  const pos = state.data.positions[state.ply];
  const bar = $("eval-bar");
  const fill = $("eval-fill");
  const text = $("eval-text");
  bar.classList.toggle("flipped", state.orientation === "black");
  fill.style.height = `${pos.win === null ? 50 : pos.win}%`;

  const whiteBetter = whiteIsBetter(pos);
  // Broj stoji na strani onoga ko vodi
  const whiteAtBottom = state.orientation === "white";
  const atBottom = whiteBetter === whiteAtBottom;
  text.className = `eval-text ${atBottom ? "at-bottom" : "at-top"} ${whiteBetter ? "white-side" : "black-side"}`;
  text.textContent = evalText(pos, false);
}

function renderBoard(animate = true) {
  const { positions, moves, game } = state.data;
  const pos = positions[state.ply];
  const move = state.ply > 0 ? moves[state.ply - 1] : null;
  const lastMove = pos.last_move ? [pos.last_move.slice(0, 2), pos.last_move.slice(2, 4)] : undefined;

  // Okretanje mora kroz toggleOrientation (set ne crta tablu iznova)
  if (cg.state.orientation !== state.orientation) cg.toggleOrientation();
  cg.set({
    fen: pos.fen,
    turnColor: pos.turn,
    check: pos.check,
    lastMove,
    animation: { enabled: animate },
  });

  // Strelica najboljeg poteza kad je moj potez bio greška
  const shapes = [];
  if (move && move.color === game.my_color && BAD.has(move.classification) && move.best_uci) {
    shapes.push({ orig: move.best_uci.slice(0, 2), dest: move.best_uci.slice(2, 4), brush: "green" });
  }
  cg.setAutoShapes(shapes);

  // Ikonica oznake u gornjem desnom uglu polja na koje je figura stigla
  const boardIcon = $("board-icon");
  if (move && move.classification) {
    const dest = move.uci.slice(2, 4);
    const file = dest.charCodeAt(0) - 97;
    const rank = Number(dest[1]) - 1;
    const x = state.orientation === "white" ? file : 7 - file;
    const y = state.orientation === "white" ? 7 - rank : rank;
    boardIcon.style.left = `${(x + 1) * 12.5}%`;
    boardIcon.style.top = `${y * 12.5}%`;
    boardIcon.replaceChildren(icon(move.classification));
    boardIcon.hidden = false;
  } else {
    boardIcon.hidden = true;
  }
}

function renderActiveMove() {
  const box = $("moves");
  for (const btn of box.querySelectorAll(".move.active")) btn.classList.remove("active");
  const active = box.querySelector(`.move[data-ply="${state.ply}"]`);
  if (!active) {
    if (state.ply === 0) box.scrollTop = 0;
    return;
  }
  active.classList.add("active");
  // Skrolujemo samo listu poteza, ne celu stranicu
  const top = active.offsetTop - box.offsetTop;
  if (top < box.scrollTop + 8) box.scrollTop = top - 8;
  else if (top + active.offsetHeight > box.scrollTop + box.clientHeight - 8) {
    box.scrollTop = top + active.offsetHeight - box.clientHeight + 8;
  }
}

function renderNav() {
  const last = state.data.moves.length;
  $("btn-first").disabled = $("btn-prev").disabled = state.ply === 0;
  $("btn-next").disabled = $("btn-last").disabled = state.ply === last;
}

// Zvuk pri promeni poteza: unazad običan potez, inače zvuk poteza na koji smo stigli
// (šah ima prednost nad uzimanjem)
function playMoveSound(fromPly) {
  const { ply } = state;
  if (ply === fromPly || ply === 0) return;
  if (ply === fromPly - 1) {
    playSound("move");
    return;
  }
  const move = state.data.moves[ply - 1];
  if (state.data.positions[ply].check) playSound("check");
  else if (move.capture) playSound("capture");
  else playSound("move");
}

function goTo(ply, animate = true) {
  const last = state.data.moves.length;
  const fromPly = state.ply;
  state.ply = Math.max(0, Math.min(last, ply));
  playMoveSound(fromPly);
  // Skok preko više poteza bez animacije, da figure ne "lete" preko table
  renderBoard(animate);
  renderEvalBar();
  renderCoach();
  renderActiveMove();
  renderNav();
  if (chart) chart.update("none");
}

// ------------------------------------------------------------ grafikon

// Pozadina grafikona, srednja linija i vertikalna linija na trenutnom potezu
const chartDecor = {
  id: "decor",
  beforeDraw(c) {
    const { ctx, chartArea: a } = c;
    ctx.save();
    ctx.fillStyle = "#403d39";
    ctx.fillRect(a.left, a.top, a.right - a.left, a.bottom - a.top);
    ctx.restore();
  },
  afterDatasetsDraw(c) {
    const { ctx, chartArea: a, scales } = c;
    ctx.save();
    const mid = scales.y.getPixelForValue(50);
    ctx.strokeStyle = "rgba(128, 128, 128, 0.6)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(a.left, mid);
    ctx.lineTo(a.right, mid);
    ctx.stroke();

    const x = scales.x.getPixelForValue(state.ply);
    ctx.strokeStyle = "#81b64c";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(x, a.top);
    ctx.lineTo(x, a.bottom);
    ctx.stroke();
    ctx.restore();
  },
};

function renderChart() {
  const { positions, moves } = state.data;
  const analyzed = positions.some((p) => p.win !== null);
  $("chart-empty").hidden = analyzed;
  if (!analyzed) return;

  // Tačka u boji oznake za važne poteze (pozicija k = posle poteza k)
  const markOf = (i) => {
    const label = i > 0 ? moves[i - 1].classification : null;
    return CHART_MARKS.has(label) ? label : null;
  };

  const data = positions.map((p) => (p.win === null ? null : p.win));
  if (chart) chart.destroy();
  chart = new Chart($("chart"), {
    type: "line",
    data: {
      labels: positions.map((_, i) => i),
      datasets: [{
        data,
        fill: "origin",
        backgroundColor: "#f0eee9",
        borderColor: "#d6d3ce",
        borderWidth: 1,
        tension: 0,
        pointRadius: (ctx) => (markOf(ctx.dataIndex) ? 3.5 : 0),
        pointHoverRadius: 4,
        pointBackgroundColor: (ctx) => {
          const label = markOf(ctx.dataIndex);
          return label ? LABELS[label].color : "#d6d3ce";
        },
        pointBorderColor: "#262421",
        pointBorderWidth: 1,
      }],
    },
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      // Mesto za tačke na ivicama grafikona
      layout: { padding: 5 },
      scales: {
        x: { type: "linear", display: false, min: 0, max: positions.length - 1 },
        y: { display: false, min: 0, max: 100 },
      },
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          displayColors: false,
          callbacks: {
            title: (items) => {
              const i = items[0].dataIndex;
              return i === 0 ? "Početna pozicija" : moveLabel(moves[i - 1]);
            },
            label: (item) => {
              const i = item.dataIndex;
              const label = i > 0 ? moves[i - 1].classification : null;
              const text = evalText(positions[i]);
              return label ? `${text}  ·  ${LABELS[label].name}` : text;
            },
          },
        },
      },
      onClick: (evt, _elements, c) => {
        const points = c.getElementsAtEventForMode(evt, "index", { intersect: false }, false);
        if (points.length) goTo(points[0].index, false);
      },
    },
    plugins: [chartDecor],
  });
}

// ------------------------------------------------------------ učitavanje

function renderAll() {
  const { game } = state.data;
  document.title = `Review · ${game.white} – ${game.black}`;
  const outcome = { win: "pobeda", loss: "poraz", draw: "remi" }[game.outcome];
  $("game-meta").textContent = `${game.white} – ${game.black} · ${game.result} (${outcome})`;
  renderPlayers();
  renderAccuracy();
  renderCounts();
  renderMoveList();
  renderChart();
  goTo(state.ply, false);
}

async function fetchGame() {
  const resp = await fetch(`/api/games/${encodeURIComponent(gid)}`);
  if (!resp.ok) throw new Error(resp.status === 404 ? "Partija nije pronađena" : `HTTP ${resp.status}`);
  return resp.json();
}

// Dok analiza traje, povremeno proveravamo da li je gotova
async function pollUntilAnalyzed() {
  try {
    const data = await fetchGame();
    if (data.game.status !== state.data.game.status || data.game.status === "done") {
      state.data = data;
      renderAll();
    }
    if (data.game.status === "done" || data.game.status === "error") return;
  } catch {
    // Privremena greška: pokušaćemo ponovo
  }
  setTimeout(pollUntilAnalyzed, POLL_MS);
}

function bindControls() {
  $("btn-first").addEventListener("click", () => goTo(0, false));
  $("btn-prev").addEventListener("click", () => goTo(state.ply - 1));
  $("btn-next").addEventListener("click", () => goTo(state.ply + 1));
  $("btn-last").addEventListener("click", () => goTo(state.data.moves.length, false));
  $("btn-flip").addEventListener("click", flip);
  $("btn-sound").addEventListener("click", toggleSound);
  renderSoundButton();

  document.addEventListener("keydown", (e) => {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    const actions = {
      ArrowLeft: () => goTo(state.ply - 1),
      ArrowRight: () => goTo(state.ply + 1),
      ArrowUp: () => goTo(0, false),
      Home: () => goTo(0, false),
      ArrowDown: () => goTo(state.data.moves.length, false),
      End: () => goTo(state.data.moves.length, false),
      f: flip,
      F: flip,
      m: toggleSound,
      M: toggleSound,
    };
    const action = actions[e.key];
    if (!action) return;
    e.preventDefault();
    action();
  });

  window.addEventListener("resize", () => cg.redrawAll());
}

function renderSoundButton() {
  const btn = $("btn-sound");
  const muted = isMuted();
  btn.textContent = muted ? "🔇" : "🔊";
  btn.title = muted ? "Uključi zvuk (M)" : "Isključi zvuk (M)";
  btn.setAttribute("aria-label", btn.title);
  btn.setAttribute("aria-pressed", String(muted));
}

function toggleSound() {
  setMuted(!isMuted());
  renderSoundButton();
}

function flip() {
  state.orientation = state.orientation === "white" ? "black" : "white";
  renderPlayers();
  goTo(state.ply, false);
}

async function init() {
  try {
    state.data = await fetchGame();
  } catch (err) {
    document.querySelector(".review").hidden = true;
    $("error").hidden = false;
    $("error").textContent = `Greška pri učitavanju partije: ${err.message}.`;
    return;
  }

  state.orientation = state.data.game.my_color;
  cg = Chessground($("board"), {
    viewOnly: true,
    coordinates: true,
    orientation: state.orientation,
    animation: { enabled: true, duration: 180 },
    highlight: { lastMove: true, check: true },
    drawable: { enabled: false, visible: true },
  });
  bindControls();
  renderAll();

  if (state.data.game.status !== "done" && state.data.game.status !== "error") {
    setTimeout(pollUntilAnalyzed, POLL_MS);
  }
}

init();
