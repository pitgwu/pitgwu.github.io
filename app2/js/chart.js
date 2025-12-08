// js/chart.js
// -------------------------------------------------------------
// ✔ K 線右側對齊 + 每次更新貼齊右邊
// ✔ 不可用滑鼠縮放 / 不可左右拖拉
// ✔ MA / BB / 趨勢線 / 支撐壓力 / W 底 / 三角 收斂畫線
// ✔ 成交量 / 指標圖與主圖 timeScale 完全同步
// -------------------------------------------------------------
(function (global) {
  "use strict";

  const U   = global.Util;
  const WM  = global.PatternWM;
  const TRI = global.PatternTriangle;

  let chart, candleSeries;
  let volChart, volSeries;
  let indChart, line1, line2, histSeries;

  let ma5Series, ma10Series, ma20Series;
  let bbUpperSeries, bbMidSeries, bbLowerSeries;

  let resLine, supLine;
  let trendLineUp, trendLineDown;

  let wLine1, wLine2, wNeckLine;
  let triLine1, triLine2;

  let chartEl, volEl, indEl;

  function fixedChartConfig(el, height) {
    return LightweightCharts.createChart(el, {
      width: el.clientWidth,
      height,
      layout: { background: { color: "#ffffff" }, textColor: "#222" },

      rightPriceScale: {
        borderColor: "#ccc",
        autoScale: true,
      },

      timeScale: {
        borderColor: "#ccc",
        timeVisible: true,
        fixLeftEdge: true,
        fixRightEdge: false,
        rightBarStaysOnScroll: true,
        scrollEnabled: false,
        zoomEnabled: false,
        barSpacing: 8,
      },

      handleScroll: {
        mouseWheel: false,
        pressedMouseMove: false,
        horzTouchDrag: false,
        vertTouchDrag: false,
      },
      handleScale: {
        axisPressedMouseMove: false,
        mouseWheel: false,
        pinch: false,
      },
    });
  }

  function initMainChart() {
    chartEl = document.getElementById("chart");
    chart   = fixedChartConfig(chartEl, 420);

    candleSeries = chart.addCandlestickSeries({
      upColor: "#ff0000",
      downColor: "#00aa00",
      borderUpColor: "#ff0000",
      borderDownColor: "#00aa00",
      wickUpColor: "#ff0000",
      wickDownColor: "#00aa00",
    });

    const noScale = () => ({ priceRange: null });

    ma5Series = chart.addLineSeries({
      color: "#ff0000",
      lineWidth: 1,
      priceLineVisible: false,
      autoscaleInfoProvider: noScale,
    });
    ma10Series = chart.addLineSeries({
      color: "#00aa00",
      lineWidth: 1,
      priceLineVisible: false,
      autoscaleInfoProvider: noScale,
    });
    ma20Series = chart.addLineSeries({
      color: "#0000ff",
      lineWidth: 1,
      priceLineVisible: false,
      autoscaleInfoProvider: noScale,
    });

    bbUpperSeries = chart.addLineSeries({
      color: "#ffa500",
      lineWidth: 1,
      autoscaleInfoProvider: noScale,
    });
    bbMidSeries = chart.addLineSeries({
      color: "#0066cc",
      lineWidth: 1,
      autoscaleInfoProvider: noScale,
    });
    bbLowerSeries = chart.addLineSeries({
      color: "#008800",
      lineWidth: 1,
      autoscaleInfoProvider: noScale,
    });

    resLine = chart.addLineSeries({
      color: "#ff4444",
      lineWidth: 1,
      priceLineVisible: false,
    });
    supLine = chart.addLineSeries({
      color: "#44aa44",
      lineWidth: 1,
      priceLineVisible: false,
    });

    trendLineUp = chart.addLineSeries({
      color: "#00aa88",
      lineWidth: 2,
      priceLineVisible: false,
      autoscaleInfoProvider: noScale,
    });
    trendLineDown = chart.addLineSeries({
      color: "#aa0044",
      lineWidth: 2,
      priceLineVisible: false,
      autoscaleInfoProvider: noScale,
    });

    wLine1 = chart.addLineSeries({
      color: "#0066ff",
      lineWidth: 2,
      priceLineVisible: false,
      autoscaleInfoProvider: noScale,
    });
    wLine2 = chart.addLineSeries({
      color: "#0066ff",
      lineWidth: 2,
      priceLineVisible: false,
      autoscaleInfoProvider: noScale,
    });
    wNeckLine = chart.addLineSeries({
      color: "#ff8800",
      lineWidth: 1,
      priceLineVisible: false,
      autoscaleInfoProvider: noScale,
    });

    triLine1 = chart.addLineSeries({
      color: "#9933ff",
      lineWidth: 2,
      priceLineVisible: false,
      autoscaleInfoProvider: noScale,
    });
    triLine2 = chart.addLineSeries({
      color: "#9933ff",
      lineWidth: 2,
      priceLineVisible: false,
      autoscaleInfoProvider: noScale,
    });
  }

  function initVolumeChart() {
    volEl = document.getElementById("volume");
    volChart = fixedChartConfig(volEl, 100);
    volChart.applyOptions({ timeScale: { visible: false } });

    volSeries = volChart.addHistogramSeries({
      color: "#a3c4ff",
      priceFormat: { type: "volume" },
    });
  }

  function initIndicatorChart() {
    indEl = document.getElementById("indicator");
    indChart = fixedChartConfig(indEl, 150);
    indChart.applyOptions({ timeScale: { visible: false } });

    line1 = indChart.addLineSeries({
      color: "#1f77b4",
      lineWidth: 2,
    });
    line2 = indChart.addLineSeries({
      color: "#aa00aa",
      lineWidth: 2,
    });
    histSeries = indChart.addHistogramSeries({
      priceFormat: { type: "volume" },
    });
  }

  function bindResize() {
    window.addEventListener("resize", () => {
      if (!chart || !volChart || !indChart) return;
      chart.resize(chartEl.clientWidth, 420);
      volChart.resize(volEl.clientWidth, 100);
      indChart.resize(indEl.clientWidth, 150);
    });
  }

  function scrollToRight(shownLen) {
    if (!chart) return;
    if (shownLen < 10) return;
    chart.timeScale().scrollToPosition(-1, true);
  }

  function update(shown, ind, opt = {}) {
    if (!shown || !shown.length) return;

    const cdl = shown.map(d => ({
      time: d.time,
      open: d.open,
      high: d.high,
      low:  d.low,
      close:d.close,
    }));
    candleSeries.setData(cdl);

    volSeries.setData(shown.map(d => ({ time: d.time, value: d.volume })));

    const closes = U.closesOf(shown);

    // MA
    if (opt.showMA) {
      const ma5  = U.sma(closes, 5);
      const ma10 = U.sma(closes, 10);
      const ma20 = U.sma(closes, 20);
      ma5Series.setData(shown.map((d, i) => ({ time: d.time, value: ma5[i] })));
      ma10Series.setData(shown.map((d, i) => ({ time: d.time, value: ma10[i] })));
      ma20Series.setData(shown.map((d, i) => ({ time: d.time, value: ma20[i] })));
    } else {
      ma5Series.setData([]);
      ma10Series.setData([]);
      ma20Series.setData([]);
    }

    // BB
    if (opt.showBB && ind && ind.BB) {
      bbUpperSeries.setData(shown.map((d, i) => ({ time: d.time, value: ind.BB.upper[i] })));
      bbMidSeries.setData(shown.map((d, i) => ({ time: d.time, value: ind.BB.mid[i] })));
      bbLowerSeries.setData(shown.map((d, i) => ({ time: d.time, value: ind.BB.lower[i] })));
    } else {
      bbUpperSeries.setData([]);
      bbMidSeries.setData([]);
      bbLowerSeries.setData([]);
    }

    // 指標圖
    line1.setData([]);
    line2.setData([]);
    histSeries.setData([]);

    if (ind && opt.indicatorType) {
      switch (opt.indicatorType) {
        case "kd":
          line1.setData(shown.map((d, i) => ({ time: d.time, value: ind.K[i] })));
          line2.setData(shown.map((d, i) => ({ time: d.time, value: ind.D[i] })));
          break;

        case "rsi":
          line1.setData(shown.map((d, i) => ({ time: d.time, value: ind.RSI[i] })));
          break;

        case "macd":
          line1.setData(shown.map((d, i) => ({ time: d.time, value: ind.MACD[i] })));
          line2.setData(shown.map((d, i) => ({ time: d.time, value: ind.MACDSignal[i] })));
          histSeries.setData(
            shown.map((d, i) => ({
              time: d.time,
              value: ind.MACDHist[i],
              color: ind.MACDHist[i] >= 0 ? "#26a69a" : "#ff6b6b",
            }))
          );
          break;
      }
    }

    // 支撐壓力線
    const sr = global.SupportResistance.findLines(shown, 20);
    const last = shown[shown.length - 1];

    const res = sr[0] && sr[0].price ? sr[0].price : null;
    const sup = sr[1] && sr[1].price ? sr[1].price : null;

    resLine.setData(res != null ? [{ time: last.time, value: res }] : []);
    supLine.setData(sup != null ? [{ time: last.time, value: sup }] : []);

    // 趨勢線
    trendLineUp.setData([]);
    trendLineDown.setData([]);

    if (opt.trendlines && opt.trendlines.upLines && opt.trendlines.downLines) {
      const upLines = opt.trendlines.upLines;
      const downLines = opt.trendlines.downLines;

      if (upLines.length) {
        const u = upLines[upLines.length - 1];
        if (shown[u.p1.index] && shown[u.p2.index]) {
          trendLineUp.setData([
            { time: shown[u.p1.index].time, value: u.p1.price },
            { time: shown[u.p2.index].time, value: u.p2.price },
          ]);
        }
      }
      if (downLines.length) {
        const d = downLines[downLines.length - 1];
        if (shown[d.p1.index] && shown[d.p2.index]) {
          trendLineDown.setData([
            { time: shown[d.p1.index].time, value: d.p1.price },
            { time: shown[d.p2.index].time, value: d.p2.price },
          ]);
        }
      }
    }

    // W 底畫線（跟 MA 開關一起）
    wLine1.setData([]);
    wLine2.setData([]);
    wNeckLine.setData([]);

    const w = WM.isWBottom(shown);
    if (opt.showMA && w) {
      const p1 = w.p1.index;
      const p2 = w.p2.index;
      const p3 = w.p3.index;
      const p4 = w.p4.index;
      if (shown[p1] && shown[p2]) {
        wLine1.setData([
          { time: shown[p1].time, value: shown[p1].low },
          { time: shown[p2].time, value: shown[p2].low },
        ]);
      }
      if (shown[p3] && shown[p4]) {
        wLine2.setData([
          { time: shown[p3].time, value: shown[p3].low },
          { time: shown[p4].time, value: shown[p4].low },
        ]);
      }
      if (shown[p1] && shown[p4]) {
        wNeckLine.setData([
          { time: shown[p1].time, value: w.neck },
          { time: shown[p4].time, value: w.neck },
        ]);
      }
    }

    // 三角收斂畫線（跟 MA 開關一起）
    triLine1.setData([]);
    triLine2.setData([]);

    const tri = TRI.detectTriangle(shown);
    if (opt.showMA && tri) {
      const up1 = tri.upperLine.p1.index;
      const up2 = tri.upperLine.p2.index;
      const lo1 = tri.lowerLine.p1.index;
      const lo2 = tri.lowerLine.p2.index;

      if (shown[up1] && shown[up2]) {
        triLine1.setData([
          { time: shown[up1].time, value: tri.upperLine.p1.price },
          { time: shown[up2].time, value: tri.upperLine.p2.price },
        ]);
      }
      if (shown[lo1] && shown[lo2]) {
        triLine2.setData([
          { time: shown[lo1].time, value: tri.lowerLine.p1.price },
          { time: shown[lo2].time, value: tri.lowerLine.p2.price },
        ]);
      }
    }

    // 主圖右側對齊
    scrollToRight(shown.length);

    // ★ 同步 visibleRange 到成交量圖 & 指標圖
    const ts = chart.timeScale();
    // ---- 修正版：等待主圖渲染後再同步 ----
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const range = chart.timeScale().getVisibleRange();
        if (range) {
          volChart.timeScale().setVisibleRange(range);
          indChart.timeScale().setVisibleRange(range);
        }
      });
    });
  }

  function init() {
    initMainChart();
    initVolumeChart();
    initIndicatorChart();
    bindResize();
  }

  global.ChartManager = { init, update };

})(window);
