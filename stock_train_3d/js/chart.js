// js/chart.js

(function (global) {
  "use strict";

  const U = global.Util;

  let chart, candle;
  let volChart, volSeries;
  let indChart;

  // ===== 主圖 Series =====
  let ma5, ma10, ma20;
  let bbU, bbM, bbL;

  // 型態線 Series
  let resLine, supLine;
  let trendUp, trendDn;
  let triUp, triLow;
  let wLine1, wLine2, wNeck;

  // ===== 指標 Series =====
  let indAutoL1, indAutoL2;       
  let macdL1, macdL2, macdHist;   

  // ===== ⭐ 三日戰法水平線 (改回 LineSeries) ⭐ =====
  let stratBullLine, stratBearLine;

  function fixedChart(el, height) {
    return LightweightCharts.createChart(el, {
      width: el.clientWidth,
      height,
      layout: { background: { color: "#fff" }, textColor: "#222" },
      rightPriceScale: { 
        autoScale: true, 
        visible: true,
        // 增加邊距，避免 K 線貼頂貼底
        scaleMargins: { top: 0.1, bottom: 0.1 }
      },
      leftPriceScale:  { visible: false },
      timeScale: {
        timeVisible: true,          
        secondsVisible: false,
        barSpacing: 6,
        fixLeftEdge: true,
        fixRightEdge: true,
        rightBarStaysOnScroll: true,   
      },
      handleScroll: false,
      handleScale: false,
    });
  }

  function init() {
    if (chart) {
      chart.remove();
      volChart.remove();
      indChart.remove();
    }
      
    chart = fixedChart(document.getElementById("chart"), 420);

    // ✅ K 線 (主角，由它決定縮放)
    candle = chart.addCandlestickSeries({
      upColor: "#ff0000", downColor: "#00aa00",
      borderUpColor: "#ff0000", borderDownColor: "#00aa00",
      wickUpColor: "#ff0000", wickDownColor: "#00aa00",
      priceScaleId: "right"
    });

    // 定義一個通用的設定，讓輔助線不影響縮放
    const auxiliaryLineOptions = {
        lineWidth: 1,
        visible: false,
        priceScaleId: "right",
        // ⭐⭐ 關鍵：告訴圖表忽略這些線的數值，不影響 K 線縮放 ⭐⭐
        autoscaleInfoProvider: () => null
    };

    // ✅ 均線
    ma5 = chart.addLineSeries({ color:"#f00", ...auxiliaryLineOptions });
    ma10 = chart.addLineSeries({ color:"#0a0", ...auxiliaryLineOptions });
    ma20 = chart.addLineSeries({ color:"#00f", ...auxiliaryLineOptions });

    // ✅ 布林通道
    bbU = chart.addLineSeries({ color:"#ffa500", ...auxiliaryLineOptions });
    bbM = chart.addLineSeries({ color:"#0066cc", ...auxiliaryLineOptions });
    bbL = chart.addLineSeries({ color:"#008800", ...auxiliaryLineOptions });

    // ✅ 型態線
    resLine = chart.addLineSeries({ color:"#dd4444", ...auxiliaryLineOptions });
    supLine = chart.addLineSeries({ color:"#44aa44", ...auxiliaryLineOptions });
    trendUp = chart.addLineSeries({ color:"#00aa88", lineWidth:2, ...auxiliaryLineOptions });
    trendDn = chart.addLineSeries({ color:"#aa0044", lineWidth:2, ...auxiliaryLineOptions });
    triUp  = chart.addLineSeries({ color:"#aa6600", ...auxiliaryLineOptions });
    triLow = chart.addLineSeries({ color:"#5588ff", ...auxiliaryLineOptions });
    wLine1 = chart.addLineSeries({ color:"#cc00cc", ...auxiliaryLineOptions });
    wLine2 = chart.addLineSeries({ color:"#cc00cc", ...auxiliaryLineOptions });
    wNeck  = chart.addLineSeries({ color:"#cc00cc", ...auxiliaryLineOptions });

    // ===== ⭐ 三日戰法線 (初始化) ⭐ =====
    const stratOpt = {
        lineWidth: 2,
        lineStyle: 0, // 實線
        visible: false,
        priceScaleId: "right",
        // ⭐⭐ 關鍵：絕對不要影響縮放 ⭐⭐
        autoscaleInfoProvider: () => null,
        // 讓線條更乾淨，不顯示標籤
        crosshairMarkerVisible: false,
        lastValueVisible: false,
        priceLineVisible: false
    };
    stratBullLine = chart.addLineSeries({ color: '#ff0000', ...stratOpt });
    stratBearLine = chart.addLineSeries({ color: '#00aa00', ...stratOpt });

    /* ===== 副圖 ===== */
    volChart = fixedChart(document.getElementById("volume"), 100);
    volChart.timeScale().applyOptions({ visible: false });
    volSeries = volChart.addHistogramSeries({ priceFormat: { type: "volume" } });
    indChart = fixedChart(document.getElementById("indicator"), 150);
    indChart.timeScale().applyOptions({ visible: false });
    indAutoL1 = indChart.addLineSeries({ lineWidth: 2, color: "#1f77b4" });
    indAutoL2 = indChart.addLineSeries({ lineWidth: 2, color: "#aa00aa" });
    macdL1 = indChart.addLineSeries({ lineWidth: 2, color: "#1f77b4" });
    macdL2 = indChart.addLineSeries({ lineWidth: 2, color: "#aa00aa" });
    macdHist = indChart.addHistogramSeries({});
    
    chart.timeScale().fitContent();
    chart.priceScale("right").applyOptions({ autoScale: true });
  }

  function setLineDataSafe(series, points, visible) {
    series.setData(points);
    series.applyOptions({ visible: !!visible });
  }

  function update(shown, indicators, opt) {
    shown = shown.filter(c => c.time != null);
    if (!shown || shown.length < 2) return;

    const visibleBars = opt.visibleBars || 40;
    const indType = opt.indicatorType;

    // 取得當前畫面最左和最右的時間，用於繪製水平線
    const startTime = shown[0].time;
    const endTime = shown[shown.length - 1].time;

    // ===== 1. K線與成交量 =====
    candle.setData(shown);
    volSeries.setData(shown.map(c => ({ time: c.time, value: c.volume })));

    // ===== 2. 均線 (每次重算，解決不更新問題) =====
    const closes = shown.map(c => c.close);
    if (opt.showMA) {
      const ma5Pts = U.sma(closes, 5).map((v,i)=>v!=null?{ time: shown[i].time, value: v }:null).filter(Boolean);
      const ma10Pts = U.sma(closes, 10).map((v,i)=>v!=null?{ time: shown[i].time, value: v }:null).filter(Boolean);
      const ma20Pts = U.sma(closes, 20).map((v,i)=>v!=null?{ time: shown[i].time, value: v }:null).filter(Boolean);
      setLineDataSafe(ma5, ma5Pts, true);
      setLineDataSafe(ma10, ma10Pts, true);
      setLineDataSafe(ma20, ma20Pts, true);
    } else {
      ma5.setData([]); ma5.applyOptions({ visible:false }); 
      ma10.setData([]); ma10.applyOptions({ visible:false }); 
      ma20.setData([]); ma20.applyOptions({ visible:false });
    }

    // ===== 3. 布林通道 =====
    if (opt.showBB) {
      const u = shown.map((c,i)=> (indicators.BB.upper[i] != null ? { time:c.time, value:indicators.BB.upper[i] } : null)).filter(Boolean);
      const m = shown.map((c,i)=> (indicators.BB.mid[i]   != null ? { time:c.time, value:indicators.BB.mid[i] }   : null)).filter(Boolean);
      const l = shown.map((c,i)=> (indicators.BB.lower[i] != null ? { time:c.time, value:indicators.BB.lower[i] } : null)).filter(Boolean);
      setLineDataSafe(bbU, u, true);
      setLineDataSafe(bbM, m, true);
      setLineDataSafe(bbL, l, true);
    } else {
      bbU.setData([]); bbU.applyOptions({ visible:false }); 
      bbM.setData([]); bbM.applyOptions({ visible:false }); 
      bbL.setData([]); bbL.applyOptions({ visible:false });
    }

    // ===== 4. 型態線 (清空舊的) =====
    [resLine,supLine,trendUp,trendDn,triUp,triLow,wLine1,wLine2,wNeck].forEach(s=>{
      s.setData([]);
      s.applyOptions({ visible:false });
    });
    if (opt.showMA && global.SupportResistance?.findLines) { /*...略...*/ }
    if (opt.trendlines) { /*...略...*/ }
    if (opt.triangle) { /*...略...*/ }
    if (opt.wPattern) { /*...略...*/ }

    // ===========================================
    // ⭐⭐ 三日戰法 (水平線繪製邏輯) ⭐⭐
    // ===========================================
    candle.setMarkers([]);

    if (opt.strat3Day) {
        candle.setMarkers(opt.strat3Day.markers || []);
        
        const bullPrice = opt.strat3Day.currentBullSupport;
        const bearPrice = opt.strat3Day.currentBearResist;

        // 畫紅色支撐線
        if (!isNaN(bullPrice) && bullPrice > 0) {
            // 技巧：只用「起點」和「終點」兩個點，畫出一條橫跨畫面的水平線
            stratBullLine.setData([
                { time: startTime, value: bullPrice },
                { time: endTime, value: bullPrice }
            ]);
            stratBullLine.applyOptions({ visible: true });
        } else {
            stratBullLine.setData([]);
            stratBullLine.applyOptions({ visible: false });
        }

        // 畫綠色壓力線
        if (!isNaN(bearPrice) && bearPrice > 0) {
            stratBearLine.setData([
                { time: startTime, value: bearPrice },
                { time: endTime, value: bearPrice }
            ]);
            stratBearLine.applyOptions({ visible: true });
        } else {
            stratBearLine.setData([]);
            stratBearLine.applyOptions({ visible: false });
        }

    } else {
        // 關閉時清空數據
        stratBullLine.setData([]); stratBullLine.applyOptions({ visible: false });
        stratBearLine.setData([]); stratBearLine.applyOptions({ visible: false });
    }

    // ===== 指標區 =====
    indAutoL1.setData([]); indAutoL2.setData([]);
    macdL1.setData([]); macdL2.setData([]); macdHist.setData([]);
    if (indType === "kd") { /*...略...*/ } 
    else if (indType === "rsi") { /*...略...*/ } 
    else if (indType === "macd") { /*...略...*/ }

    const start = Math.max(0, shown.length - visibleBars);
    const from = shown[start].time;
    const to   = shown[shown.length - 1].time;
    chart.timeScale().setVisibleRange({ from, to });
    volChart.timeScale().setVisibleRange({ from, to });
    indChart.timeScale().setVisibleRange({ from, to });
  }

  global.ChartManager = { init, update };
})(window);