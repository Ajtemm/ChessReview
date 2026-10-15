// Tabla za Review: chessground, poslednji potez, šah, strelica najboljeg poteza
// i ikonica oznake na polju na koje je figura stigla
import { Chessground } from "/static/vendor/chessground/chessground.min.js";
import { icon } from "/static/labels.js";

// "e2e4" -> ["e2", "e4"]
const squares = (uci) => [uci.slice(0, 2), uci.slice(2, 4)];

export class ReviewBoard {
  constructor(boardEl, iconEl, orientation) {
    this.iconEl = iconEl;
    this.orientation = orientation;
    this.cg = Chessground(boardEl, {
      viewOnly: true,
      coordinates: true,
      orientation,
      animation: { enabled: true, duration: 180 },
      highlight: { lastMove: true, check: true },
      drawable: { enabled: false, visible: true },
    });
    window.addEventListener("resize", () => this.cg.redrawAll());
  }

  setOrientation(orientation) {
    this.orientation = orientation;
    // Okretanje mora kroz toggleOrientation (set ne crta tablu iznova)
    if (this.cg.state.orientation !== orientation) this.cg.toggleOrientation();
  }

  // position: pozicija iz API-ja; move: potez koji je doveo do nje (null za početnu);
  // bestArrow: uci poteza za strelicu (ili null)
  show(position, move, { bestArrow = null, animate = true } = {}) {
    this.cg.set({
      fen: position.fen,
      turnColor: position.turn,
      check: position.check,
      lastMove: position.last_move ? squares(position.last_move) : undefined,
      animation: { enabled: animate },
    });
    if (bestArrow) {
      const [orig, dest] = squares(bestArrow);
      this.cg.setAutoShapes([{ orig, dest, brush: "green" }]);
    } else {
      this.cg.setAutoShapes([]);
    }
    this._showIcon(move);
  }

  // Ikonica oznake u gornjem desnom uglu polja na koje je figura stigla
  _showIcon(move) {
    if (!move || !move.classification) {
      this.iconEl.hidden = true;
      return;
    }
    const dest = move.uci.slice(2, 4);
    const file = dest.charCodeAt(0) - 97;
    const rank = Number(dest[1]) - 1;
    const white = this.orientation === "white";
    const x = white ? file : 7 - file;
    const y = white ? 7 - rank : rank;
    this.iconEl.style.left = `${(x + 1) * 12.5}%`;
    this.iconEl.style.top = `${y * 12.5}%`;
    this.iconEl.replaceChildren(icon(move.classification));
    this.iconEl.hidden = false;
  }
}
