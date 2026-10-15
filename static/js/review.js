// Review jedne partije: stanje ekrana, paneli, navigacija i učitavanje podataka.
// Tabla je u board.js, grafikon u eval-chart.js, oznake u labels.js, zvuk u sounds.js.
import { ReviewBoard } from "/static/js/board.js";
import { $, el } from "/static/js/dom.js";
import { createEvalChart } from "/static/js/eval-chart.js";
import { evalText, hasEval, whiteIsBetter } from "/static/js/format.js";
import { BAD_LABELS, icon, LABEL_ORDER, LABELS } from "/static/js/labels.js";
import { isMuted, playSound, setMuted } from "/static/js/sounds.js";

const POLL_MS = 5000;  // dok analiza nije gotova

const gid = decodeURIComponent(location.pathname.split("/").filter(Boolean).pop());

const state = {
  data: null,           // odgovor /api/games/<id>: {game, positions, moves}
  ply: 0,               // trenutna pozicija (0 = početna, k = posle k-tog polupoteza)
  orientation: "white",
};

let board = null;
let chart = null;

const lastPly = () => state.data.moves.length;
const currentMove = () => (state.ply > 0 ? state.data.moves[state.ply - 1] : null);

// ------------------------------------------------------------ paneli (crtaju se jednom po učitavanju)

function renderHeader() {
  const { game } = state.data;
  document.title = `Review · ${game.white} – ${game.black}`;
  const outcome = { win: "pobeda", loss: "poraz", draw: "remi" }[game.outcome];
  $("game-meta").textContent = `${game.white} – ${game.black} · ${game.result} (${outcome})`;
}

function renderPlayers() {
  const { game } = state.data;
  const top = state.orientation === "white" ? "black" : "white";
  for (const [slot, color] of [["player-top", top], ["player-bottom", state.orientation]]) {
    const box = $(slot);
    box.replaceChildren(el("span", `color-dot ${color}`), el("span", null, game[color]));
    const rating = game[`${color}_rating`];
    if (rating) box.append(el("span", "rating muted", `(${rating})`));
    const acc = game[`${color}_accuracy`];
    if (acc !== null) box.append(el("span", "player-acc", `Tačnost ${acc.toFixed(1)}`));
  }
}

function renderAccuracy() {
  const { game } = state.data;
  $("accuracy").replaceChildren(...["white", "black"].map((color) => {
    const acc = game[`${color}_accuracy`];
    const wrap = el("div", "acc-player");
    wrap.append(
      el("div", `acc-name${color === game.my_color ? " me" : ""}`, game[color]),
      el("div", `acc-box ${color}`, acc === null ? "—" : acc.toFixed(1)),
      el("div", "acc-label", "Tačnost"),
    );
    return wrap;
  }));
}

// Broj poteza po oznaci za belog i crnog
function renderCounts() {
  const { moves } = state.data;
  const count = (color, label) => moves.filter((m) => m.color === color && m.classification === label).length;
  const head = el("tr");
  head.append(el("td"), el("td", "n muted", "Beli"), el("td", "n muted", "Crni"));
  const rows = LABEL_ORDER.map((label) => {
    const name = el("div", "label-cell");
    name.append(icon(label), el("span", null, LABELS[label].name));
    const nameCell = el("td");
    nameCell.append(name);
    const tr = el("tr");
    tr.append(nameCell, el("td", "n", String(count("white", label))), el("td", "n", String(count("black", label))));
    return tr;
  });
  $("counts").replaceChildren(head, ...rows);
}

