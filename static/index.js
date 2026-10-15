// Lista partija: učitavanje sa /api/games, status preuzimanja/analize sa /api/status
// i dugme za ručno preuzimanje novih partija
import { $, el } from "/static/dom.js";

const REFRESH_BUSY_MS = 2000;   // dok traje preuzimanje ili analiza
const REFRESH_IDLE_MS = 30000;  // inače, da se vide partije iz automatskog preuzimanja

const OUTCOME_LABELS = { win: "Pobeda", loss: "Poraz", draw: "Remi" };
const STATUS_LABELS = {
  done: "Analizirano",
  pending: "Na čekanju",
  running: "Analizira se",
  error: "Greška",
};
const TIME_CLASS_LABELS = { bullet: "Bullet", blitz: "Blitz", rapid: "Rapid", daily: "Dnevna" };

const body = $("games-body");
const message = $("message");
const summary = $("summary");
const fetchBtn = $("fetch-btn");
const fetchState = $("fetch-state");
const fetchMeta = $("fetch-meta");

let refreshTimer = null;

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

// Vreme za status: danas samo sat, inače i datum
function formatWhen(iso) {
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  const time = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  return d.toDateString() === new Date().toDateString()
    ? time
    : `${pad(d.getDate())}.${pad(d.getMonth() + 1)}. ${time}`;
}

function newGamesText(n) {
  if (n === 0) return "nema novih";
  if (n === 1) return "1 nova";
  return n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? `${n} nove` : `${n} novih`;
}

function renderStatus(status) {
  const { fetch: f, analysis: a } = status;
  fetchBtn.disabled = f.fetching;

  fetchState.className = "fetch-state";
  if (f.fetching) {
    fetchState.classList.add("busy");
    fetchState.textContent = "Preuzimanje…";
  } else if (a.running) {
    fetchState.classList.add("busy");
    fetchState.textContent = `Analizira se ${a.current}/${a.total}`;
  } else if (f.last_error) {
    fetchState.classList.add("error");
    fetchState.textContent = `Greška pri preuzimanju: ${f.last_error}`;
  } else {
    fetchState.textContent = "";
  }

  const meta = [];
  if (f.last_fetch_at) {
    const result = f.last_result ? ` (${newGamesText(f.last_result.new)})` : "";
    meta.push(`Poslednje preuzimanje: ${formatWhen(f.last_fetch_at)}${result}`);
  }
  if (f.next_run_at) meta.push(`sledeće automatski u ${formatWhen(f.next_run_at)}`);
  fetchMeta.textContent = meta.join(" · ");
}

function scheduleLoad(ms) {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(load, ms);
}

async function load() {
  let busy = false;
  try {
    const [gamesResp, statusResp] = await Promise.all([fetch("/api/games"), fetch("/api/status")]);
    if (!gamesResp.ok) throw new Error(`HTTP ${gamesResp.status}`);
    const games = await gamesResp.json();

    body.replaceChildren(...games.map(renderRow));
    renderSummary(games);
    message.hidden = games.length > 0;
    message.className = "message";
    message.textContent = "Još nema partija. Klikni „Preuzmi nove partije“.";
    busy = games.some((g) => g.status === "pending" || g.status === "running");

    if (statusResp.ok) {
      const status = await statusResp.json();
      renderStatus(status);
      busy = busy || status.fetch.fetching || status.analysis.running;
    }
  } catch (err) {
    message.hidden = false;
    message.className = "message error";
    message.textContent = `Greška pri učitavanju partija (${err.message}).`;
  }
  scheduleLoad(busy ? REFRESH_BUSY_MS : REFRESH_IDLE_MS);
}

fetchBtn.addEventListener("click", async () => {
  fetchBtn.disabled = true;
  try {
    const resp = await fetch("/api/fetch", { method: "POST" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    renderStatus(await resp.json());
  } catch (err) {
    fetchState.className = "fetch-state error";
    fetchState.textContent = `Greška: ${err.message}`;
    fetchBtn.disabled = false;
  }
  // Brzo osvežavanje dok traje preuzimanje i analiza
  scheduleLoad(REFRESH_BUSY_MS);
});

load();
