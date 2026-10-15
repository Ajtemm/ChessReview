// Grafikon ocene kroz partiju (Chart.js, učitan kao globalni `Chart`)
import { LABELS } from "/static/labels.js";
import { evalText, moveLabel } from "/static/format.js";

// Oznake koje dobijaju tačku u boji na grafikonu
const CHART_MARKS = new Set(["brilliant", "great", "miss", "mistake", "blunder"]);

// Pozadina, srednja linija (50%) i vertikalna linija na trenutnom potezu
function decorPlugin(getCurrentPly) {
  return {
    id: "decor",
    beforeDraw(chart) {
      const { ctx, chartArea: a } = chart;
      ctx.save();
      ctx.fillStyle = "#403d39";
      ctx.fillRect(a.left, a.top, a.right - a.left, a.bottom - a.top);
      ctx.restore();
    },
    afterDatasetsDraw(chart) {
      const { ctx, chartArea: a, scales } = chart;
      ctx.save();
      const mid = scales.y.getPixelForValue(50);
      ctx.strokeStyle = "rgba(128, 128, 128, 0.6)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(a.left, mid);
      ctx.lineTo(a.right, mid);
      ctx.stroke();

      const x = scales.x.getPixelForValue(getCurrentPly());
      ctx.strokeStyle = "#81b64c";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x, a.top);
      ctx.lineTo(x, a.bottom);
      ctx.stroke();
      ctx.restore();
    },
  };
}

// Pravi grafikon win% (iz ugla belog) za sve pozicije; pozicija k je posle poteza k.
// getCurrentPly() daje trenutni potez za vertikalnu liniju, onSelect(ply) se zove na klik.
export function createEvalChart(canvas, positions, moves, { getCurrentPly, onSelect }) {
  const labelAt = (i) => (i > 0 ? moves[i - 1].classification : null);
  const markAt = (i) => (CHART_MARKS.has(labelAt(i)) ? labelAt(i) : null);

  return new Chart(canvas, {
    type: "line",
    data: {
      labels: positions.map((_, i) => i),
      datasets: [{
        data: positions.map((p) => p.win),
        fill: "origin",
        backgroundColor: "#f0eee9",
        borderColor: "#d6d3ce",
        borderWidth: 1,
        tension: 0,
        pointRadius: (ctx) => (markAt(ctx.dataIndex) ? 3.5 : 0),
        pointHoverRadius: 4,
        pointBackgroundColor: (ctx) => {
          const label = markAt(ctx.dataIndex);
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
            title: ([item]) => (item.dataIndex === 0 ? "Početna pozicija" : moveLabel(moves[item.dataIndex - 1])),
            label: (item) => {
              const label = labelAt(item.dataIndex);
              const text = evalText(positions[item.dataIndex]);
              return label ? `${text}  ·  ${LABELS[label].name}` : text;
            },
          },
        },
      },
      onClick: (evt, _elements, chart) => {
        const points = chart.getElementsAtEventForMode(evt, "index", { intersect: false }, false);
        if (points.length) onSelect(points[0].index);
      },
    },
    plugins: [decorPlugin(getCurrentPly)],
  });
}
