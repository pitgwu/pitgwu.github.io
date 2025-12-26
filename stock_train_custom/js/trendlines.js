// js/trendlines.js
// ------------------------------------------------------
// 自動畫趨勢線偵測（進階版）
// 只回傳最近一組較具代表性的 upLines / downLines
// 格式：{ upLines: [{ p1:{index,price}, p2:{index,price} }], downLines:[...] }
// ------------------------------------------------------
(function (global) {
  "use strict";

  const Trend = {};

  function findPivots(data, window = 3) {
    const highs = data.map(d => d.high);
    const lows = data.map(d => d.low);
    const pivotHighs = [];
    const pivotLows = [];

    for (let i = window; i < data.length - window; i++) {
      const h = highs[i];
      const l = lows[i];

      let isHigh = true;
      let isLow = true;

      for (let k = i - window; k <= i + window; k++) {
        if (highs[k] > h) isHigh = false;
        if (lows[k] < l) isLow = false;
        if (!isHigh && !isLow) break;
      }

      if (isHigh) pivotHighs.push({ index: i, price: h });
      if (isLow) pivotLows.push({ index: i, price: l });
    }

    return { pivotHighs, pivotLows };
  }

  function pickTrendLine(pivots, type = "up") {
    if (pivots.length < 2) return null;
    const recent = pivots.slice(-6);
    let best = null;
    let bestScore = -Infinity;

    for (let i = 0; i < recent.length - 1; i++) {
      for (let j = i + 1; j < recent.length; j++) {
        const p1 = recent[i];
        const p2 = recent[j];
        if (p2.index === p1.index) continue;

        const dx = p2.index - p1.index;
        const dy = p2.price - p1.price;
        const slope = dy / dx;

        if (type === "up" && slope <= 0) continue;
        if (type === "down" && slope >= 0) continue;

        const angle = Math.atan(slope) * 180 / Math.PI;
        if (Math.abs(angle) < 5) continue;
        if (Math.abs(angle) > 75) continue;

        const recency = p2.index;
        const span = dx;
        const score = recency * 2 + span;

        if (score > bestScore) {
          bestScore = score;
          best = { p1, p2 };
        }
      }
    }
    return best;
  }

  Trend.findTrendlines = function (data) {
    if (!data || data.length < 30) return { upLines: [], downLines: [] };

    const { pivotHighs, pivotLows } = findPivots(data, 3);

    const up = pickTrendLine(pivotLows, "up");
    const down = pickTrendLine(pivotHighs, "down");

    const upLines = up ? [up] : [];
    const downLines = down ? [down] : [];

    return { upLines, downLines };
  };

  global.Trendlines = Trend;

})(window);
