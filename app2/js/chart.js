// js/chart.js
(function (global) {
  "use strict";

  const U = global.Util;

  let chart, candle;
  let volChart, volSeries;
  let indChart;

  // 主圖
  let ma5, ma10, ma20;
  let bbU, bbM, bbL;

  // 指標（分組，避免比例污染）
  let indAutoL1, indAutoL2;       // KD / RSI
  let macdL1, macdL2, macdHist;   // MACD（固定比例）

  function fixedChart(el, height) {
    return LightweightCharts.createChart(el, {
      width: el.clientWidth,
      height,
      layout: { background: { color: "#fff" }, textColor: "#222" },
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
    /* ===== 主圖 ===== */
    chart = fixedChart(document.getElementById("chart"), 420);

    candle = chart.addCandlestickSeries({
      upColor: "#ff0000",
      downColor: "#00aa00",
      borderUpColor: "#ff0000",
      borderDownColor: "#00aa00",
      wickUpColor: "#ff0000",
      wickDownColor: "#00aa00",
    });

    ma5  = chart.addLineSeries({ color: "#f00", lineWidth: 1 });
    ma10 = chart.addLineSeries({ color: "#0a0", lineWidth: 1 });
    ma20 = chart.addLineSeries({ color: "#00f", lineWidth: 1 });

    bbU = chart.addLineSeries({ color: "#ffa500" });
    bbM = chart.addLineSeries({ color: "#0066cc" });
    bbL = chart.addLineSeries({ color: "#008800" });

    /* ===== 成交量 ===== */
    volChart = fixedChart(document.getElementById("volume"), 100);
    volChart.timeScale().applyOptions({ visible: false });
    volSeries = volChart.addHistogramSeries({
      priceFormat: { type: "volume" }
    });

    /* ===== 指標區 ===== */
    indChart = fixedChart(document.getElementById("indicator"), 150);
    indChart.timeScale().applyOptions({ visible: false });

    // KD / RSI（自動比例）
    indAutoL1 = indChart.addLineSeries({ lineWidth: 2, color: "#1f77b4" });
    indAutoL2 = indChart.addLineSeries({ lineWidth: 2, color: "#aa00aa" });

    // MACD（固定比例）
    const macdScale = () => ({
      priceRange: { minValue: -5, maxValue: 5 }
    });

    macdL1 = indChart.addLineSeries({
      lineWidth: 2,
      color: "#1f77b4",
      autoscaleInfoProvider: macdScale
    });

    macdL2 = indChart.addLineSeries({
      lineWidth: 2,
      color: "#aa00aa",
      autoscaleInfoProvider: macdScale
    });

    macdHist = indChart.addHistogramSeries({
      autoscaleInfoProvider: macdScale
    });
  }

  function update(shown, indicators, opt) {
    if (!shown || !shown.length) return;
    const visibleBars = opt.visibleBars || 40;

    /* ===== K 線 / 成交量 ===== */
    candle.setData(shown);
    volSeries.setData(shown.map(c => ({ time: c.time, value: c.volume })));

    /* ===== 均線 ===== */
    if (opt.showMA) {
      const closes = shown.map(c => c.close);
      ma5.setData(U.sma(closes,5).map((v,i)=>v?{time:shown[i].time,value:v}:null).filter(Boolean));
      ma10.setData(U.sma(closes,10).map((v,i)=>v?{time:shown[i].time,value:v}:null).filter(Boolean));
      ma20.setData(U.sma(closes,20).map((v,i)=>v?{time:shown[i].time,value:v}:null).filter(Boolean));
    } else {
      ma5.setData([]); ma10.setData([]); ma20.setData([]);
    }

    /* ===== 布林通道 ===== */
    if (opt.showBB) {
      bbU.setData(shown.map((c,i)=>({time:c.time,value:indicators.BB.upper[i]})));
      bbM.setData(shown.map((c,i)=>({time:c.time,value:indicators.BB.mid[i]})));
      bbL.setData(shown.map((c,i)=>({time:c.time,value:indicators.BB.lower[i]})));
    } else {
      bbU.setData([]); bbM.setData([]); bbL.setData([]);
    }

    /* ===== 清空所有指標 ===== */
    indAutoL1.setData([]); indAutoL2.setData([]);
    macdL1.setData([]); macdL2.setData([]); macdHist.setData([]);

    /* ===== 指標切換 ===== */
    if (opt.indicatorType === "kd") {
      indAutoL1.setData(shown.map((c,i)=>({time:c.time,value:indicators.K[i]})));
      indAutoL2.setData(shown.map((c,i)=>({time:c.time,value:indicators.D[i]})));
    }
    else if (opt.indicatorType === "rsi") {
      indAutoL1.setData(shown.map((c,i)=>({time:c.time,value:indicators.RSI[i]})));
    }
    else if (opt.indicatorType === "macd") {
      macdL1.setData(shown.map((c,i)=>({time:c.time,value:indicators.MACD[i]})));
      macdL2.setData(shown.map((c,i)=>({time:c.time,value:indicators.MACDSignal[i]})));
      macdHist.setData(shown.map((c,i)=>({
        time: c.time,
        value: indicators.MACDHist[i],
        color: indicators.MACDHist[i] >= 0 ? "#26a69a" : "#ff6b6b"
      })));
    }

    /* ===== 固定視窗 ===== */
    const start = Math.max(0, shown.length - visibleBars);
    const from = shown[start].time;
    const to   = shown[shown.length - 1].time;

    chart.timeScale().setVisibleRange({ from, to });
    volChart.timeScale().setVisibleRange({ from, to });
    indChart.timeScale().setVisibleRange({ from, to });
  }

  global.ChartManager = { init, update };
})(window);
