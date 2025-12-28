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

  // 型態線 Series (這些是短暫出現的，可以清空)
  let resLine, supLine;
  let trendUp, trendDn;
  let triUp, triLow;
  let wLine1, wLine2, wNeck;

  // ===== 指標 Series =====
  let indAutoL1, indAutoL2;       
  let macdL1, macdL2, macdHist;   

  // ===== 三日戰法 PriceLine =====
  let activeBullPriceLine = null;
  let activeBearPriceLine = null;

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
      upColor: "#ff0000", downColor: "#00aa00",
      borderUpColor: "#ff0000", borderDownColor: "#00aa00",
      wickUpColor: "#ff0000", wickDownColor: "#00aa00",
      priceScaleId: "right"
    });

    // ✅ 均線 (設定 autoscaleInfoProvider: null)
    // 這樣即使數值有變，也不會影響 K 線縮放
    const maOpt = { 
        lineWidth: 1, 
        visible: false, 
        priceScaleId: "right",
        autoscaleInfoProvider: () => null 
    };
    ma5 = chart.addLineSeries({ color:"#f00", ...maOpt });
    ma10 = chart.addLineSeries({ color:"#0a0", ...maOpt });
    ma20 = chart.addLineSeries({ color:"#00f", ...maOpt });

    // ✅ 布林通道
    const bbOpt = { 
        visible: false, 
        priceScaleId: "right",
        autoscaleInfoProvider: () => null 
    };
    bbU = chart.addLineSeries({ color:"#ffa500", ...bbOpt });
    bbM = chart.addLineSeries({ color:"#0066cc", ...bbOpt });
    bbL = chart.addLineSeries({ color:"#008800", ...bbOpt });

    // ✅ 型態線 (短暫出現)
    const patternOpt = {
        lineWidth: 1,
        visible: false,
        priceScaleId: "right",
        autoscaleInfoProvider: () => null 
    };
    resLine = chart.addLineSeries({ color:"#dd4444", ...patternOpt });
    supLine = chart.addLineSeries({ color:"#44aa44", ...patternOpt });
    trendUp = chart.addLineSeries({ color:"#00aa88", lineWidth:2, visible:false, priceScaleId: "right", autoscaleInfoProvider: () => null });
    trendDn = chart.addLineSeries({ color:"#aa0044", lineWidth:2, visible:false, priceScaleId: "right", autoscaleInfoProvider: () => null });
    triUp  = chart.addLineSeries({ color:"#aa6600", ...patternOpt });
    triLow = chart.addLineSeries({ color:"#5588ff", ...patternOpt });
    wLine1 = chart.addLineSeries({ color:"#cc00cc", ...patternOpt });
    wLine2 = chart.addLineSeries({ color:"#cc00cc", ...patternOpt });
    wNeck  = chart.addLineSeries({ color:"#cc00cc", ...patternOpt });

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

    // 取得當前畫面最左和最右的時間 (三日線用)
    const startTime = shown[0].time;
    const endTime = shown[shown.length - 1].time;

    // ===== 1. K線與成交量 =====
    candle.setData(shown);
    volSeries.setData(shown.map(c => ({ time: c.time, value: c.volume })));

    // ===== 2. 均線 (⭐ 修正：永遠塞入數據，只切換 visible) =====
    const closes = shown.map(c => c.close);
    const ma5Pts = U.sma(closes, 5).map((v,i)=>v!=null?{ time: shown[i].time, value: v }:null).filter(Boolean);
    const ma10Pts = U.sma(closes, 10).map((v,i)=>v!=null?{ time: shown[i].time, value: v }:null).filter(Boolean);
    const ma20Pts = U.sma(closes, 20).map((v,i)=>v!=null?{ time: shown[i].time, value: v }:null).filter(Boolean);

    // 不管 opt.showMA 是什麼，都把數據塞進去，保持圖表穩定
    ma5.setData(ma5Pts);
    ma10.setData(ma10Pts);
    ma20.setData(ma20Pts);

    // 只控制顯示/隱藏
    ma5.applyOptions({ visible: !!opt.showMA });
    ma10.applyOptions({ visible: !!opt.showMA });
    ma20.applyOptions({ visible: !!opt.showMA });

    // ===== 3. 布林通道 (⭐ 修正：永遠塞入數據) =====
    const bbUData = shown.map((c,i)=> (indicators.BB.upper[i] != null ? { time:c.time, value:indicators.BB.upper[i] } : null)).filter(Boolean);
    const bbMData = shown.map((c,i)=> (indicators.BB.mid[i]   != null ? { time:c.time, value:indicators.BB.mid[i] }   : null)).filter(Boolean);
    const bbLData = shown.map((c,i)=> (indicators.BB.lower[i] != null ? { time:c.time, value:indicators.BB.lower[i] } : null)).filter(Boolean);
    
    bbU.setData(bbUData);
    bbM.setData(bbMData);
    bbL.setData(bbLData);
    
    bbU.applyOptions({ visible: !!opt.showBB });
    bbM.applyOptions({ visible: !!opt.showBB });
    bbL.applyOptions({ visible: !!opt.showBB });

    // ===== 4. 型態線 (這些可以清空，因為它們不一定每天都有) =====
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
    
    // (Trendline/Triangle/WPattern - 保持不變)
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
      triUp.applyOptions({ visible:true }); triLow.applyOptions({ visible:true });
    }
    if (opt.wPattern) {
      const W = opt.wPattern;
      wLine1.setData([{ time: shown[W.p1.index].time, value: W.p1.price }, { time: shown[W.p2.index].time, value: W.p2.price }]);
      wLine2.setData([{ time: shown[W.p3.index].time, value: W.p3.price }, { time: shown[W.p4.index].time, value: W.p4.price }]);
      wNeck.setData([{ time: shown[W.p1.index].time, value: W.neck }, { time: shown[shown.length - 1].time, value: W.neck }]);
      wLine1.applyOptions({ visible:true }); wLine2.applyOptions({ visible:true }); wNeck.applyOptions({ visible:true });
    }

    // ===========================================
    // ⭐⭐ 三日戰法 (水平線繪製) ⭐⭐
    // ===========================================
    
    // 1. 移除舊 PriceLine
    if (activeBullPriceLine) {
        candle.removePriceLine(activeBullPriceLine);
        activeBullPriceLine = null;
    }
    if (activeBearPriceLine) {
        candle.removePriceLine(activeBearPriceLine);
        activeBearPriceLine = null;
    }
    candle.setMarkers([]); 

    // 2. 如果開關打開
    if (opt.strat3Day) {
        candle.setMarkers(opt.strat3Day.markers || []);
        
        const bullPrice = opt.strat3Day.currentBullSupport;
        const bearPrice = opt.strat3Day.currentBearResist;

        // 畫上最新的紅色支撐線 (必須 > 0)
        if (!isNaN(bullPrice) && bullPrice > 0) {
            activeBullPriceLine = candle.createPriceLine({
                price: bullPrice,
                color: '#ff0000',
                lineWidth: 2,
                lineStyle: 0, 
                axisLabelVisible: false,
            });
        }

        // 畫上最新的綠色壓力線 (必須 > 0)
        if (!isNaN(bearPrice) && bearPrice > 0) {
            activeBearPriceLine = candle.createPriceLine({
                price: bearPrice,
                color: '#00aa00',
                lineWidth: 2,
                lineStyle: 0,
                axisLabelVisible: false,
            });
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

    const start = Math.max(0, shown.length - visibleBars);
    const from = shown[start].time;
    const to   = shown[shown.length - 1].time;

    chart.timeScale().setVisibleRange({ from, to });
    volChart.timeScale().setVisibleRange({ from, to });
    indChart.timeScale().setVisibleRange({ from, to });
  }

  global.ChartManager = { init, update };
})(window);