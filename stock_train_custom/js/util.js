// js/util.js
(function (global) {
  "use strict";

  const Util = {};

  Util.el = function (id) {
    return document.getElementById(id);
  };

  Util.formatNumber = function (v) {
    if (v == null || isNaN(v)) return "0";
    return Math.round(v).toLocaleString();
  };

  Util.closesOf = function (arr) {
    return arr.map(d => d.close);
  };

  Util.sma = function (values, period) {
    const len = values.length;
    const out = new Array(len).fill(null);
    if (len < period) return out;
    let sum = 0;
    for (let i = 0; i < len; i++) {
      sum += values[i];
      if (i >= period) sum -= values[i - period];
      if (i >= period - 1) {
        out[i] = sum / period;
      }
    }
    return out;
  };

  Util.ema = function (values, period) {
    const len = values.length;
    const out = new Array(len).fill(null);
    if (!len) return out;
    const k = 2 / (period + 1);
    let prev = values[0];
    out[0] = prev;
    for (let i = 1; i < len; i++) {
      const v = values[i];
      if (v == null) {
        out[i] = prev;
        continue;
      }
      prev = v * k + prev * (1 - k);
      out[i] = prev;
    }
    return out;
  };

  Util.rollingStd = function (values, period) {
    const len = values.length;
    const out = new Array(len).fill(null);
    if (len < period) return out;
    for (let i = period - 1; i < len; i++) {
      let sum = 0, sumSq = 0;
      for (let j = i - period + 1; j <= i; j++) {
        const v = values[j];
        sum += v;
        sumSq += v * v;
      }
      const mean = sum / period;
      const variance = (sumSq / period) - mean * mean;
      out[i] = Math.sqrt(Math.max(variance, 0));
    }
    return out;
  };

  global.Util = Util;

})(window);
