// js/kpattern.js
// K 線型態偵測（最後三根）
(function (global) {
  "use strict";

  const PATTERN_DESCRIPTION = {
    "三白兵": "連續三根中長紅 K，並且每根收盤價都創前一根新高，屬於強勢多頭型態。",
    "三黑鴉": "連續三根中長黑 K，並且每根收盤價都創前一根新低，屬於強勢空頭型態。",
    "晨星": "下跌趨勢後出現長黑→十字→長紅的三連型態，常是反轉向上的訊號。",
    "黃昏星": "上漲趨勢後出現長紅→十字→長黑的三連型態，常是反轉向下的訊號。",
    "跳空向上": "當天 K 線的開收價整體高於前一根 K 線高點，強勢突破。",
    "跳空向下": "當天 K 線的開收價整體低於前一根 K 線低點，強勢下跌。",
    "價漲量縮背離": "價格上漲但量能萎縮，攻擊力道不足。",
    "價跌量增背離": "價格下跌但量能放大，賣壓急速增加，偏空。",
  };

  function isRed(c) {
    return c.close > c.open;
  }
  function isGreen(c) {
    return c.close < c.open;
  }
  function smallBody(c) {
    return (
      Math.abs(c.close - c.open) / Math.max(c.open, 1) < 0.003
    );
  }

  function detect(candles) {
    if (!candles || candles.length < 3) return "";
    const last3 = candles.slice(-3);
    const [c1, c2, c3] = last3;
    const patterns = [];

    if (
      isRed(c1) &&
      isRed(c2) &&
      isRed(c3) &&
      c2.close > c1.close &&
      c3.close > c2.close
    ) {
      patterns.push("三白兵");
    }

    if (
      isGreen(c1) &&
      isGreen(c2) &&
      isGreen(c3) &&
      c2.close < c1.close &&
      c3.close < c2.close
    ) {
      patterns.push("三黑鴉");
    }

    if (
      isGreen(c1) &&
      smallBody(c2) &&
      isRed(c3) &&
      c3.close > (c1.open + c1.close) / 2
    ) {
      patterns.push("晨星");
    }

    if (
      isRed(c1) &&
      smallBody(c2) &&
      isGreen(c3) &&
      c3.close < (c1.open + c1.close) / 2
    ) {
      patterns.push("黃昏星");
    }

    if (c2.open > c1.high && c2.close > c1.high) {
      patterns.push("跳空向上");
    }
    if (c2.open < c1.low && c2.close < c1.low) {
      patterns.push("跳空向下");
    }

    const volTrend = [c1.volume, c2.volume, c3.volume];
    const priceTrend = [c1.close, c2.close, c3.close];
    if (priceTrend[2] > priceTrend[0] && volTrend[2] < volTrend[0]) {
      patterns.push("價漲量縮背離");
    }
    if (priceTrend[2] < priceTrend[0] && volTrend[2] > volTrend[0]) {
      patterns.push("價跌量增背離");
    }

    if (!patterns.length) return "（無明顯型態）";
    return patterns.join("、");
  }

  global.KPattern = {
    detect,
    explain: p => PATTERN_DESCRIPTION[p] || p || "",
  };
})(window);
