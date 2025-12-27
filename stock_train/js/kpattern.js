// js/kpattern.js
// K 線型態偵測 (含酒田戰法)
(function (global) {
  "use strict";

  const PATTERNS = [];

  // 輔助函式
  const isRed = (c) => c.close > c.open;
  const isGreen = (c) => c.close < c.open;
  const bodySize = (c) => Math.abs(c.close - c.open);
  const upperShadow = (c) => c.high - Math.max(c.open, c.close);
  const lowerShadow = (c) => Math.min(c.open, c.close) - c.low;
  const isGapUp = (c1, c2) => c2.low > c1.high;
  const isGapDown = (c1, c2) => c2.high < c1.low;

  // 1. 三兵 (Three Soldiers/Crows)
  PATTERNS.push((data) => {
    if (data.length < 3) return null;
    const [c1, c2, c3] = data.slice(-3);
    
    // 紅三兵 (穩健上漲)
    if (isRed(c1) && isRed(c2) && isRed(c3) && 
        c2.close > c1.close && c3.close > c2.close &&
        c2.open > c1.open && c3.open > c2.open) {
      return { side: "bull", name: "紅三兵：多頭穩健進攻" };
    }
    // 黑三鴉 (沈重賣壓)
    if (isGreen(c1) && isGreen(c2) && isGreen(c3) && 
        c2.close < c1.close && c3.close < c2.close) {
      return { side: "bear", name: "黑三鴉：空頭主力倒貨" };
    }
    return null;
  });

  // 2. 三法 (Three Methods) - 休息後再上
  PATTERNS.push((data) => {
    if (data.length < 5) return null;
    const slice = data.slice(-5);
    const [c1, c2, c3, c4, c5] = slice;

    // 上升三法 (長紅 -> 三小黑整理 -> 長紅突破)
    if (isRed(c1) && bodySize(c1) > c1.open * 0.015 && // 第一根長紅
        isRed(c5) && c5.close > c1.close && // 第五根長紅創新高
        // 中間三根都在第一根範圍內
        c2.low > c1.low && c3.low > c1.low && c4.low > c1.low) {
      return { side: "bull", name: "上升三法：N字攻擊發動" };
    }

    // 下降三法 (長黑 -> 三小紅整理 -> 長黑跌破)
    if (isGreen(c1) && bodySize(c1) > c1.open * 0.015 &&
        isGreen(c5) && c5.close < c1.close &&
        c2.high < c1.high && c3.high < c1.high && c4.high < c1.high) {
      return { side: "bear", name: "下降三法：空頭中繼再殺" };
    }
    return null;
  });

  // 3. 三空 (Three Gaps) - 過熱警訊
  PATTERNS.push((data) => {
    if (data.length < 4) return null;
    const [c1, c2, c3, c4] = data.slice(-4);

    // 三空陽 (連跳三空)
    if (isGapUp(c1, c2) && isGapUp(c2, c3) && isGapUp(c3, c4)) {
      return { side: "bear", name: "三空陽：多頭力竭，隨時回檔" };
    }
    // 三空陰
    if (isGapDown(c1, c2) && isGapDown(c2, c3) && isGapDown(c3, c4)) {
      return { side: "bull", name: "三空陰：空頭力竭，醞釀反彈" };
    }
    return null;
  });

  // 4. 吞噬與貫穿 (Engulfing / Piercing)
  PATTERNS.push((data) => {
    if (data.length < 2) return null;
    const [c1, c2] = data.slice(-2);

    // 陽包陰 (多頭吞噬)
    if (isGreen(c1) && isRed(c2) && c2.close > c1.high && c2.open < c1.low) {
      return { side: "bull", name: "陽包陰：多頭吞噬" };
    }
    // 陰包陽 (空頭吞噬)
    if (isRed(c1) && isGreen(c2) && c2.close < c1.low && c2.open > c1.high) {
      return { side: "bear", name: "陰包陽：空頭吞噬" };
    }
    // 貫穿線 (低檔反轉)
    if (isGreen(c1) && isRed(c2) && c2.open < c1.low && c2.close > (c1.open + c1.close)/2) {
      return { side: "bull", name: "貫穿線：低檔反轉訊號" };
    }
    // 烏雲蓋頂 (高檔反轉)
    if (isRed(c1) && isGreen(c2) && c2.open > c1.high && c2.close < (c1.open + c1.close)/2) {
      return { side: "bear", name: "烏雲蓋頂：高檔反轉訊號" };
    }
    return null;
  });

  // 5. 單K型態 (大陽/大陰/十字)
  PATTERNS.push((data) => {
    const c = data[data.length - 1];
    const range = bodySize(c);
    const ratio = range / c.open;

    // 大陽線 (>2.5%)
    if (isRed(c) && ratio > 0.025) {
      return { side: "bull", name: "大陽線：強勢表態" };
    }
    // 大陰線 (>2.5%)
    if (isGreen(c) && ratio > 0.025) {
      return { side: "bear", name: "大陰線：恐慌殺盤" };
    }
    // 十字變盤線
    if (ratio < 0.002 && (upperShadow(c) > range * 2 || lowerShadow(c) > range * 2)) {
      return { side: "bull", name: "十字星：多空變盤" }; // side 暫定，需看位置
    }
    return null;
  });

  // 對外公開的偵測函式
  // 回傳 [{ side: 'bull'|'bear', name: '...' }, ...]
  function detectAll(data) {
    if (!data || data.length < 5) return [];
    
    const results = [];
    
    // 跑所有定義好的型態邏輯
    PATTERNS.forEach(logic => {
      const res = logic(data);
      if (res) results.push(res);
    });

    return results;
  }

  global.KPattern = { detectAll };

})(window);