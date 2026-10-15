// Lista partija: učitavanje sa /api/games i periodično osvežavanje statusa analize

const REFRESH_BUSY_MS = 5000;   // dok se nešto analizira
const REFRESH_IDLE_MS = 30000;  // inače, da se vide nove partije

const OUTCOME_LABELS = { win: "Pobeda", loss: "Poraz", draw: "Remi" };
const STATUS_LABELS = {
  done: "Analizirano",
  pending: "Na čekanju",
  running: "Analizira se",
  error: "Greška",
};
const TIME_CLASS_LABELS = { bullet: "Bullet", blitz: "Blitz", rapid: "Rapid", daily: "Dnevna" };

const body = document.getElementById("games-body");
const message = document.getElementById("message");
const summary = document.getElementById("summary");

// Mali pomoćnik za pravljenje elemenata (tekst ide kroz textContent, bez HTML injekcije)
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

function formatTimeControl(tc) {
  if (!tc) return "—";
  // Dnevne partije: "1/86400" = sekundi po potezu
  if (tc.includes("/")) {
    const days = Math.round(Number(tc.split("/")[1]) / 86400);
    return days === 1 ? "1 dan" : `${days} dana`;
  }
  const [base, inc] = tc.split("+").map(Number);
  const baseText = base >= 60 ? `${base / 60}` : `${base}s`;
  if (inc) return `${baseText} | ${inc}`;
  return base >= 60 ? `${baseText} min` : baseText;
}

function formatDate(iso) {
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}. ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function formatAccuracy(value) {
  return value === null || value === undefined ? "—" : value.toFixed(1);
}

function renderRow(game) {
  const tr = el("tr");
  tr.tabIndex = 0;
  const href = `/review/${encodeURIComponent(game.id)}`;
  tr.addEventListener("click", (e) => {
    if (e.target.closest("a")) return;  // link radi sam (i srednji klik / nova kartica)
    window.location.href = href;
  });
  tr.addEventListener("keydown", (e) => {
    if (e.key === "Enter") window.location.href = href;
  });

  const opp = el("td", "opponent");
  const link = el("a", null, game.opponent);
  link.href = href;
  opp.append(link);
  if (game.opponent_rating) opp.append(el("span", "rating", `(${game.opponent_rating})`));

  const res = el("td");
  res.append(el("span", `outcome ${game.outcome}`, OUTCOME_LABELS[game.outcome]));
  res.append(el("span", "score", game.result.replace("1/2", "½")));

  const color = el("td");
  color.append(el("span", `color-dot ${game.my_color}`));
  color.append(document.createTextNode(game.my_color === "white" ? "Beli" : "Crni"));

  const date = el("td", "hide-sm muted", formatDate(game.end_time));

  const time = el("td");
  time.append(document.createTextNode(formatTimeControl(game.time_control)));
  const tcl = TIME_CLASS_LABELS[game.time_class];
  if (tcl) time.append(el("span", "muted", ` · ${tcl}`));

  const acc = el("td", "num accuracy");
  acc.title = "Moja tačnost / tačnost protivnika";
  acc.append(el("strong", null, formatAccuracy(game.my_accuracy)));
  acc.append(el("span", "muted", `/ ${formatAccuracy(game.opponent_accuracy)}`));

  const status = el("td");
  status.append(el("span", `status ${game.status}`, STATUS_LABELS[game.status] || game.status));

  tr.append(opp, res, color, date, time, acc, status);
  return tr;
}

function renderSummary(games) {
  const count = (pred) => games.filter(pred).length;
  const wins = count((g) => g.outcome === "win");
  const losses = count((g) => g.outcome === "loss");
  const draws = count((g) => g.outcome === "draw");
  const analyzed = count((g) => g.status === "done");

  summary.replaceChildren(
    el("strong", null, String(games.length)), document.createTextNode(" partija · "),
    el("strong", null, `${wins}/${losses}/${draws}`), document.createTextNode(" pobeda/poraz/remi · analizirano "),
    el("strong", null, `${analyzed}/${games.length}`),
  );
}

async function load() {
  let busy = false;
  try {
    const resp = await fetch("/api/games");
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const games = await resp.json();

    body.replaceChildren(...games.map(renderRow));
    renderSummary(games);
    message.hidden = games.length > 0;
    message.className = "message";
    message.textContent = "Još nema partija. Pokreni preuzimanje partija.";
    busy = games.some((g) => g.status === "pending" || g.status === "running");
  } catch (err) {
    message.hidden = false;
    message.className = "message error";
    message.textContent = `Greška pri učitavanju partija (${err.message}).`;
  }
  setTimeout(load, busy ? REFRESH_BUSY_MS : REFRESH_IDLE_MS);
}

load();
