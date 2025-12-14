// js/indicators.js
// KD / RSI / MACD / BB 指標計算
(function (global) {
  "use strict";

  const U = global.Util;

  function computeKD(candles, n = 9, kPeriod = 3, dPeriod = 3) {
    const len = candles.length;
    const K = new Array(len).fill(null);
    const D = new Array(len).fill(null);
    let kPrev = 50, dPrev = 50;

    for (let i = 0; i < len; i++) {
      if (i < n - 1) {
        K[i] = kPrev;
        D[i] = dPrev;
        continue;
      }
      let low = Infinity;
      let high = -Infinity;
      for (let j = i - n + 1; j <= i; j++) {
        if (candles[j].low < low) low = candles[j].low;
        if (candles[j].high > high) high = candles[j].high;
      }
      const rsv = (high === low)
        ? 50
        : ((candles[i].close - low) / (high - low)) * 100;

      kPrev = (kPrev * (kPeriod - 1) + rsv) / kPeriod;
      dPrev = (dPrev * (dPeriod - 1) + kPrev) / dPeriod;

      K[i] = kPrev;
      D[i] = dPrev;
    }
    return { K, D };
  }

  function computeRSI(candles, period = 14) {
    const closes = U.closesOf(candles);
    const len = closes.length;
    const RSI = new Array(len).fill(50);
    if (len <= period) return RSI;

    let gain = 0, loss = 0;
    for (let i = 1; i <= period; i++) {
      const diff = closes[i] - closes[i - 1];
      if (diff > 0) gain += diff;
      else loss -= diff;
    }
    let avgGain = gain / period;
    let avgLoss = loss / period;

    RSI[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);

    for (let i = period + 1; i < len; i++) {
      const diff = closes[i] - closes[i - 1];
      const up = diff > 0 ? diff : 0;
      const down = diff < 0 ? -diff : 0;

      avgGain = (avgGain * (period - 1) + up) / period;
      avgLoss = (avgLoss * (period - 1) + down) / period;

      if (avgLoss === 0) RSI[i] = 100;
      else {
        const rs = avgGain / avgLoss;
        RSI[i] = 100 - 100 / (1 + rs);
      }
    }
    return RSI;
  }

  function computeMACD(candles, fast = 12, slow = 26, signalPeriod = 9) {
    const closes = U.closesOf(candles);
    const emaFast = U.ema(closes, fast);
    const emaSlow = U.ema(closes, slow);

    const MACD = closes.map((_, i) =>
      emaFast[i] != null && emaSlow[i] != null
        ? emaFast[i] - emaSlow[i]
        : null
    );
    const MACDSignal = U.ema(MACD, signalPeriod);
    const MACDHist = MACD.map((v, i) =>
      v != null && MACDSignal[i] != null ? v - MACDSignal[i] : null
    );

    return { MACD, MACDSignal, MACDHist };
  }

  function computeBB(candles, period = 20, mult = 2) {
    const closes = U.closesOf(candles);
    const mid = U.sma(closes, period);
    const std = U.rollingStd(closes, period);

    const upper = new Array(closes.length).fill(null);
    const lower = new Array(closes.length).fill(null);

    for (let i = 0; i < closes.length; i++) {
      if (mid[i] != null && std[i] != null) {
        upper[i] = mid[i] + std[i] * mult;
        lower[i] = mid[i] - std[i] * mult;
      }
    }
    return { upper, mid, lower };
  }

  function computeAll(candles) {
    const KD = computeKD(candles);
    const RSI = computeRSI(candles);
    const MACD = computeMACD(candles);
    const BB = computeBB(candles);

    return {
      K: KD.K,
      D: KD.D,
      RSI,
      MACD: MACD.MACD,
      MACDSignal: MACD.MACDSignal,
      MACDHist: MACD.MACDHist,
      BB,
    };
  }

  global.Indicators = {
    computeKD,
    computeRSI,
    computeMACD,
    computeBB,
    computeAll,
  };

})(window);
