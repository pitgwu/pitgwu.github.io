// js/signals.js
// ------------------------------------------------------
// 多空訊號引擎：
//   buildSignalContext(data, indicators)
//   evaluateSignalsForAll(ctx) -> [ [ {side,name}, ... ], ... ]
// ------------------------------------------------------
(function (global) {
  "use strict";

  const Indicators = global.Indicators;
  const WM = global.PatternWM;
  const TRI = global.PatternTriangle;

  const SignalEngine = {};

  SignalEngine.buildSignalContext = function (data, preComputedIndicators) {
    const ind = preComputedIndicators || Indicators.computeAll(data);
    return { data, ind };
  };

  SignalEngine.evaluateSignalsForAll = function (ctx) {
    const { data, ind } = ctx;
    const n = data.length;

    const out = new Array(n).fill(null).map(() => []);

    for (let i = 1; i < n; i++) {
      const day  = data[i];
      const prev = data[i - 1];
      const sig  = out[i];

      const K           = ind.K[i];
      const D           = ind.D[i];
      const RSI         = ind.RSI[i];
      const MACD        = ind.MACD[i];
      const MACDSignal  = ind.MACDSignal[i];
      const MACDHist    = ind.MACDHist[i];
      const bbU         = ind.BB.upper[i];
      const bbL         = ind.BB.lower[i];

      // MA 多頭 / 空頭排列
      if (i >= 20) {
        const closes = data.slice(i - 19, i + 1).map(d => d.close);
        const ma5  = smaTail(closes, 5);
        const ma10 = smaTail(closes, 10);
        const ma20 = smaTail(closes, 20);
        if (ma5 && ma10 && ma20) {
          if (ma5 > ma10 && ma10 > ma20) {
            sig.push({ side: "bull", name: "MA 多頭排列(5>10>20)" });
          }
          if (ma5 < ma10 && ma10 < ma20) {
            sig.push({ side: "bear", name: "MA 空頭排列(5<10<20)" });
          }
        }
		
	    // 均線糾結（即將選方向）
	    if (isMACompression(i, data, ma5, ma10, ma20)) {
		   sig.push({ name: "均線糾結：即將選方向" });
        }
      }

      // MACD 金叉 / 死叉
      if (i > 1 && MACD != null && MACDSignal != null) {
        const pMACD   = ind.MACD[i - 1];
        const pSignal = ind.MACDSignal[i - 1];
        if (pMACD != null && pSignal != null) {
          if (pMACD < pSignal && MACD > MACDSignal) {
            sig.push({ side: "bull", name: "MACD 黃金交叉" });
          }
          if (pMACD > pSignal && MACD < MACDSignal) {
            sig.push({ side: "bear", name: "MACD 死亡交叉" });
          }
        }
      }

      // RSI
      if (RSI != null) {
        if (RSI > 70) {
          sig.push({ side: "bear", name: "RSI > 70 過熱區" });
        } else if (RSI < 30) {
          sig.push({ side: "bull", name: "RSI < 30 超跌區" });
        }
      }

      // BB 上下軌
      if (bbU != null && bbL != null) {
        if (day.close > bbU) {
          sig.push({ side: "bear", name: "突破 BB 上軌，短線過熱" });
        } else if (day.close < bbL) {
          sig.push({ side: "bull", name: "跌破 BB 下軌，可能超跌反彈" });
        }
      }

      // 價量
      const volUp = day.volume > prev.volume * 1.5;
      if (day.close > prev.close && volUp) {
        sig.push({ side: "bull", name: "紅 K 放量上漲" });
      }
      if (day.close < prev.close && volUp) {
        sig.push({ side: "bear", name: "綠 K 放量下殺" });
      }

      // W / M / 三角
      if (i > 40) {
        const slice = data.slice(0, i + 1);

        const w = WM.isWBottom(slice);
        if (w && w.confirmed && i >= w.p4.index) {
          sig.push({ side: "bull", name: "W 底頸線突破完成" });
        }

        const m = WM.isMTop(slice);
        if (m && m.confirmed && i >= m.p4.index) {
          sig.push({ side: "bear", name: "M 頭頸線跌破完成" });
        }

        const tri = TRI.detectTriangle(slice);
        if (tri) {
          if (MACDHist != null && MACDHist > 0) {
            sig.push({ side: "bull", name: `${tri.type} 上緣突破動能偏多` });
          } else if (MACDHist != null && MACDHist < 0) {
            sig.push({ side: "bear", name: `${tri.type} 下緣跌破動能偏空` });
          } else {
            sig.push({ side: "bull", name: `${tri.type} 收斂完成，留意突破方向` });
          }
        }
      }
	  
	  // RSI / MACD 背離 轉折提示（高階盤感）
	  if (isRSIBearDiv(i,data,RSI)) {
		 sig.push({ side: "bear", name: "高檔轉折風險升高" });
      }
 	  if (isRSIBullDiv(i,data,RSI)) {
		 sig.push({ side: "bull", name: "低檔反彈機會" });
      }

    }

    return out;
  };

  function smaTail(arr, period) {
    if (arr.length < period) return null;
    let sum = 0;
    for (let i = arr.length - period; i < arr.length; i++) sum += arr[i];
    return sum / period;
  }
  
  function isMACompression(i, data, ma5, ma10, ma20) {
    if (!ma5[i] || !ma10[i] || !ma20[i]) return false;
    const price = data[i].close;
    const max = Math.max(ma5[i], ma10[i], ma20[i]);
    const min = Math.min(ma5[i], ma10[i], ma20[i]);
    return (max - min) / price < 0.01;
  }

  function isRSIBearDiv(i, data, rsiArr) {
    if (!rsiArr || i < 5) return false;
    return data[i].high > data[i-5].high && rsiArr[i] < rsiArr[i-5];
  }

  function isRSIBullDiv(i, data, rsiArr) {
    if (!rsiArr || i < 5) return false;
    return data[i].low < data[i-5].low && rsiArr[i] > rsiArr[i-5];
  }
  
  global.SignalEngine = SignalEngine;

})(window);
