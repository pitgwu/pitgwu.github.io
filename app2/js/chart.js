// js/chart.js
(function (global) {
  "use strict";

  const U = global.Util;

  let chart, candle;
  let volChart, volSeries;
  let indChart, indL1, indL2, indHist;

  let ma5, ma10, ma20;
  let bbU, bbM, bbL;

  function fixedChart(el, height) {
    return LightweightCharts.createChart(el, {
      width: el.clientWidth,
      height,
      layout: {
        background: { color: "#ffffff" },
        textColor: "#222"
      },
      rightPriceScale: { autoScale: true },
      timeScale: {
        timeVisible: true,
        barSpacing: 8,
        rightBarStaysOnScroll: true,
        scrollEnabled: false,
        zoomEnabled: false,
      },
      handleScroll: false,
      handleScale: false,
    });
  }

  function init() {
    // ===== K 線 =====
    chart = fixedChart(document.getElementById("chart"), 420);

    candle = chart.addCandlestickSeries({
      upColor: "#ff0000",        // 漲紅
      downColor: "#00aa00",      // 跌綠
      borderUpColor: "#ff0000",
      borderDownColor: "#00aa00",
      wickUpColor: "#ff0000",
      wickDownColor: "#00aa00",
    });

    // ===== 均線 =====
    ma5  = chart.addLineSeries({ color: "#f00", lineWidth: 1 });
    ma10 = chart.addLineSeries({ color: "#0a0", lineWidth: 1 });
    ma20 = chart.addLineSeries({ color: "#00f", lineWidth: 1 });

    // ===== 布林通道 =====
    bbU = chart.addLineSeries({ color: "#ffa500" });
    bbM = chart.addLineSeries({ color: "#0066cc" });
    bbL = chart.addLineSeries({ color: "#008800" });

    // ===== 成交量 =====
    volChart = fixedChart(document.getElementById("volume"), 100);
    volChart.timeScale().applyOptions({ visible: false });

    volSeries = volChart.addHistogramSeries({
      priceFormat: { type: "volume" },
      color: "#90b7ff",
    });

    // ===== 技術指標 =====
    indChart = fixedChart(document.getElementById("indicator"), 150);
    indChart.timeScale().applyOptions({ visible: false });

    // 固定比例，避免 MACD ON / OFF 跳動
    const fixedScale = () => ({
      priceRange: { minValue: -5, maxValue: 5 }
    });

    indL1 = indChart.addLineSeries({
      lineWidth: 2,
      autoscaleInfoProvider: fixedScale
    });

    indL2 = indChart.addLineSeries({
      lineWidth: 2,
      autoscaleInfoProvider: fixedScale
    });

    indHist = indChart.addHistogramSeries({
      autoscaleInfoProvider: fixedScale
    });
  }

  function update(shown, indicators, opt) {
    if (!shown || !shown.length) return;

    // === K 線 / 成交量 ===
    candle.setData(shown);
    volSeries.setData(
      shown.map(c => ({ time: c.time, value: c.volume }))
    );

    // === 均線 ===
    if (opt.showMA) {
      const closes = shown.map(c => c.close);

      ma5.setData(
        U.sma(closes, 5)
          .map((v,i)=>v ? { time: shown[i].time, value: v } : null)
          .filter(Boolean)
      );
      ma10.setData(
        U.sma(closes, 10)
          .map((v,i)=>v ? { time: shown[i].time, value: v } : null)
          .filter(Boolean)
      );
      ma20.setData(
        U.sma(closes, 20)
          .map((v,i)=>v ? { time: shown[i].time, value: v } : null)
          .filter(Boolean)
      );
    } else {
      ma5.setData([]);
      ma10.setData([]);
      ma20.setData([]);
    }

    // === 布林 ===
    if (opt.showBB) {
      bbU.setData(shown.map((c,i)=>({ time:c.time, value: indicators.BB.upper[i] })));
      bbM.setData(shown.map((c,i)=>({ time:c.time, value: indicators.BB.mid[i] })));
      bbL.setData(shown.map((c,i)=>({ time:c.time, value: indicators.BB.lower[i] })));
    } else {
      bbU.setData([]);
      bbM.setData([]);
      bbL.setData([]);
    }

    // === 技術指標 ===
    indL1.setData([]);
    indL2.setData([]);
    indHist.setData([]);

    if (opt.indicatorType === "kd") {
      indL1.setData(shown.map((c,i)=>({ time:c.time, value: indicators.K[i] })));
      indL2.setData(shown.map((c,i)=>({ time:c.time, value: indicators.D[i] })));
    }
    else if (opt.indicatorType === "rsi") {
      indL1.setData(shown.map((c,i)=>({ time:c.time, value: indicators.RSI[i] })));
    }
    else if (opt.indicatorType === "macd") {
      indL1.setData(shown.map((c,i)=>({ time:c.time, value: indicators.MACD[i] })));
      indL2.setData(shown.map((c,i)=>({ time:c.time, value: indicators.MACDSignal[i] })));
      indHist.setData(shown.map((c,i)=>({
        time: c.time,
        value: indicators.MACDHist[i],
        color: indicators.MACDHist[i] >= 0 ? "#26a69a" : "#ff6b6b"
      })));
    }

    // === 右對齊 ===
    requestAnimationFrame(() => {
      chart.timeScale().scrollToPosition(-1, false);
      volChart.timeScale().scrollToPosition(-1, false);
      indChart.timeScale().scrollToPosition(-1, false);
    });
  }

  global.ChartManager = { init, update };

})(window);
