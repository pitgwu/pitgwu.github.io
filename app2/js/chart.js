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
    chart = fixedChart(document.getElementById("chart"), 420);
    candle = chart.addCandlestickSeries();

    ma5  = chart.addLineSeries({ color: "#f00", lineWidth: 1 });
    ma10 = chart.addLineSeries({ color: "#0a0", lineWidth: 1 });
    ma20 = chart.addLineSeries({ color: "#00f", lineWidth: 1 });

    bbU = chart.addLineSeries({ color: "#ffa500" });
    bbM = chart.addLineSeries({ color: "#0066cc" });
    bbL = chart.addLineSeries({ color: "#008800" });

    volChart = fixedChart(document.getElementById("volume"), 100);
    volChart.timeScale().applyOptions({ visible: false });
    volSeries = volChart.addHistogramSeries({ priceFormat: { type: "volume" } });

    indChart = fixedChart(document.getElementById("indicator"), 150);
    indChart.timeScale().applyOptions({ visible: false });
    indL1 = indChart.addLineSeries({ lineWidth: 2 });
    indL2 = indChart.addLineSeries({ lineWidth: 2 });
    indHist = indChart.addHistogramSeries();
  }

  function update(shown, indicators, opt) {
    const visibleBars = opt.visibleBars || 40;

    // ✅ 1. K 線 / 成交量：只畫「已發生」
    candle.setData(shown);
    volSeries.setData(
      shown.map(c => ({ time: c.time, value: c.volume }))
    );

    // ✅ 2. 均線（與 shown 對齊）
    if (opt.showMA) {
      const closes = shown.map(c => c.close);
      ma5.setData(U.sma(closes, 5).map((v,i)=>v?{time:shown[i].time,value:v}:null).filter(Boolean));
      ma10.setData(U.sma(closes,10).map((v,i)=>v?{time:shown[i].time,value:v}:null).filter(Boolean));
      ma20.setData(U.sma(closes,20).map((v,i)=>v?{time:shown[i].time,value:v}:null).filter(Boolean));
    } else {
      ma5.setData([]); ma10.setData([]); ma20.setData([]);
    }

    // ✅ 3. 布林通道
    if (opt.showBB) {
      bbU.setData(shown.map((c,i)=>({time:c.time,value:indicators.BB.upper[i]})));
      bbM.setData(shown.map((c,i)=>({time:c.time,value:indicators.BB.mid[i]})));
      bbL.setData(shown.map((c,i)=>({time:c.time,value:indicators.BB.lower[i]})));
    } else {
      bbU.setData([]); bbM.setData([]); bbL.setData([]);
    }

    // ✅ 4. 技術指標（完全對齊）
    indL1.setData([]); indL2.setData([]); indHist.setData([]);

    if (opt.indicatorType === "kd") {
      indL1.setData(shown.map((c,i)=>({time:c.time,value:indicators.K[i]})));
      indL2.setData(shown.map((c,i)=>({time:c.time,value:indicators.D[i]})));
    }
    else if (opt.indicatorType === "rsi") {
      indL1.setData(shown.map((c,i)=>({time:c.time,value:indicators.RSI[i]})));
    }
    else if (opt.indicatorType === "macd") {
      indL1.setData(shown.map((c,i)=>({time:c.time,value:indicators.MACD[i]})));
      indL2.setData(shown.map((c,i)=>({time:c.time,value:indicators.MACDSignal[i]})));
      indHist.setData(shown.map((c,i)=>({
        time:c.time,
        value:indicators.MACDHist[i],
        color: indicators.MACDHist[i] >= 0 ? "#26a69a" : "#ff6b6b"
      })));
    }

    // ✅ 5. 固定視窗 40 根，右對齊「當下交易日」
    const start = Math.max(0, shown.length - visibleBars);
    const from = shown[start].time;
    const to   = shown[shown.length - 1].time;

    chart.timeScale().setVisibleRange({ from, to });
    volChart.timeScale().setVisibleRange({ from, to });
    indChart.timeScale().setVisibleRange({ from, to });
  }

  global.ChartManager = { init, update };
})(window);
