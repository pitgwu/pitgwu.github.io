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

  // ===== Cache (確保均線不重算) =====
  let maCache = { ma5: [], ma10: [], ma20: [] };
  let bbCache = { u: [], m: [], l: [] };
  let cacheReady = false;
  
  // ===== 三日支撐／壓力線 (改用 PriceLine 變數) =====
  // 舊的 stratBullLine / stratBearLine 移除，改用這兩個變數
  let activeBullPriceLine = null;
  let activeBearPriceLine = null;

  function fixedChart(el, height) {
    return LightweightCharts.createChart(el, {
      width: el.clientWidth,
      height,
      layout: { background: { color: "#fff" }, textColor: "#222" },

      // ✅ 正確控制價格刻度
      rightPriceScale: { 
        autoScale: true, 
        visible: true,
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

    cacheReady = false;
    maCache = { ma5: [], ma10: [], ma20: [] };
    bbCache = { u: [], m: [], l: [] };
    
    // 重置 PriceLine 參照
    activeBullPriceLine = null;
    activeBearPriceLine = null;

    if (chart) {
      chart.remove();
      volChart.remove();
      indChart.remove();
    }
      
    chart = fixedChart(document.getElementById("chart"), 420);

    // ✅ K 線
    candle = chart.addCandlestickSeries({
      upColor: "#ff0000",
      downColor: "#00aa00",
      borderUpColor: "#ff0000",
      borderDownColor: "#00aa00",
      wickUpColor: "#ff0000",
      wickDownColor: "#00aa00",
      priceScaleId: "right"
    });

    // ✅ 均線 (Line Series)
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

    // ⭐ 注意：這裡不再建立 stratBullLine / stratBearLine (改用 PriceLine 機制)

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

    // ===== 1. 計算 Cache (均線/布林) =====
    // 這裡我們把資料算好存起來，確保資料一定是對的
    if (!cacheReady) {
      const closes = shown.map(c => c.close);

      maCache.ma5  = U.sma(closes, 5).map((v,i)=>v!=null?{ time: shown[i].time, value: v }:null).filter(Boolean);
      maCache.ma10 = U.sma(closes,10).map((v,i)=>v!=null?{ time: shown[i].time, value: v }:null).filter(Boolean);
      maCache.ma20 = U.sma(closes,20).map((v,i)=>v!=null?{ time: shown[i].time, value: v }:null).filter(Boolean);

      bbCache.u = shown.map((c,i)=>(indicators.BB.upper[i]!=null?{time:c.time,value:indicators.BB.upper[i]}:null)).filter(Boolean);
      bbCache.m = shown.map((c,i)=>(indicators.BB.mid[i]!=null?{time:c.time,value:indicators.BB.mid[i]}:null)).filter(Boolean);
      bbCache.l = shown.map((c,i)=>(indicators.BB.lower[i]!=null?{time:c.time,value:indicators.BB.lower[i]}:null)).filter(Boolean);

      // 寫入 Series
      ma5.setData(maCache.ma5);
      ma10.setData(maCache.ma10);
      ma20.setData(maCache.ma20);

      bbU.setData(bbCache.u);
      bbM.setData(bbCache.m);
      bbL.setData(bbCache.l);

      cacheReady = true;
    }

    // ===== 2. K線與成交量 =====
    candle.setData(shown);
    volSeries.setData(shown.map(c => ({ time: c.time, value: c.volume })));

    // ===== 3. 控制均線顯示 =====
    // 直接操作 visible 屬性，最穩定的做法
    ma5.applyOptions({ visible: !!opt.showMA });
    ma10.applyOptions({ visible: !!opt.showMA });
    ma20.applyOptions({ visible: !!opt.showMA });

    // ===== 4. 控制布林顯示 =====
    bbU.applyOptions({ visible: !!opt.showBB });
    bbM.applyOptions({ visible: !!opt.showBB });
    bbL.applyOptions({ visible: !!opt.showBB });

    // ===== 5. 型態線 (清空舊的) =====
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
    
    // (省略: Trendline, Triangle, WPattern 的繪圖邏輯，保持原本的即可)
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

    // ===========================================
    // ⭐⭐ 6. 核心修正：三日戰法 PriceLine ⭐⭐
    // ===========================================
    
    // A. 先移除舊的線 (不管開關有沒有開，先清乾淨)
    if (activeBullPriceLine) {
        candle.removePriceLine(activeBullPriceLine);
        activeBullPriceLine = null;
    }
    if (activeBearPriceLine) {
        candle.removePriceLine(activeBearPriceLine);
        activeBearPriceLine = null;
    }
    
    candle.setMarkers([]); // 清空標記

    // B. 如果開關打開，且有資料，就畫新的「死板水平線」
    if (opt.strat3Day) {
        candle.setMarkers(opt.strat3Day.markers || []);
        
        const bullPrice = opt.strat3Day.currentBullSupport;
        const bearPrice = opt.strat3Day.currentBearResist;

        // 畫上最新的紅色支撐線 (如果是有效的數值)
        if (!isNaN(bullPrice)) {
            activeBullPriceLine = candle.createPriceLine({
                price: bullPrice,
                color: '#ff0000',
                lineWidth: 2,
                lineStyle: 0, // 0 = 實線 (Solid)
                axisLabelVisible: false, // 不要在右邊顯示標籤
            });
        }

        // 畫上最新的綠色壓力線
        if (!isNaN(bearPrice)) {
            activeBearPriceLine = candle.createPriceLine({
                price: bearPrice,
                color: '#00aa00',
                lineWidth: 2,
                lineStyle: 0,
                axisLabelVisible: false,
            });
        }
    }
    // ===========================================


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