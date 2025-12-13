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

  // ===== 型態線 =====
  let resLine, supLine;
  let trendUp, trendDn;
  let triUp, triLow;
  let wLine1, wLine2, wNeck;

  // ===== 指標 =====
  let indAutoL1, indAutoL2;       // KD / RSI
  let macdL1, macdL2, macdHist;   // MACD（固定比例）

  // ✅【關鍵修正】過熱 / 過冷底色：必須是 module scope
  let indBgHigh, indBgLow;

  function fixedChart(el, height) {
    return LightweightCharts.createChart(el, {
      width: el.clientWidth,
      height,
      layout: { background: { color: "#fff" }, textColor: "#222" },
      rightPriceScale: { autoScale: true },
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
    const noScale = () => ({ priceRange: null });

    /* ===== 主圖 ===== */
    chart = fixedChart(document.getElementById("chart"), 420);

    candle = chart.addCandlestickSeries({
      upColor: "#ff0000",
      downColor: "#00aa00",
      borderUpColor: "#ff0000",
      borderDownColor: "#00aa00",
      wickUpColor: "#ff0000",
      wickDownColor: "#00aa00",
    });

    ma5  = chart.addLineSeries({ color:"#f00", lineWidth:1, visible:false, autoscaleInfoProvider:noScale });
    ma10 = chart.addLineSeries({ color:"#0a0", lineWidth:1, visible:false, autoscaleInfoProvider:noScale });
    ma20 = chart.addLineSeries({ color:"#00f", lineWidth:1, visible:false, autoscaleInfoProvider:noScale });

    bbU = chart.addLineSeries({ color:"#ffa500", autoscaleInfoProvider:noScale });
    bbM = chart.addLineSeries({ color:"#0066cc", autoscaleInfoProvider:noScale });
    bbL = chart.addLineSeries({ color:"#008800", autoscaleInfoProvider:noScale });

    resLine = chart.addLineSeries({ color:"#dd4444", lineWidth:1 });
    supLine = chart.addLineSeries({ color:"#44aa44", lineWidth:1 });
    trendUp = chart.addLineSeries({ color:"#00aa88", lineWidth:2 });
    trendDn = chart.addLineSeries({ color:"#aa0044", lineWidth:2 });
    triUp  = chart.addLineSeries({ color:"#aa6600", lineWidth:1 });
    triLow = chart.addLineSeries({ color:"#5588ff", lineWidth:1 });
    wLine1 = chart.addLineSeries({ color:"#cc00cc", lineWidth:1 });
    wLine2 = chart.addLineSeries({ color:"#cc00cc", lineWidth:1 });
    wNeck  = chart.addLineSeries({ color:"#cc00cc", lineWidth:1 });

    /* ===== 成交量 ===== */
    volChart = fixedChart(document.getElementById("volume"), 100);
    volChart.timeScale().applyOptions({ visible: false });
    volSeries = volChart.addHistogramSeries({ priceFormat:{ type:"volume" } });

    /* ===== 指標區 ===== */
    indChart = fixedChart(document.getElementById("indicator"), 150);
    indChart.timeScale().applyOptions({ visible: false });

    // ✅ 過熱 / 過冷底色（一定要在這裡初始化）
    indBgHigh = indChart.addLineSeries({
      color: "rgba(255,0,0,0.08)",
      lineWidth: 1000,
      autoscaleInfoProvider: noScale,
      visible: false
    });

    indBgLow = indChart.addLineSeries({
      color: "rgba(0,120,255,0.08)",
      lineWidth: 1000,
      autoscaleInfoProvider: noScale,
      visible: false
    });

    // KD / RSI
    indAutoL1 = indChart.addLineSeries({ lineWidth:2, color:"#1f77b4" });
    indAutoL2 = indChart.addLineSeries({ lineWidth:2, color:"#aa00aa" });

    // MACD（固定比例，避免縮放影響其他指標）
    const macdScale = () => ({ priceRange:{ minValue:-3, maxValue:3 } });

    macdL1 = indChart.addLineSeries({ lineWidth:2, autoscaleInfoProvider:macdScale });
    macdL2 = indChart.addLineSeries({ lineWidth:2, autoscaleInfoProvider:macdScale });
    macdHist = indChart.addHistogramSeries({ autoscaleInfoProvider:macdScale });
  }

  function update(shown, indicators, opt) {
    if (!shown || !shown.length) return;
    const visibleBars = opt.visibleBars || 40;

    candle.setData(shown);
    volSeries.setData(shown.map(c => ({ time:c.time, value:c.volume })));

    // ===== MA =====
    if (opt.showMA) {
      const c = shown.map(d => d.close);
      ma5.setData(U.sma(c,5).map((v,i)=>v?{time:shown[i].time,value:v}:null).filter(Boolean));
      ma10.setData(U.sma(c,10).map((v,i)=>v?{time:shown[i].time,value:v}:null).filter(Boolean));
      ma20.setData(U.sma(c,20).map((v,i)=>v?{time:shown[i].time,value:v}:null).filter(Boolean));
      ma5.applyOptions({ visible:true });
      ma10.applyOptions({ visible:true });
      ma20.applyOptions({ visible:true });
    } else {
      ma5.applyOptions({ visible:false });
      ma10.applyOptions({ visible:false });
      ma20.applyOptions({ visible:false });
    }

    // ===== BB =====
    if (opt.showBB) {
      bbU.setData(shown.map((c,i)=>({time:c.time,value:indicators.BB.upper[i]})));
      bbM.setData(shown.map((c,i)=>({time:c.time,value:indicators.BB.mid[i]})));
      bbL.setData(shown.map((c,i)=>({time:c.time,value:indicators.BB.lower[i]})));
    } else {
      bbU.setData([]); bbM.setData([]); bbL.setData([]);
    }

    // ===== 清空指標 =====
    indAutoL1.setData([]); indAutoL2.setData([]);
    macdL1.setData([]); macdL2.setData([]); macdHist.setData([]);
    indBgHigh.setData([]); indBgLow.setData([]);
    indBgHigh.applyOptions({ visible:false });
    indBgLow.applyOptions({ visible:false });

    if (opt.showMA) {
      // 支撐壓力
      if (global.SupportResistance?.findLines) {
        const SR = global.SupportResistance.findLines(shown, 20);
        const t = shown[shown.length - 1].time;
        if (SR[0]) resLine.setData([{ time:t, value:SR[0].price }]);
        if (SR[1]) supLine.setData([{ time:t, value:SR[1].price }]);
		resLine.applyOptions({ visible: true });
		supLine.applyOptions({ visible: true });
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
        }
        if (downLines?.length) {
          const d = downLines.at(-1);
          trendDn.setData([
            { time: shown[d.p1.index].time, value: d.p1.price },
            { time: shown[d.p2.index].time, value: d.p2.price },
          ]);
        }
		trendUp.applyOptions({ visible: true });
	    trendDn.applyOptions({ visible: true });
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
		triUp.applyOptions({ visible: true });
	    triLow.applyOptions({ visible: true });
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
	    wLine1.applyOptions({ visible: true });
	    wLine2.applyOptions({ visible: true });
	    wNeck.applyOptions({ visible: true });
      }
    }

    // ===== 指標切換 =====
    if (opt.indicatorType === "kd") {
      indAutoL1.setData(shown.map((c,i)=>({time:c.time,value:indicators.K[i]})));
      indAutoL2.setData(shown.map((c,i)=>({time:c.time,value:indicators.D[i]})));
      indBgHigh.setData(shown.map(c=>({time:c.time,value:80})));
      indBgLow.setData(shown.map(c=>({time:c.time,value:20})));
      indBgHigh.applyOptions({ visible:true });
      indBgLow.applyOptions({ visible:true });
    }

    if (opt.indicatorType === "rsi") {
      indAutoL1.setData(shown.map((c,i)=>({time:c.time,value:indicators.RSI[i]})));
      indBgHigh.setData(shown.map(c=>({time:c.time,value:70})));
      indBgLow.setData(shown.map(c=>({time:c.time,value:30})));
      indBgHigh.applyOptions({ visible:true });
      indBgLow.applyOptions({ visible:true });
    }

    if (opt.indicatorType === "macd") {
      macdL1.setData(shown.map((c,i)=>({time:c.time,value:indicators.MACD[i]})));
      macdL2.setData(shown.map((c,i)=>({time:c.time,value:indicators.MACDSignal[i]})));
      macdHist.setData(shown.map((c,i)=>({
        time:c.time,
        value:indicators.MACDHist[i],
        color: indicators.MACDHist[i] >= 0 ? "#26a69a" : "#ff6b6b"
      })));
    }

	if (opt.indicatorType === "rsi") {
  	  indBgHigh.setData(shown.map(c => ({ time: c.time, value: 70 })));
  	  indBgLow.setData(shown.map(c => ({ time: c.time, value: 30 })));
  	  indBgHigh.applyOptions({ visible: true });
  	  indBgLow.applyOptions({ visible: true });
	}

	if (opt.indicatorType === "kd") {
  	  indBgHigh.setData(shown.map(c => ({ time: c.time, value: 80 })));
	  indBgLow.setData(shown.map(c => ({ time: c.time, value: 20 })));
	  indBgHigh.applyOptions({ visible: true });
	  indBgLow.applyOptions({ visible: true });
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
