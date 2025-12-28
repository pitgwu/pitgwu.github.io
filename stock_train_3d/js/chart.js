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

  // ===== Ultra-Smooth cache =====
  let maCache = { ma5: [], ma10: [], ma20: [] };
  let bbCache = { u: [], m: [], l: [] };
  let cacheReady = false;
  
  // ===== 三日支撐／壓力線 =====
  let stratBullLine, stratBearLine;

  function fixedChart(el, height) {
    return LightweightCharts.createChart(el, {
      width: el.clientWidth,
      height,
      layout: { background: { color: "#fff" }, textColor: "#222" },

      // ✅ 正確控制價格刻度
      rightPriceScale: { 
        autoScale: true, 
        visible: true,
        // 確保 K 線不會貼頂或貼底
        scaleMargins: { top: 0.1, bottom: 0.1 }
      },
      leftPriceScale:  { visible: false },

      timeScale: {
        timeVisible: true,          // ✅ 盤中顯示 HH:mm
        secondsVisible: false,
        barSpacing: 6,
        fixLeftEdge: true,
        fixRightEdge: true,
        rightBarStaysOnScroll: true,   // ✅ 關鍵：不要顯示盤前 / 盤後空白
      },
      
      handleScroll: false,
      handleScale: false,
    });
  }

  function init() {

    cacheReady = false;
    maCache = { ma5: [], ma10: [], ma20: [] };
    bbCache = { u: [], m: [], l: [] };

    // 如果 chart 已存在，先移除
    if (chart) {
      chart.remove();
      volChart.remove();
      indChart.remove();
    }
      
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

    // ✅ 均線
    ma5 = chart.addLineSeries({ color:"#f00", lineWidth:1, visible:false, priceScaleId: "right" });
    ma10 = chart.addLineSeries({ color:"#0a0", lineWidth:1, visible:false, priceScaleId: "right" });
    ma20 = chart.addLineSeries({ color:"#00f", lineWidth:1, visible:false, priceScaleId: "right" });

    // ✅ 布林通道
    bbU = chart.addLineSeries({ color:"#ffa500", visible:false, priceScaleId: "right" });
    bbM = chart.addLineSeries({ color:"#0066cc", visible:false, priceScaleId: "right" });
    bbL = chart.addLineSeries({ color:"#008800", visible:false, priceScaleId: "right" });

    // 型態線
    resLine = chart.addLineSeries({ color:"#dd4444", lineWidth:1, visible:false, priceScaleId: "right" });
    supLine = chart.addLineSeries({ color:"#44aa44", lineWidth:1, visible:false, priceScaleId: "right" });

    trendUp = chart.addLineSeries({ color:"#00aa88", lineWidth:2, visible:false, priceScaleId: "right" });
    trendDn = chart.addLineSeries({ color:"#aa0044", lineWidth:2, visible:false, priceScaleId: "right" });

    triUp  = chart.addLineSeries({ color:"#aa6600", lineWidth:1, visible:false, priceScaleId: "right" });
    triLow = chart.addLineSeries({ color:"#5588ff", lineWidth:1, visible:false, priceScaleId: "right" });

    wLine1 = chart.addLineSeries({ color:"#cc00cc", lineWidth:1, visible:false, priceScaleId: "right" });
    wLine2 = chart.addLineSeries({ color:"#cc00cc", lineWidth:1, visible:false, priceScaleId: "right" });
    wNeck  = chart.addLineSeries({ color:"#cc00cc", lineWidth:1, visible:false, priceScaleId: "right" });

    // ⭐ 紅色支撐線 (修正版)
    stratBullLine = chart.addLineSeries({ 
      color: '#ff0000', 
      lineWidth: 2, 
      lineType: 0, // 0 = Simple Line (非階梯線)
      visible: false,
      priceScaleId: "right",
      // ⭐ 關鍵：告訴圖表「不要」參考這條線來縮放，以 K 線為主
      autoscaleInfoProvider: () => null, 
      // ⭐ 讓線條更乾淨
      crosshairMarkerVisible: false, 
      lastValueVisible: false,       
      priceLineVisible: false        
    });
  
    // ⭐ 綠色壓力線 (修正版)
    stratBearLine = chart.addLineSeries({ 
      color: '#00aa00', 
      lineWidth: 2, 
      lineType: 0, 
      visible: false,
      priceScaleId: "right",
      autoscaleInfoProvider: () => null, // 忽略縮放
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false 
    });

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
    
    // 🔒 強制穩定主價格刻度
    chart.timeScale().fitContent();
    chart.priceScale("right").applyOptions({ autoScale: true });
  }

  function setLineDataSafe(series, points, visible) {
    series.setData(points);
    series.applyOptions({ visible: !!visible });
  }

  function update(shown, indicators, opt) {
    shown = shown.filter(c => c.time != null);
    if (shown.length < 2) return;
    if (!shown || !shown.length) return;

    const visibleBars = opt.visibleBars || 40;
    const indType = opt.indicatorType;

    // ===== build cache once =====
    if (!cacheReady) {
      const closes = shown.map(c => c.close);

      maCache.ma5  = U.sma(closes, 5).map((v,i)=>v!=null?{ time: shown[i].time, value: v }:null).filter(Boolean);
      maCache.ma10 = U.sma(closes,10).map((v,i)=>v!=null?{ time: shown[i].time, value: v }:null).filter(Boolean);
      maCache.ma20 = U.sma(closes,20).map((v,i)=>v!=null?{ time: shown[i].time, value: v }:null).filter(Boolean);

      bbCache.u = shown.map((c,i)=>(indicators.BB.upper[i]!=null?{time:c.time,value:indicators.BB.upper[i]}:null)).filter(Boolean);
      bbCache.m = shown.map((c,i)=>(indicators.BB.mid[i]!=null?{time:c.time,value:indicators.BB.mid[i]}:null)).filter(Boolean);
      bbCache.l = shown.map((c,i)=>(indicators.BB.lower[i]!=null?{time:c.time,value:indicators.BB.lower[i]}:null)).filter(Boolean);

      ma5.setData(maCache.ma5);
      ma10.setData(maCache.ma10);
      ma20.setData(maCache.ma20);

      bbU.setData(bbCache.u);
      bbM.setData(bbCache.m);
      bbL.setData(bbCache.l);

      cacheReady = true;
    }

    // ===== K線/成交量 =====
    candle.setData(shown);
    volSeries.setData(shown.map(c => ({ time: c.time, value: c.volume })));

    // ===== 均線 =====
    if (opt.showMA) {
      setLineDataSafe(ma5, maCache.ma5, true);
      setLineDataSafe(ma10, maCache.ma10, true);
      setLineDataSafe(ma20, maCache.ma20, true);
    } else {
      ma5.applyOptions({ visible:false });
      ma10.applyOptions({ visible:false });
      ma20.applyOptions({ visible:false });
    }

    // ===== 布林通道 =====
    if (opt.showBB) {
      // 這裡如果只是 toggle，不需要重算，直接 toggle visible 即可 (優化效能)
      // 但為了保險起見，維持原邏輯重新 setData 也無妨
      const u = shown.map((c,i)=> (indicators.BB.upper[i] != null ? { time:c.time, value:indicators.BB.upper[i] } : null)).filter(Boolean);
      const m = shown.map((c,i)=> (indicators.BB.mid[i]   != null ? { time:c.time, value:indicators.BB.mid[i] }   : null)).filter(Boolean);
      const l = shown.map((c,i)=> (indicators.BB.lower[i] != null ? { time:c.time, value:indicators.BB.lower[i] } : null)).filter(Boolean);
      setLineDataSafe(bbU, u, true);
      setLineDataSafe(bbM, m, true);
      setLineDataSafe(bbL, l, true);
    } else {
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
      if (global.SupportResistance?.findLines) {
        const SR = global.SupportResistance.findLines(shown, 20);
        const t = shown[shown.length - 1].time;
        if (SR[0]) { resLine.setData([{ time:t, value:SR[0].price }]); resLine.applyOptions({ visible:true }); }
        if (SR[1]) { supLine.setData([{ time:t, value:SR[1].price }]); supLine.applyOptions({ visible:true }); }
      }
    }
    
    if (opt.trendlines) {
      const { upLines, downLines } = opt.trendlines;
      if (upLines?.length) {
        const u = upLines.at(-1);
        trendUp.setData([{ time: shown[u.p1.index].time, value: u.p1.price }, { time: shown[u.p2.index].time, value: u.p2.price }]);
        trendUp.applyOptions({ visible:true });
      }
      if (downLines?.length) {
        const d = downLines.at(-1);
        trendDn.setData([{ time: shown[d.p1.index].time, value: d.p1.price }, { time: shown[d.p2.index].time, value: d.p2.price }]);
        trendDn.applyOptions({ visible:true });
      }
    }

    if (opt.triangle) {
      triUp.setData([{ time: shown[opt.triangle.upperLine.p1.index].time, value: opt.triangle.upperLine.p1.price }, { time: shown[opt.triangle.upperLine.p2.index].time, value: opt.triangle.upperLine.p2.price }]);
      triLow.setData([{ time: shown[opt.triangle.lowerLine.p1.index].time, value: opt.triangle.lowerLine.p1.price }, { time: shown[opt.triangle.lowerLine.p2.index].time, value: opt.triangle.lowerLine.p2.price }]);
      triUp.applyOptions({ visible:true });
      triLow.applyOptions({ visible:true });
    }

    if (opt.wPattern) {
      const W = opt.wPattern;
      wLine1.setData([{ time: shown[W.p1.index].time, value: W.p1.price }, { time: shown[W.p2.index].time, value: W.p2.price }]);
      wLine2.setData([{ time: shown[W.p3.index].time, value: W.p3.price }, { time: shown[W.p4.index].time, value: W.p4.price }]);
      wNeck.setData([{ time: shown[W.p1.index].time, value: W.neck }, { time: shown[shown.length - 1].time, value: W.neck }]);
      wLine1.applyOptions({ visible:true }); wLine2.applyOptions({ visible:true }); wNeck.applyOptions({ visible:true });
    }

    // ⭐ 三日戰法數據更新
    if (opt.strat3Day) {
        candle.setMarkers(opt.strat3Day.markers || []);
        setLineDataSafe(stratBullLine, opt.strat3Day.bullLine, true);
        setLineDataSafe(stratBearLine, opt.strat3Day.bearLine, true);
    } else {
        // ⭐ 關鍵：關閉時要清空數據，否則 ghost data 會影響縮放
        stratBullLine.setData([]); stratBullLine.applyOptions({ visible: false });
        stratBearLine.setData([]); stratBearLine.applyOptions({ visible: false });
        candle.setMarkers([]);
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

    const start = Math.max(0, shown.length - visibleBars);
    const from = shown[start].time;
    const to   = shown[shown.length - 1].time;

    chart.timeScale().setVisibleRange({ from, to });
    volChart.timeScale().setVisibleRange({ from, to });
    indChart.timeScale().setVisibleRange({ from, to });
  }

  global.ChartManager = { init, update };
})(window);