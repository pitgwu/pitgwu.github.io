// js/chart.js
// 盤感訓練專用 K 線 Chart Manager
(function (global) {
  "use strict";

  const U = global.Util;

  let chart, candle;
  let volChart, volSeries;
  let indChart, indL1, indL2, indHist;

  let ma5, ma10, ma20;
  let bbU, bbM, bbL;

  let resLine, supLine;
  let trendUp, trendDn;

  let wLine1, wLine2, wNeck;
  let triUp, triLow;

  function fixedChartConfig(el, height) {
    return LightweightCharts.createChart(el, {
      width: el.clientWidth,
      height,

      layout: {
        background: { color: "#ffffff" },
        textColor: "#222"
      },

      rightPriceScale: {
        borderColor: "#ccc",
        autoScale: true,
      },

      timeScale: {
        borderColor: "#ccc",
        timeVisible: true,
        barSpacing: 8,
        fixLeftEdge: true,
        fixRightEdge: true,
        rightBarStaysOnScroll: true,

        scrollEnabled: false,
        zoomEnabled: false,
        shiftVisibleRangeOnResize: false,
      },

      handleScroll: {
        mouseWheel: false,
        pressedMouseMove: false,
      },

      handleScale: {
        mouseWheel: false,
        axisPressedMouseMove: false,
        pinch: false,
      },
    });
  }

  function initMain() {
    const el = document.getElementById("chart");
    chart = fixedChartConfig(el, 420);

    candle = chart.addCandlestickSeries({
      upColor: "#ff0000",
      downColor: "#00aa00",
      borderUpColor: "#ff0000",
      borderDownColor: "#00aa00",
      wickUpColor: "#ff0000",
      wickDownColor: "#00aa00",
    });

    const noScale = () => ({ priceRange: null });

    ma5  = chart.addLineSeries({ color:"#f00",    lineWidth:1, autoscaleInfoProvider:noScale });
    ma10 = chart.addLineSeries({ color:"#0a0",    lineWidth:1, autoscaleInfoProvider:noScale });
    ma20 = chart.addLineSeries({ color:"#00f",    lineWidth:1, autoscaleInfoProvider:noScale });

    bbU  = chart.addLineSeries({ color:"#ffa500", autoscaleInfoProvider:noScale });
    bbM  = chart.addLineSeries({ color:"#0066cc", autoscaleInfoProvider:noScale });
    bbL  = chart.addLineSeries({ color:"#008800", autoscaleInfoProvider:noScale });

    resLine  = chart.addLineSeries({ color:"#dd4444", lineWidth:1 });
    supLine  = chart.addLineSeries({ color:"#44aa44", lineWidth:1 });

    trendUp  = chart.addLineSeries({ color:"#00aa88", lineWidth:2 });
    trendDn  = chart.addLineSeries({ color:"#aa0044", lineWidth:2 });

    triUp    = chart.addLineSeries({ color:"#aa6600", lineWidth:1 });
    triLow   = chart.addLineSeries({ color:"#5588ff", lineWidth:1 });

    wLine1   = chart.addLineSeries({ color:"#cc00cc", lineWidth:1 });
    wLine2   = chart.addLineSeries({ color:"#cc00cc", lineWidth:1 });
    wNeck    = chart.addLineSeries({ color:"#cc00cc", lineWidth:1 });
  }

  function initVolume() {
    const el = document.getElementById("volume");
    volChart = fixedChartConfig(el, 100);
    volChart.timeScale().applyOptions({ visible:false });

    volSeries = volChart.addHistogramSeries({
      color:"#a3c4ff",
      priceFormat:{ type:"volume" },
    });
  }

  function initIndicator() {
    const el = document.getElementById("indicator");
    indChart = fixedChartConfig(el, 150);
    indChart.timeScale().applyOptions({ visible:false });

    indL1 = indChart.addLineSeries({ color:"#1f77b4", lineWidth:2 });
    indL2 = indChart.addLineSeries({ color:"#aa00aa", lineWidth:2 });
    indHist = indChart.addHistogramSeries({
      priceFormat:{ type:"volume" }
    });
  }

  function update(shown, ind, opt) {
    if (!shown || !shown.length) return;

    const closes = U.closesOf(shown);

    candle.setData(shown);
    volSeries.setData(shown.map(c => ({ time:c.time, value:c.volume })));

    // MA
    if (opt.showMA) {
      const m5  = U.sma(closes,5);
      const m10 = U.sma(closes,10);
      const m20 = U.sma(closes,20);

      ma5.setData (shown.map((c,i)=>({time:c.time,value:m5[i]})));
      ma10.setData(shown.map((c,i)=>({time:c.time,value:m10[i]})));
      ma20.setData(shown.map((c,i)=>({time:c.time,value:m20[i]})));
    } else {
      ma5.setData([]); ma10.setData([]); ma20.setData([]);
    }

    // Bollinger
    if (opt.showBB) {
      bbU.setData(shown.map((c,i)=>({time:c.time,value:ind.BB.upper[i]})));
      bbM.setData(shown.map((c,i)=>({time:c.time,value:ind.BB.mid[i]})));
      bbL.setData(shown.map((c,i)=>({time:c.time,value:ind.BB.lower[i]})));
    } else {
      bbU.setData([]); bbM.setData([]); bbL.setData([]);
    }

    // KD / RSI / MACD
    indL1.setData([]); indL2.setData([]); indHist.setData([]);

    if (opt.indicatorType === "kd") {
      indL1.setData(shown.map((c,i)=>({time:c.time,value:ind.K[i]})));
      indL2.setData(shown.map((c,i)=>({time:c.time,value:ind.D[i]})));
    }
    else if (opt.indicatorType === "rsi") {
      indL1.setData(shown.map((c,i)=>({time:c.time,value:ind.RSI[i]})));
    }
    else if (opt.indicatorType === "macd") {
      indL1.setData(shown.map((c,i)=>({time:c.time,value:ind.MACD[i]})));
      indL2.setData(shown.map((c,i)=>({time:c.time,value:ind.MACDSignal[i]})));
      indHist.setData(shown.map((c,i)=>({
        time:c.time,
        value:ind.MACDHist[i],
        color: ind.MACDHist[i] >= 0 ? "#26a69a" : "#ff6b6b"
      })));
    }

    // 支撐壓力
    const SR = global.SupportResistance.findLines(shown, 20);
    const lastT = shown[shown.length - 1].time;

    resLine.setData(SR[0] ? [{ time:lastT, value:SR[0].price }] : []);
    supLine.setData(SR[1] ? [{ time:lastT, value:SR[1].price }] : []);

    // 趨勢線
    trendUp.setData([]);
    trendDn.setData([]);

    if (opt.showMA && opt.trendlines) {
      const { upLines, downLines } = opt.trendlines;

      if (upLines?.length) {
        const u = upLines[upLines.length - 1];
        trendUp.setData([
          { time: shown[u.p1.index].time, value: u.p1.price },
          { time: shown[u.p2.index].time, value: u.p2.price },
        ]);
      }

      if (downLines?.length) {
        const d = downLines[downLines.length - 1];
        trendDn.setData([
          { time: shown[d.p1.index].time, value: d.p1.price },
          { time: shown[d.p2.index].time, value: d.p2.price },
        ]);
      }
    }

    // 三角收斂
    triUp.setData([]);
    triLow.setData([]);

    if (opt.showMA && opt.triangle) {
      const T = opt.triangle;
      triUp.setData([
        { time: shown[T.upperLine.p1.index].time, value: T.upperLine.p1.price },
        { time: shown[T.upperLine.p2.index].time, value: T.upperLine.p2.price },
      ]);
      triLow.setData([
        { time: shown[T.lowerLine.p1.index].time, value: T.lowerLine.p1.price },
        { time: shown[T.lowerLine.p2.index].time, value: T.lowerLine.p2.price },
      ]);
    }

    // W 底
    wLine1.setData([]);
    wLine2.setData([]);
    wNeck.setData([]);

    if (opt.showMA && opt.wPattern) {
      const W = opt.wPattern;

      wLine1.setData([
        { time: shown[W.p1.index].time, value: W.p1.price },
        { time: shown[W.p2.index].time, value: W.p2.price },
      ]);

      wLine2.setData([
        { time: shown[W.p3.index].time, value: W.p3.price },
        { time: shown[W.p4.index].time, value: W.p4.price },
      ]);

      const lastT2 = shown[shown.length - 1].time;
      wNeck.setData([
        { time: shown[W.p1.index].time, value: W.neck },
        { time: lastT2, value: W.neck },
      ]);
    }

    // ★ 每次更新都貼齊右側（含三張圖）
    requestAnimationFrame(() => {
      chart.timeScale().scrollToPosition(-1, false);
      volChart.timeScale().scrollToPosition(-1, false);
      indChart.timeScale().scrollToPosition(-1, false);
    });
  }

  function init() {
    initMain();
    initVolume();
    initIndicator();
  }

  global.ChartManager = { init, update };

})(window);
