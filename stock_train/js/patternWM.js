// js/patternWM.js
// ------------------------------------------------------
// W 底 / M 頭 型態偵測
// 回傳：
//   isWBottom(data) -> { p1,p2,p3,p4, neck, confirmed } | null
//   isMTop(data)    -> 同上
// ------------------------------------------------------
(function (global) {
  "use strict";

  const WM = {};

  function findPivotsHL(data, window = 2) {
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

  WM.isWBottom = function (data) {
    if (!data || data.length < 30) return null;

    const { pl } = findPivotsHL(data, 2);
    if (pl.length < 4) return null;

    const pivots = pl.slice(-6);
    if (pivots.length < 4) return null;
    const p1 = pivots[pivots.length - 4];
    const p2 = pivots[pivots.length - 3];
    const p3 = pivots[pivots.length - 2];
    const p4 = pivots[pivots.length - 1];

    const v1 = p1.price;
    const v3 = p3.price;
    const midHighIdx = Math.max(p1.index, p3.index) - Math.floor((Math.max(p1.index, p3.index) - Math.min(p1.index, p3.index)) / 2);
    const midHigh = data[midHighIdx].high;

    const valleyDiff = Math.abs(v1 - v3) / ((v1 + v3) / 2);
    if (valleyDiff > 0.08) return null;

    if (!(midHigh > v1 * 1.05 && midHigh > v3 * 1.05)) return null;

    const left = Math.min(p1.index, p3.index);
    const right = Math.max(p1.index, p3.index);
    let neck = -Infinity;
    for (let i = left; i <= right; i++) {
      neck = Math.max(neck, data[i].high);
    }

    const confirmed = data[data.length - 1].close > neck;

    return { p1, p2, p3, p4, neck, confirmed };
  };

  WM.isMTop = function (data) {
    if (!data || data.length < 30) return null;

    const { ph } = findPivotsHL(data, 2);
    if (ph.length < 4) return null;

    const pivots = ph.slice(-6);
    if (pivots.length < 4) return null;

    const p1 = pivots[pivots.length - 4];
    const p2 = pivots[pivots.length - 3];
    const p3 = pivots[pivots.length - 2];
    const p4 = pivots[pivots.length - 1];

    const v1 = p1.price;
    const v3 = p3.price;
    const midLowIdx = Math.max(p1.index, p3.index) - Math.floor((Math.max(p1.index, p3.index) - Math.min(p1.index, p3.index)) / 2);
    const midLow = data[midLowIdx].low;

    const peakDiff = Math.abs(v1 - v3) / ((v1 + v3) / 2);
    if (peakDiff > 0.08) return null;

    if (!(midLow < v1 * 0.95 && midLow < v3 * 0.95)) return null;

    const left = Math.min(p1.index, p3.index);
    const right = Math.max(p1.index, p3.index);
    let neck = Infinity;
    for (let i = left; i <= right; i++) {
      neck = Math.min(neck, data[i].low);
    }

    const confirmed = data[data.length - 1].close < neck;

    return { p1, p2, p3, p4, neck, confirmed };
  };

  global.PatternWM = WM;

})(window);
