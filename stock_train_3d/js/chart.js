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

  // 輔助：清洗數據
  function cleanData(data) {
    return data.filter(d => d && d.time != null && Number.isFinite(d.value));
  }

  function fixedChart(el, height) {
    return LightweightCharts.createChart(el, {
      width: el.clientWidth,
      height,
      layout: { background: { color: "#fff" }, textColor: "#222" },
      rightPriceScale: { 
        autoScale: true, 
        visible: true,
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

    // 1. K 線
    candle = chart.addCandlestickSeries({
      upColor: "#ff0000", downColor: "#00aa00",
      borderUpColor: "#ff0000", borderDownColor: "#00aa00",
      wickUpColor: "#ff0000", wickDownColor: "#00aa00",
      priceScaleId: "right"
    });

    // 2. 定義「完全忽略縮放」的設定
    const noScaleOpt = {
        lineWidth: 1,
        visible: false,
        priceScaleId: "right",
        // ⭐ 絕對關鍵：告訴圖表不要參考這些線的數值
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

    // 3. 三日戰法線
    // 使用 LineSeries 繪製水平線，並套用 noScaleOpt
    const stratOpt = Object.assign({}, noScaleOpt, {
        lineWidth: 2,
        lineStyle: 0,
        crosshairMarkerVisible: false,
        lastValueVisible: false,
        priceLineVisible: false
    });
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

  function update(shown, indicators, opt) {
    shown = shown.filter(c => c && c.time != null);
    if (!shown || shown.length < 2) return;

    const visibleBars = opt.visibleBars || 40;
    const indType = opt.indicatorType;
    const startTime = shown[0].time;
    const endTime = shown[shown.length - 1].time;

    // 1. K線
    candle.setData(shown);

    // 2. 成交量
    const volData = shown.map(c => ({ 
        time: c.time, 
        value: (c.volume != null && Number.isFinite(c.volume)) ? c.volume : 0 
    }));
    volSeries.setData(volData);

    // 3. 均線
    const closes = shown.map(c => c.close);
    const ma5Data = cleanData(U.sma(closes, 5).map((v,i)=>({ time: shown[i].time, value: v })));
    const ma10Data = cleanData(U.sma(closes, 10).map((v,i)=>({ time: shown[i].time, value: v })));
    const ma20Data = cleanData(U.sma(closes, 20).map((v,i)=>({ time: shown[i].time, value: v })));

    ma5.setData(ma5Data); ma5.applyOptions({ visible: !!opt.showMA });
    ma10.setData(ma10Data); ma10.applyOptions({ visible: !!opt.showMA });
    ma20.setData(ma20Data); ma20.applyOptions({ visible: !!opt.showMA });

    // 4. 布林
    const u = cleanData(shown.map((c,i)=> (indicators.BB.upper[i] != null ? { time:c.time, value:indicators.BB.upper[i] } : null)));
    const m = cleanData(shown.map((c,i)=> (indicators.BB.mid[i]   != null ? { time:c.time, value:indicators.BB.mid[i] }   : null)));
    const l = cleanData(shown.map((c,i)=> (indicators.BB.lower[i] != null ? { time:c.time, value:indicators.BB.lower[i] } : null)));
    
    bbU.setData(u); bbU.applyOptions({ visible: !!opt.showBB });
    bbM.setData(m); bbM.applyOptions({ visible: !!opt.showBB });
    bbL.setData(l); bbL.applyOptions({ visible: !!opt.showBB });

    // 5. 型態線 (清空)
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

        // 紅色支撐線：嚴格檢查
        // ⭐ 必須 > 1 (避免 0 值壓縮) 且必須是有限數值
        if (Number.isFinite(bullPrice) && bullPrice > 1) {
            stratBullLine.setData([
                { time: startTime, value: bullPrice },
                { time: endTime, value: bullPrice }
            ]);
            stratBullLine.applyOptions({ visible: true });
        } else {
            // ⭐ 絕對清空，傳入空陣列，這是解決 K 線縮小的核心
            stratBullLine.setData([]); 
            stratBullLine.applyOptions({ visible: false });
        }

        // 綠色壓力線：嚴格檢查
        if (Number.isFinite(bearPrice) && bearPrice > 1) {
            stratBearLine.setData([
                { time: startTime, value: bearPrice },
                { time: endTime, value: bearPrice }
            ]);
            stratBearLine.applyOptions({ visible: true });
        } else {
            // ⭐ 絕對清空
            stratBearLine.setData([]);
            stratBearLine.applyOptions({ visible: false });
        }

    } else {
        // 功能關閉時，清空數據
        stratBullLine.setData([]); stratBullLine.applyOptions({ visible: false });
        stratBearLine.setData([]); stratBearLine.applyOptions({ visible: false });
    }

    // 指標區
    indAutoL1.setData([]); indAutoL2.setData([]);
    macdL1.setData([]); macdL2.setData([]); macdHist.setData([]);
    if (indType === "kd") {
      indAutoL1.setData(cleanData(shown.map((c,i)=>({time:c.time,value:indicators.K[i]}))));
      indAutoL2.setData(cleanData(shown.map((c,i)=>({time:c.time,value:indicators.D[i]}))));
    } else if (indType === "rsi") {
      indAutoL1.setData(cleanData(shown.map((c,i)=>({time:c.time,value:indicators.RSI[i]}))));
    } else if (indType === "macd") {
      macdL1.setData(cleanData(shown.map((c,i)=>({time:c.time,value:indicators.MACD[i]}))));
      macdL2.setData(cleanData(shown.map((c,i)=>({time:c.time,value:indicators.MACDSignal[i]}))));
      macdHist.setData(cleanData(shown.map((c,i)=>({
        time: c.time,
        value: indicators.MACDHist[i],
        color: indicators.MACDHist[i] >= 0 ? "#26a69a" : "#ff6b6b"
      }))));
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