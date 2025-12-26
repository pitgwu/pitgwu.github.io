// js/supportResistance.js
// ------------------------------------------------------
// 簡易支撐/壓力偵測：近 N 日高點 / 低點的聚集區
// 回傳：[{ type: "resistance", price }, { type:"support", price }]
// ------------------------------------------------------
(function (global) {
  "use strict";

  const SR = {};

  SR.findLines = function (data, lookback) {
    const n = data.length;
    if (n < lookback) lookback = n;
    if (lookback < 10) return [];

    const slice = data.slice(n - lookback);
    const highs = slice.map(d => d.high);
    const lows = slice.map(d => d.low);

    const maxHigh = Math.max(...highs);
    const minLow = Math.min(...lows);

    const resistance = { type: "resistance", price: maxHigh };
    const support = { type: "support", price: minLow };

    return [resistance, support];
  };

  global.SupportResistance = SR;

})(window);
