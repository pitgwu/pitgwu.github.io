// js/chart.js
(function (global) {
  "use strict";

  const U = global.Util;

  let chart, candle;
  let volChart, volSeries;
  let indChart;

  // 主圖指標
  let ma5, ma10, ma20;
  let bbU, bbM, bbL;

  // 型態線
  let resLine, supLine;
  let trendUp, trendDn;
  let triUp, triLow;
  let wLine1, wLine2, wNeck;

  // 三日戰法 (水平線 - 使用 LineSeries)
  let stratBullLine, stratBearLine;

  // 副圖指標
  let indAutoL1, indAutoL2;       
  let macdL1, macdL2, macdHist;   

  // 輔助：建立圖表
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
        timeVisible: true, secondsVisible: false, barSpacing: 6,
        fixLeftEdge: true, fixRightEdge: true, rightBarStaysOnScroll: true,   
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

    // 1. K 線 (主角)
    candle = chart.addCandlestickSeries({
      upColor: "#ff0000", downColor: "#00aa00",
      borderUpColor: "#ff0000", borderDownColor: "#00aa00",
      wickUpColor: "#ff0000", wickDownColor: "#00aa00",
      priceScaleId: "right"
    });

    // 2. 定義「輔助線」設定：強制忽略縮放 (關鍵！)
    const noScaleOpt = {
        lineWidth: 1,
        visible: false,
        priceScaleId: "right",
        // ⭐ 這行是防止 K 線縮小的關鍵，告訴圖表不要參考這些線來計算 Y 軸
        autoscaleInfoProvider: () => null 
    };

    // 均線
    ma5 = chart.addLineSeries(Object.assign({ color:"#f00" }, noScaleOpt));
    ma10 = chart.addLineSeries(Object.assign({ color:"#0a0" }, noScaleOpt));
    ma20 = chart.addLineSeries(Object.assign({ color:"#00f" }, noScaleOpt));

    // 布林
    bbU = chart.addLineSeries(Object.assign({ color:"#ffa500" }, noScaleOpt));
    bbM = chart.addLineSeries(Object.assign({ color:"#0066cc" }, noScaleOpt));
    bbL = chart.addLineSeries(Object.assign({ color:"#008800" }, noScaleOpt));

    // 型態線
    resLine = chart.addLineSeries(Object.assign({ color:"#dd4444" }, noScaleOpt));
    supLine = chart.addLineSeries(Object.assign({ color:"#44aa44" }, noScaleOpt));
    trendUp = chart.addLineSeries(Object.assign({ color:"#00aa88", lineWidth:2 }, noScaleOpt));
    trendDn = chart.addLineSeries(Object.assign({ color:"#aa0044", lineWidth:2 }, noScaleOpt));
    triUp  = chart.addLineSeries(Object.assign({ color:"#aa6600" }, noScaleOpt));
    triLow = chart.addLineSeries(Object.assign({ color:"#5588ff" }, noScaleOpt));
    wLine1 = chart.addLineSeries(Object.assign({ color:"#cc00cc" }, noScaleOpt));
    wLine2 = chart.addLineSeries(Object.assign({ color:"#cc00cc" }, noScaleOpt));
    wNeck  = chart.addLineSeries(Object.assign({ color:"#cc00cc" }, noScaleOpt));

    // 3. 三日戰法線 (也是 LineSeries，但加上忽略縮放)
    const stratOpt = {
        lineWidth: 2,
        lineStyle: 0, // 實線
        visible: false,
        priceScaleId: "right",
        autoscaleInfoProvider: () => null, // ⭐ 絕對不要影響縮放
        crosshairMarkerVisible: false,
        lastValueVisible: false,
        priceLineVisible: false
    };
    stratBullLine = chart.addLineSeries(Object.assign({ color: '#ff0000' }, stratOpt));
    stratBearLine = chart.addLineSeries(Object.assign({ color: '#00aa00' }, stratOpt));

    /* 副圖 */
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
    const startTime = shown[0].time;
    const endTime = shown[shown.length - 1].time;

    // 1. K線
    candle.setData(shown);
    volSeries.setData(shown.map(c => ({ time: c.time, value: c.volume })));

    // 2. 均線 (永遠塞數據，只切換 visible)
    const closes = shown.map(c => c.close);
    const ma5Pts = U.sma(closes, 5).map((v,i)=>v!=null?{ time: shown[i].time, value: v }:null).filter(Boolean);
    const ma10Pts = U.sma(closes, 10).map((v,i)=>v!=null?{ time: shown[i].time, value: v }:null).filter(Boolean);
    const ma20Pts = U.sma(closes, 20).map((v,i)=>v!=null?{ time: shown[i].time, value: v }:null).filter(Boolean);

    ma5.setData(ma5Pts); ma5.applyOptions({ visible: !!opt.showMA });
    ma10.setData(ma10Pts); ma10.applyOptions({ visible: !!opt.showMA });
    ma20.setData(ma20Pts); ma20.applyOptions({ visible: !!opt.showMA });

    // 3. 布林 (永遠塞數據)
    const u = shown.map((c,i)=> (indicators.BB.upper[i] != null ? { time:c.time, value:indicators.BB.upper[i] } : null)).filter(Boolean);
    const m = shown.map((c,i)=> (indicators.BB.mid[i]   != null ? { time:c.time, value:indicators.BB.mid[i] }   : null)).filter(Boolean);
    const l = shown.map((c,i)=> (indicators.BB.lower[i] != null ? { time:c.time, value:indicators.BB.lower[i] } : null)).filter(Boolean);
    
    bbU.setData(u); bbU.applyOptions({ visible: !!opt.showBB });
    bbM.setData(m); bbM.applyOptions({ visible: !!opt.showBB });
    bbL.setData(l); bbL.applyOptions({ visible: !!opt.showBB });

    // 4. 型態線 (可清空)
    [resLine,supLine,trendUp,trendDn,triUp,triLow,wLine1,wLine2,wNeck].forEach(s=>{
      s.setData([]); s.applyOptions({ visible:false });
    });
    if (opt.showMA && global.SupportResistance?.findLines) { /* ...略... */ }
    if (opt.trendlines) { /* ...略... */ }
    if (opt.triangle) { /* ...略... */ }
    if (opt.wPattern) { /* ...略... */ }

    // ===========================================
    // ⭐⭐ 三日戰法 (水平線繪製) ⭐⭐
    // ===========================================
    candle.setMarkers([]);

    if (opt.strat3Day) {
        candle.setMarkers(opt.strat3Day.markers || []);
        
        const bullPrice = opt.strat3Day.currentBullSupport;
        const bearPrice = opt.strat3Day.currentBearResist;

        // 畫紅色支撐線 (加強檢查：必須大於 1，避免 0 值造成壓縮)
        if (!isNaN(bullPrice) && bullPrice > 1) {
            stratBullLine.setData([
                { time: startTime, value: bullPrice },
                { time: endTime, value: bullPrice }
            ]);
            stratBullLine.applyOptions({ visible: true });
        } else {
            stratBullLine.applyOptions({ visible: false });
        }

        // 畫綠色壓力線 (加強檢查)
        if (!isNaN(bearPrice) && bearPrice > 1) {
            stratBearLine.setData([
                { time: startTime, value: bearPrice },
                { time: endTime, value: bearPrice }
            ]);
            stratBearLine.applyOptions({ visible: true });
        } else {
            stratBearLine.applyOptions({ visible: false });
        }

    } else {
        // 關閉時只隱藏，不清空數據
        stratBullLine.applyOptions({ visible: false });
        stratBearLine.applyOptions({ visible: false });
    }

    // 指標區
    indAutoL1.setData([]); indAutoL2.setData([]);
    macdL1.setData([]); macdL2.setData([]); macdHist.setData([]);
    if (indType === "kd") { /* ...略... */ } 
    else if (indType === "rsi") { /* ...略... */ } 
    else if (indType === "macd") { /* ...略... */ }

    const start = Math.max(0, shown.length - visibleBars);
    const from = shown[start].time;
    const to   = shown[shown.length - 1].time;
    chart.timeScale().setVisibleRange({ from, to });
    volChart.timeScale().setVisibleRange({ from, to });
    indChart.timeScale().setVisibleRange({ from, to });
  }

  global.ChartManager = { init, update };
})(window);