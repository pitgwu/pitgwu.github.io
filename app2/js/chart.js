// js/chart.js
(function (global) {
  "use strict";

  const U = global.Util;

  let chart, candleSeries;
  let volChart, volSeries;
  let indChart, line1, line2, histSeries;

  let ma5Series, ma10Series, ma20Series;
  let bbUpperSeries, bbMidSeries, bbLowerSeries;

  let resLine, supLine;
  let trendLineUp, trendLineDown;

  // W 底線
  let wLine1, wLine2;
  // 三角形
  let triUpLine, triLowLine;

  // -----------------------------------------------------
  function fixedCfg(el, height) {
    return LightweightCharts.createChart(el, {
      width: el.clientWidth,
      height,
      layout: { background: { color: "#fff" }, textColor: "#222" },

      rightPriceScale: { borderColor: "#ccc", autoScale: true },
      timeScale: {
        borderColor: "#ccc",
        timeVisible: true,
        barSpacing: 8,
        rightBarStaysOnScroll: true,
        scrollEnabled: false,
        zoomEnabled: false
      },
    });
  }

  // -----------------------------------------------------
  // Init 主圖
  // -----------------------------------------------------
  function initMainChart() {
    chart = fixedCfg(document.getElementById("chart"), 420);

    candleSeries = chart.addCandlestickSeries({
      upColor: "#ff0000",
      downColor: "#00aa00",
      borderUpColor: "#ff0000",
      borderDownColor: "#00aa00",
      wickUpColor: "#ff0000",
      wickDownColor: "#00aa00",
    });

    const noScale = () => ({ priceRange: null });

    ma5Series  = chart.addLineSeries({ color:"#ff0000", autoscaleInfoProvider:noScale });
    ma10Series = chart.addLineSeries({ color:"#008800", autoscaleInfoProvider:noScale });
    ma20Series = chart.addLineSeries({ color:"#0000ff", autoscaleInfoProvider:noScale });

    bbUpperSeries = chart.addLineSeries({ color:"#ffaa00", autoscaleInfoProvider:noScale });
    bbMidSeries   = chart.addLineSeries({ color:"#0066cc", autoscaleInfoProvider:noScale });
    bbLowerSeries = chart.addLineSeries({ color:"#00aa00", autoscaleInfoProvider:noScale });

    resLine = chart.addLineSeries({ color:"#ff4444", lineWidth:1 });
    supLine = chart.addLineSeries({ color:"#44aa44", lineWidth:1 });

    trendLineUp   = chart.addLineSeries({ color:"#00aa88", lineWidth:2 });
    trendLineDown = chart.addLineSeries({ color:"#aa0044", lineWidth:2 });

    wLine1 = chart.addLineSeries({ color:"#aa33ff", lineWidth:2 });
    wLine2 = chart.addLineSeries({ color:"#aa33ff", lineWidth:2 });

    triUpLine = chart.addLineSeries({ color:"#3333ff", lineWidth:2 });
    triLowLine = chart.addLineSeries({ color:"#ff33aa", lineWidth:2 });
  }

  function initVolumeChart() {
    volChart = fixedCfg(document.getElementById("volume"), 100);
    volChart.applyOptions({ timeScale: { visible: false } });

    volSeries = volChart.addHistogramSeries({
      color: "#a3c4ff",
      priceFormat: { type: "volume" },
    });
  }

  function initIndicatorChart() {
    indChart = fixedCfg(document.getElementById("indicator"), 150);
    indChart.applyOptions({ timeScale: { visible: false } });

    line1 = indChart.addLineSeries({ color:"#1f77b4", lineWidth:2 });
    line2 = indChart.addLineSeries({ color:"#aa00aa", lineWidth:2 });
    histSeries = indChart.addHistogramSeries({});
  }

  // -----------------------------------------------------
  // 右側自動貼齊
  // -----------------------------------------------------
  function scrollToRightAnimated() {
    const ts = chart.timeScale();
    ts.scrollToPosition(-1, true);
  }

  // -----------------------------------------------------
  // 3 份圖同步對齊
  // -----------------------------------------------------
  function syncTimeScale() {
    const mainTS = chart.timeScale();
    const vis = mainTS.getVisibleRange();
    if (!vis) return;

    volChart.timeScale().setVisibleRange(vis);
    indChart.timeScale().setVisibleRange(vis);
  }

  // -----------------------------------------------------
  // 主更新
  // -----------------------------------------------------
  function update(shown, indicators, opt = {}) {

    candleSeries.setData(shown);
    volSeries.setData(shown.map(c => ({ time:c.time, value:c.volume })));

    const closes = U.closesOf(shown);

    // ================= MA =================
    if (opt.showMA) {
      const ma5 = U.sma(closes,5);
      const ma10 = U.sma(closes,10);
      const ma20 = U.sma(closes,20);

      ma5Series.setData(shown.map((c,i)=>({time:c.time,value:ma5[i]})));
      ma10Series.setData(shown.map((c,i)=>({time:c.time,value:ma10[i]})));
      ma20Series.setData(shown.map((c,i)=>({time:c.time,value:ma20[i]})));
    } else {
      // MA OFF → 清全部
      ma5Series.setData([]);
      ma10Series.setData([]);
      ma20Series.setData([]);

      trendLineUp.setData([]);
      trendLineDown.setData([]);
      wLine1.setData([]);
      wLine2.setData([]);
      triUpLine.setData([]);
      triLowLine.setData([]);
    }

    // ================= BB =================
    if (opt.showBB) {
      bbUpperSeries.setData(shown.map((c,i)=>({ time:c.time, value:indicators.BB.upper[i] })));
      bbMidSeries.setData(shown.map((c,i)=>({ time:c.time, value:indicators.BB.mid[i] })));
      bbLowerSeries.setData(shown.map((c,i)=>({ time:c.time, value:indicators.BB.lower[i] })));
    } else {
      bbUpperSeries.setData([]);
      bbMidSeries.setData([]);
      bbLowerSeries.setData([]);
    }

    // ================= 指標 (KD, RSI, MACD) =================
    switch (opt.indicatorType) {
      case "kd":
        line1.setData(shown.map((c,i)=>({time:c.time,value:indicators.K[i]})));
        line2.setData(shown.map((c,i)=>({time:c.time,value:indicators.D[i]})));
        histSeries.setData([]);
        break;
      case "rsi":
        line1.setData(shown.map((c,i)=>({time:c.time,value:indicators.RSI[i]})));
        line2.setData([]);
        histSeries.setData([]);
        break;
      case "macd":
        line1.setData(shown.map((c,i)=>({time:c.time,value:indicators.MACD[i]})));
        line2.setData(shown.map((c,i)=>({time:c.time,value:indicators.MACDSignal[i]})));
        histSeries.setData(shown.map((c,i)=>({
          time:c.time,
          value: indicators.MACDHist[i],
          color: indicators.MACDHist[i]>=0 ? "#26a69a" : "#ff6b6b"
        })));
        break;
    }

    // ================= 支撐壓力 =================
    const lines = global.SupportResistance.findLines(shown, 20);
    const last = shown[shown.length-1].time;

    resLine.setData(lines[0]?[{time:last,value:lines[0].price}]:[]);
    supLine.setData(lines[1]?[{time:last,value:lines[1].price}]:[]);

    // ================= 趨勢線 =================
    trendLineUp.setData([]);
    trendLineDown.setData([]);

    if (opt.trendlines && opt.showMA) {
      const up = opt.trendlines.upLines;
      const down = opt.trendlines.downLines;

      if (up?.length) {
        const u = up[up.length-1];
        trendLineUp.setData([
          {time: shown[u.p1.index].time, value: u.p1.price},
          {time: shown[u.p2.index].time, value: u.p2.price},
        ]);
      }
      if (down?.length) {
        const d = down[down.length-1];
        trendLineDown.setData([
          {time: shown[d.p1.index].time, value: d.p1.price},
          {time: shown[d.p2.index].time, value: d.p2.price},
        ]);
      }
    }

    // ================= W 底畫線 =================
    wLine1.setData([]);
    wLine2.setData([]);
    if (opt.wPattern && opt.showMA) {
      const w = opt.wPattern;

      wLine1.setData([
        {time: shown[w.p1.index].time, value: w.p1.price},
        {time: shown[w.p2.index].time, value: w.p2.price},
      ]);
      wLine2.setData([
        {time: shown[w.p3.index].time, value: w.p3.price},
        {time: shown[w.p4.index].time, value: w.p4.price},
      ]);
    }

    // ================= 三角收斂 =================
    triUpLine.setData([]);
    triLowLine.setData([]);
    if (opt.triangle && opt.showMA) {
      const t = opt.triangle;

      triUpLine.setData([
        {time: shown[t.upperLine.p1.index].time, value: t.upperLine.p1.price},
        {time: shown[t.upperLine.p2.index].time, value: t.upperLine.p2.price}
      ]);

      triLowLine.setData([
        {time: shown[t.lowerLine.p1.index].time, value: t.lowerLine.p1.price},
        {time: shown[t.lowerLine.p2.index].time, value: t.lowerLine.p2.price}
      ]);
    }

    // === 動畫推到右側（主圖） ===
    scrollToRightAnimated();

    // === 等主圖動畫結束後 → 三份圖同步對齊 ===
    setTimeout(syncTimeScale, 30);
  }

  function init() {
    initMainChart();
    initVolumeChart();
    initIndicatorChart();
  }

  global.ChartManager = { init, update };

})(window);
