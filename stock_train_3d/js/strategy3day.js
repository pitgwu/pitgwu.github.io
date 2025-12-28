// js/strategy3day.js
(function (global) {
  "use strict";

  const Strat = {};

  // 取得前兩日的高點
  function getRefHigh(data, index) {
    if (index < 2) return NaN;
    return Math.max(data[index - 1].high, data[index - 2].high);
  }

  // 取得前兩日的低點
  function getRefLow(data, index) {
    if (index < 2) return NaN;
    return Math.min(data[index - 1].low, data[index - 2].low);
  }

  Strat.calculate = function (data) {
    const markers = [];
    
    // ===== 多頭堆疊 (Support Stack) =====
    // 陣列結構：[100, 105, 110...]，最後一個 (110) 是當前生效的支撐
    const bullStack = []; 
    let bullBrokenCount = 0; // 跌破計數

    // ===== 空頭堆疊 (Resistance Stack) =====
    const bearStack = [];
    let bearBrokenCount = 0; // 突破計數

    // 狀態標記 (用於畫箭頭)
    let bullTrend = 0; 
    let bearTrend = 0;

    for (let i = 0; i < data.length; i++) {
      const cur = data[i];
      const time = cur.time;

      if (i < 2) continue;

      const refHigh = getRefHigh(data, i);
      const refLow = getRefLow(data, i);

      // 取得當前生效的支撐/壓力 (堆疊的最上層)
      let currentSupport = bullStack.length > 0 ? bullStack[bullStack.length - 1] : NaN;
      let currentResist = bearStack.length > 0 ? bearStack[bearStack.length - 1] : NaN;

      // ======================================
      // 1. 多頭邏輯
      // ======================================
      
      // A. 創新高：增加新的支撐
      // 條件：收盤 > 前兩日高 且 (目前沒支撐 或 前兩日高 > 目前支撐)
      // 防止重複加入一樣的數值
      if (!isNaN(refHigh) && cur.close > refHigh) {
        if (isNaN(currentSupport) || refHigh > currentSupport) {
            bullStack.push(refHigh); // 推入新支撐
            currentSupport = refHigh; // 更新當前參考
            
            // 標記
            if (bullTrend === 0) {
                bullTrend = 1;
                markers.push({ time, position: 'aboveBar', color: '#DAA520', shape: 'arrowUp', text: '1' });
            } else {
                bullTrend = 2;
                markers.push({ time, position: 'aboveBar', color: '#CC0000', shape: 'arrowUp', size: 2 });
            }
            bullBrokenCount = 0; // 重置跌破計數
        }
      } 
      
      // B. 檢查跌破
      if (!isNaN(currentSupport)) {
        if (cur.close < currentSupport) {
            bullBrokenCount++;
            // 跌破滿 3 天 -> 移除當前支撐，退守前一個
            if (bullBrokenCount >= 3) {
                bullStack.pop(); // 移除最上面的
                bullBrokenCount = 0; 
                bullTrend = 0; // 趨勢暫時重置(或看你定義)
            }
        } else {
            bullBrokenCount = 0; // 守住了
        }
      }

      // ======================================
      // 2. 空頭邏輯
      // ======================================

      // A. 創新低：增加新的壓力
      if (!isNaN(refLow) && cur.close < refLow) {
        if (isNaN(currentResist) || refLow < currentResist) {
            bearStack.push(refLow); // 推入新壓力
            currentResist = refLow;
            
            if (bearTrend === 0) {
                bearTrend = 1;
                markers.push({ time, position: 'belowBar', color: '#000000', shape: 'arrowDown', text: '1' });
            } else {
                bearTrend = 2;
                markers.push({ time, position: 'belowBar', color: '#008000', shape: 'arrowDown', size: 2 });
            }
            bearBrokenCount = 0;
        }
      }

      // B. 檢查突破
      if (!isNaN(currentResist)) {
        if (cur.close > currentResist) {
            bearBrokenCount++;
            // 突破滿 3 天 -> 移除當前壓力，退守前一個
            if (bearBrokenCount >= 3) {
                bearStack.pop();
                bearBrokenCount = 0;
                bearTrend = 0;
            }
        } else {
            bearBrokenCount = 0;
        }
      }
    }

    // 回傳最後一根 K 棒當下有效的支撐與壓力
    // 這裡我們只取堆疊最上面 (最後加入) 的那個值給畫圖用
    const finalSupport = bullStack.length > 0 ? bullStack[bullStack.length - 1] : NaN;
    const finalResist = bearStack.length > 0 ? bearStack[bearStack.length - 1] : NaN;

    return { 
      markers, 
      currentBullSupport: finalSupport, 
      currentBearResist: finalResist 
    };
  };

  global.Strategy3Day = Strat;

})(window);