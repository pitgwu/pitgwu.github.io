// js/chart.js
(function (global) {
  "use strict";

  const U = global.Util;

  let chart, candle;
  let volChart, volSeries;
  let indChart;

  // ===== 主圖 =====
  let ma5, ma10, ma20;
  let bbU, bbM, bbL;

  // 型態線
  let resLine, supLine;
  let trendUp, trendDn;
  let triUp, triLow;
  let wLine1, wLine2, wNeck;

  // ===== 指標 =====
  let indAutoL1, indAutoL2;       // KD / RSI
  let macdL1, macdL2, macdHist;   // MACD

  function fixedChart(el, height) {
    return LightweightCharts.createChart(el, {
      width: el.clientWidth,
      height,
      layout: { background: { color: "#fff" }, textColor: "#222" },

      // ✅ 正確控制價格刻度：不要用 chart.applyOptions({priceScale...})
      rightPriceScale: { autoScale: true, visible: true },
      leftPriceScale:  { visible: false },

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

    // ✅ K 線：固定用 right scale
    candle = chart.addCandlestickSeries({
      upColor: "#ff0000",
      downColor: "#00aa00",
      borderUpColor: "#ff0000",
      borderDownColor: "#00aa00",
      wickUpColor: "#ff0000",
      wickDownColor: "#00aa00",
      priceScaleId: "right"
    });

    // ✅ 均線：也固定用 right scale（避免跟 K 線不同 scale 對不準）
    ma5 = chart.addLineSeries({ color:"#f00", lineWidth:1, visible:false, priceScaleId: "right" });
    ma10 = chart.addLineSeries({ color:"#0a0", lineWidth:1, visible:false, priceScaleId: "right" });
    ma20 = chart.addLineSeries({ color:"#00f", lineWidth:1, visible:false, priceScaleId: "right" });

    // ✅ 布林通道：同樣用 right scale
    bbU = chart.addLineSeries({ color:"#ffa500", visible:false, priceScaleId: "right" });
    bbM = chart.addLineSeries({ color:"#0066cc", visible:false, priceScaleId: "right" });
    bbL = chart.addLineSeries({ color:"#008800", visible:false, priceScaleId: "right" });

    // 型態線：全部同 right scale，避免干擾/錯位
    resLine = chart.addLineSeries({ color:"#dd4444", lineWidth:1, visible:false, priceScaleId: "right" });
    supLine = chart.addLineSeries({ color:"#44aa44", lineWidth:1, visible:false, priceScaleId: "right" });

    trendUp = chart.addLineSeries({ color:"#00aa88", lineWidth:2, visible:false, priceScaleId: "right" });
    trendDn = chart.addLineSeries({ color:"#aa0044", lineWidth:2, visible:false, priceScaleId: "right" });

    triUp  = chart.addLineSeries({ color:"#aa6600", lineWidth:1, visible:false, priceScaleId: "right" });
    triLow = chart.addLineSeries({ color:"#5588ff", lineWidth:1, visible:false, priceScaleId: "right" });

    wLine1 = chart.addLineSeries({ color:"#cc00cc", lineWidth:1, visible:false, priceScaleId: "right" });
    wLine2 = chart.addLineSeries({ color:"#cc00cc", lineWidth:1, visible:false, priceScaleId: "right" });
    wNeck  = chart.addLineSeries({ color:"#cc00cc", lineWidth:1, visible:false, priceScaleId: "right" });

    /* ===== 成交量 ===== */
    volChart = fixedChart(document.getElementById("volume"), 100);
    volChart.timeScale().applyOptions({ visible: false });
    volSeries = volChart.addHistogramSeries({ priceFormat: { type: "volume" } });

    /* ===== 指標區 ===== */
    indChart = fixedChart(document.getElementById("indicator"), 150);
    indChart.timeScale().applyOptions({ visible: false });

    indAutoL1 = indChart.addLineSeries({ lineWidth: 2, color: "#1f77b4" });
    indAutoL2 = indChart.addLineSeries({ lineWidth: 2, color: "#aa00aa" });

    macdL1 = indChart.addLineSeries({ lineWidth: 2, color: "#1f77b4" });
    macdL2 = indChart.addLineSeries({ lineWidth: 2, color: "#aa00aa" });
    macdHist = indChart.addHistogramSeries({});
  }

  function setLineDataSafe(series, points, visible) {
    series.setData(points);
    series.applyOptions({ visible: !!visible });
  }

  function update(shown, indicators, opt) {
    if (!shown || !shown.length) return;

    const visibleBars = opt.visibleBars || 40;
    const indType = opt.indicatorType;

    // ===== K線/成交量 =====
    candle.setData(shown);
    volSeries.setData(shown.map(c => ({ time: c.time, value: c.volume })));

    // ===== 均線 =====
    if (opt.showMA) {
      const closes = shown.map(c => c.close);

      const ma5Pts = U.sma(closes, 5)
        .map((v,i)=> (v != null ? { time: shown[i].time, value: v } : null))
        .filter(Boolean);

      const ma10Pts = U.sma(closes, 10)
        .map((v,i)=> (v != null ? { time: shown[i].time, value: v } : null))
        .filter(Boolean);

      const ma20Pts = U.sma(closes, 20)
        .map((v,i)=> (v != null ? { time: shown[i].time, value: v } : null))
        .filter(Boolean);

      setLineDataSafe(ma5, ma5Pts, true);
      setLineDataSafe(ma10, ma10Pts, true);
      setLineDataSafe(ma20, ma20Pts, true);
    } else {
      // ✅ OFF 時不要碰 candle / scale，只隱藏均線即可
      ma5.setData([]); ma10.setData([]); ma20.setData([]);
      ma5.applyOptions({ visible:false });
      ma10.applyOptions({ visible:false });
      ma20.applyOptions({ visible:false });
    }

    // ===== 布林通道（避免前段 undefined/NaN 汙染）=====
    if (opt.showBB) {
      const u = shown.map((c,i)=> (indicators.BB.upper[i] != null ? { time:c.time, value:indicators.BB.upper[i] } : null)).filter(Boolean);
      const m = shown.map((c,i)=> (indicators.BB.mid[i]   != null ? { time:c.time, value:indicators.BB.mid[i] }   : null)).filter(Boolean);
      const l = shown.map((c,i)=> (indicators.BB.lower[i] != null ? { time:c.time, value:indicators.BB.lower[i] } : null)).filter(Boolean);

      setLineDataSafe(bbU, u, true);
      setLineDataSafe(bbM, m, true);
      setLineDataSafe(bbL, l, true);
    } else {
      bbU.setData([]); bbM.setData([]); bbL.setData([]);
      bbU.applyOptions({ visible:false });
      bbM.applyOptions({ visible:false });
      bbL.applyOptions({ visible:false });
    }

    // ===== 型態線（先清）=====
    [resLine,supLine,trendUp,trendDn,triUp,triLow,wLine1,wLine2,wNeck].forEach(s=>{
      s.setData([]);
      s.applyOptions({ visible:false });
    });

    if (opt.showMA) {
      // 支撐壓力
      if (global.SupportResistance?.findLines) {
        const SR = global.SupportResistance.findLines(shown, 20);
        const t = shown[shown.length - 1].time;
        if (SR[0]) { resLine.setData([{ time:t, value:SR[0].price }]); resLine.applyOptions({ visible:true }); }
        if (SR[1]) { supLine.setData([{ time:t, value:SR[1].price }]); supLine.applyOptions({ visible:true }); }
      }

      // 趨勢線
      if (opt.trendlines) {
        const { upLines, downLines } = opt.trendlines;
        if (upLines?.length) {
          const u = upLines.at(-1);
          trendUp.setData([
            { time: shown[u.p1.index].time, value: u.p1.price },
            { time: shown[u.p2.index].time, value: u.p2.price },
          ]);
          trendUp.applyOptions({ visible:true });
        }
        if (downLines?.length) {
          const d = downLines.at(-1);
          trendDn.setData([
            { time: shown[d.p1.index].time, value: d.p1.price },
            { time: shown[d.p2.index].time, value: d.p2.price },
          ]);
          trendDn.applyOptions({ visible:true });
        }
      }

      // 三角
      if (opt.triangle) {
        triUp.setData([
          { time: shown[opt.triangle.upperLine.p1.index].time, value: opt.triangle.upperLine.p1.price },
          { time: shown[opt.triangle.upperLine.p2.index].time, value: opt.triangle.upperLine.p2.price },
        ]);
        triLow.setData([
          { time: shown[opt.triangle.lowerLine.p1.index].time, value: opt.triangle.lowerLine.p1.price },
          { time: shown[opt.triangle.lowerLine.p2.index].time, value: opt.triangle.lowerLine.p2.price },
        ]);
        triUp.applyOptions({ visible:true });
        triLow.applyOptions({ visible:true });
      }

      // W 底
      if (opt.wPattern) {
        const W = opt.wPattern;
        wLine1.setData([
          { time: shown[W.p1.index].time, value: W.p1.price },
          { time: shown[W.p2.index].time, value: W.p2.price },
        ]);
        wLine2.setData([
          { time: shown[W.p3.index].time, value: W.p3.price },
          { time: shown[W.p4.index].time, value: W.p4.price },
        ]);
        wNeck.setData([
          { time: shown[W.p1.index].time, value: W.neck },
          { time: shown[shown.length - 1].time, value: W.neck },
        ]);
        wLine1.applyOptions({ visible:true });
        wLine2.applyOptions({ visible:true });
        wNeck.applyOptions({ visible:true });
      }
    }

    // ===== 指標區 =====
    indAutoL1.setData([]); indAutoL2.setData([]);
    macdL1.setData([]); macdL2.setData([]); macdHist.setData([]);

    if (indType === "kd") {
      indAutoL1.setData(shown.map((c,i)=>({time:c.time,value:indicators.K[i]})));
      indAutoL2.setData(shown.map((c,i)=>({time:c.time,value:indicators.D[i]})));
    } else if (indType === "rsi") {
      indAutoL1.setData(shown.map((c,i)=>({time:c.time,value:indicators.RSI[i]})));
    } else if (indType === "macd") {
      macdL1.setData(shown.map((c,i)=>({time:c.time,value:indicators.MACD[i]})));
      macdL2.setData(shown.map((c,i)=>({time:c.time,value:indicators.MACDSignal[i]})));
      macdHist.setData(shown.map((c,i)=>({
        time: c.time,
        value: indicators.MACDHist[i],
        color: indicators.MACDHist[i] >= 0 ? "#26a69a" : "#ff6b6b"
      })));
    }

    // ✅ 每次 update 都 setVisibleRange（toggle 時 shown.length 不變，但 series/scale 變了）
    const start = Math.max(0, shown.length - visibleBars);
    const from = shown[start].time;
    const to   = shown[shown.length - 1].time;

    chart.timeScale().setVisibleRange({ from, to });
    volChart.timeScale().setVisibleRange({ from, to });
    indChart.timeScale().setVisibleRange({ from, to });
  }

  global.ChartManager = { init, update };
})(window);
