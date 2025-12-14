// js/patternTriangle.js
// ------------------------------------------------------
// 三角收斂基本偵測：
// 觀察最近一段 pivot high / low，若上緣下降、下緣上升 → 收斂三角
// 回傳：{ type, upperLine:{p1,p2}, lowerLine:{p1,p2} } | null
// ------------------------------------------------------
(function (global) {
  "use strict";

  const TRI = {};

  function findPivots(data, window = 3) {
    const highs = data.map(d => d.high);
    const lows = data.map(d => d.low);
    const ph = [];
    const pl = [];
    for (let i = window; i < data.length - window; i++) {
      const h = highs[i];
      const l = lows[i];
      let isH = true;
      let isL = true;
      for (let k = i - window; k <= i + window; k++) {
        if (highs[k] > h) isH = false;
        if (lows[k] < l) isL = false;
      }
      if (isH) ph.push({ index: i, price: h });
      if (isL) pl.push({ index: i, price: l });
    }
    return { ph, pl };
  }

  TRI.detectTriangle = function (data) {
    if (!data || data.length < 40) return null;

    const { ph, pl } = findPivots(data, 3);
    if (ph.length < 2 || pl.length < 2) return null;

    const top1 = ph[ph.length - 2];
    const top2 = ph[ph.length - 1];
    const bot1 = pl[pl.length - 2];
    const bot2 = pl[pl.length - 1];

    const upSlope = (top2.price - top1.price) / (top2.index - top1.index);
    const lowSlope = (bot2.price - bot1.price) / (bot2.index - bot1.index);

    let type = null;

    if (upSlope < 0 && lowSlope > 0) {
      type = "收斂三角形";
    } else if (Math.abs(upSlope) < 0.02 && lowSlope > 0) {
      type = "上升三角形";
    } else if (upSlope < 0 && Math.abs(lowSlope) < 0.02) {
      type = "下降三角形";
    } else {
      return null;
    }

    return {
      type,
      upperLine: { p1: top1, p2: top2 },
      lowerLine: { p1: bot1, p2: bot2 },
    };
  };

  global.PatternTriangle = TRI;

})(window);