// Lista poteza u parovima: "12. Nf3 Nf6"
function renderMoveList() {
  const box = $("moves");
  box.replaceChildren();
  let row = null;
  for (const move of state.data.moves) {
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

function renderChart() {
  const { positions, moves } = state.data;
  const analyzed = positions.some((p) => p.win !== null);
  $("chart-empty").hidden = analyzed;
  if (chart) chart.destroy();
  chart = analyzed
    ? createEvalChart($("chart"), positions, moves, {
        getCurrentPly: () => state.ply,
        onSelect: (ply) => goTo(ply, false),
      })
    : null;
}

// ------------------------------------------------------------ trenutna pozicija

function renderBoard(animate) {
  const move = currentMove();
  // Strelica najboljeg poteza samo kad je moj potez bio greška
  const showBest = move && move.color === state.data.game.my_color
    && BAD_LABELS.has(move.classification) && move.best_uci;
  board.show(state.data.positions[state.ply], move, {
    bestArrow: showBest ? move.best_uci : null,
    animate,
  });
}

function renderEvalBar() {
  const pos = state.data.positions[state.ply];
  $("eval-bar").classList.toggle("flipped", state.orientation === "black");
  $("eval-fill").style.height = `${pos.win === null ? 50 : pos.win}%`;

  // Broj stoji na strani onoga ko vodi
  const whiteBetter = whiteIsBetter(pos);
  const atBottom = whiteBetter === (state.orientation === "white");
  const text = $("eval-text");
  text.className = `eval-text ${atBottom ? "at-bottom" : "at-top"} ${whiteBetter ? "white-side" : "black-side"}`;
  text.textContent = evalText(pos, false);
}

// Objašnjenje trenutnog poteza: oznaka, ocena i najbolji potez
function renderCoach() {
  const { positions, game } = state.data;
  const box = $("coach");
  box.replaceChildren();

  if (game.status !== "done") {
    box.append(el("div", "muted", game.status === "error"
      ? "Analiza ove partije nije uspela."
      : "Analiza je u toku… ocene i oznake će se pojaviti kad bude gotova."));
    return;
  }
  const move = currentMove();
  if (!move) {
    box.append(el("div", "coach-head", "Početna pozicija"),
               el("div", "coach-best", "Koristi ← → ili dugmad ispod za kretanje kroz partiju."));
    return;
  }

  const spec = LABELS[move.classification];
  const head = el("div", "coach-head");
  if (spec) {
    const title = el("span", null, `${move.san} ${spec.phrase}`);
    title.style.color = spec.color;
    head.append(icon(move.classification), title);
  } else {
    head.append(el("span", null, move.san));
  }
  const pos = positions[state.ply];
  if (hasEval(pos)) head.append(el("span", `eval-chip ${whiteIsBetter(pos) ? "white" : "black"}`, evalText(pos)));
  box.append(head);

  const showBest = move.best_san && move.uci !== move.best_uci
    && !["book", "brilliant", "great"].includes(move.classification);
  if (showBest) {
    const best = el("div", "coach-best");
    best.append(document.createTextNode("Najbolji potez je bio "), el("strong", null, move.best_san));
    box.append(best);
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
  $("btn-first").disabled = $("btn-prev").disabled = state.ply === 0;
  $("btn-next").disabled = $("btn-last").disabled = state.ply === lastPly();
}

// Zvuk pri promeni poteza: unazad običan potez, inače zvuk poteza na koji smo stigli
// (šah ima prednost nad uzimanjem)
function playMoveSound(fromPly) {
  const { ply } = state;
  if (ply === fromPly || ply === 0) return;
  if (ply === fromPly - 1) return playSound("move");
  if (state.data.positions[ply].check) return playSound("check");
  playSound(currentMove().capture ? "capture" : "move");
}

// Prelazak na poziciju posle `ply` polupoteza. Skok preko više poteza ide bez
// animacije (animate = false), da figure ne "lete" preko table.
function goTo(ply, animate = true) {
  const fromPly = state.ply;
  state.ply = Math.max(0, Math.min(lastPly(), ply));
  playMoveSound(fromPly);
  renderBoard(animate);
  renderEvalBar();
  renderCoach();
  renderActiveMove();
  renderNav();
  if (chart) chart.update("none");
}

// ------------------------------------------------------------ kontrole

function flip() {
  state.orientation = state.orientation === "white" ? "black" : "white";
  board.setOrientation(state.orientation);
  renderPlayers();
  goTo(state.ply, false);
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

function bindControls() {
  const toStart = () => goTo(0, false);
  const toEnd = () => goTo(lastPly(), false);
  const back = () => goTo(state.ply - 1);
  const forward = () => goTo(state.ply + 1);

  $("btn-first").addEventListener("click", toStart);
  $("btn-prev").addEventListener("click", back);
  $("btn-next").addEventListener("click", forward);
  $("btn-last").addEventListener("click", toEnd);
  $("btn-flip").addEventListener("click", flip);
  $("btn-sound").addEventListener("click", toggleSound);
  renderSoundButton();

  const keys = {
    ArrowLeft: back, ArrowRight: forward,
    ArrowUp: toStart, Home: toStart,
    ArrowDown: toEnd, End: toEnd,
    f: flip, F: flip,
    m: toggleSound, M: toggleSound,
  };
  document.addEventListener("keydown", (e) => {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    const action = keys[e.key];
    if (!action) return;
    e.preventDefault();
    action();
  });
}

// ------------------------------------------------------------ učitavanje

function renderAll() {
  renderHeader();
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

const analysisFinished = (status) => status === "done" || status === "error";

// Dok analiza traje, povremeno proveravamo da li je gotova
async function pollUntilAnalyzed() {
  try {
    const data = await fetchGame();
    if (data.game.status !== state.data.game.status || data.game.status === "done") {
      state.data = data;
      renderAll();
    }
    if (analysisFinished(data.game.status)) return;
  } catch {
    // Privremena greška: pokušaćemo ponovo
  }
  setTimeout(pollUntilAnalyzed, POLL_MS);
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
  board = new ReviewBoard($("board"), $("board-icon"), state.orientation);
  bindControls();
  renderAll();

  if (!analysisFinished(state.data.game.status)) setTimeout(pollUntilAnalyzed, POLL_MS);
}

init();
