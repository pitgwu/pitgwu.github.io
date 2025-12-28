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
    
    // 使用堆疊 (Stack) 來記憶所有突破過的關卡
    // 陣列尾端 (End) 是最新的關卡
    const bullStack = []; 
    let bullBrokenCount = 0; 

    const bearStack = [];
    let bearBrokenCount = 0; 

    // 狀態標記
    let bullTrend = 0; 
    let bearTrend = 0;

    for (let i = 0; i < data.length; i++) {
      const cur = data[i];
      const time = cur.time;

      if (i < 2) continue;

      const refHigh = getRefHigh(data, i);
      const refLow = getRefLow(data, i);

      // 取出堆疊最上層 (當前生效的)
      let currentSupport = bullStack.length > 0 ? bullStack[bullStack.length - 1] : NaN;
      let currentResist = bearStack.length > 0 ? bearStack[bearStack.length - 1] : NaN;

      // ======================================
      // 1. 多頭邏輯
      // ======================================
      
      // A. 創新高：加入新支撐
      if (!isNaN(refHigh) && cur.close > refHigh) {
        // 如果目前沒支撐，或者股價突破了比現有支撐更高的高點
        if (isNaN(currentSupport) || refHigh > currentSupport) {
            bullStack.push(refHigh); // 推入堆疊
            currentSupport = refHigh;
            
            if (bullTrend === 0) {
                bullTrend = 1;
                markers.push({ time, position: 'aboveBar', color: '#DAA520', shape: 'arrowUp', text: '1' });
            } else {
                bullTrend = 2;
                markers.push({ time, position: 'aboveBar', color: '#CC0000', shape: 'arrowUp', size: 2 });
            }
            bullBrokenCount = 0;
        }
      } 
      
      // B. 跌破確認
      if (!isNaN(currentSupport)) {
        if (cur.close < currentSupport) {
            bullBrokenCount++;
            if (bullBrokenCount >= 3) {
                // 跌破三天 -> 移除第一道防線 (Pop)
                bullStack.pop(); 
                bullBrokenCount = 0; 
                bullTrend = 0; 
            }
        } else {
            bullBrokenCount = 0;
        }
      }

      // ======================================
      // 2. 空頭邏輯
      // ======================================

      // A. 創新低：加入新壓力
      if (!isNaN(refLow) && cur.close < refLow) {
        if (isNaN(currentResist) || refLow < currentResist) {
            bearStack.push(refLow);
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

      // B. 突破確認
      if (!isNaN(currentResist)) {
        if (cur.close > currentResist) {
            bearBrokenCount++;
            if (bearBrokenCount >= 3) {
                bearStack.pop(); // 移除第一道壓力
                bearBrokenCount = 0;
                bearTrend = 0;
            }
        } else {
            bearBrokenCount = 0;
        }
      }
    }

    // ⭐ 回傳最後狀態的「兩層」關卡
    const lenBull = bullStack.length;
    const lenBear = bearStack.length;

    return { 
      markers, 
      // S1: 最新的支撐, S2: 次新的支撐
      bullS1: lenBull > 0 ? bullStack[lenBull - 1] : NaN,
      bullS2: lenBull > 1 ? bullStack[lenBull - 2] : NaN,
      // R1: 最新的壓力, R2: 次新的壓力
      bearR1: lenBear > 0 ? bearStack[lenBear - 1] : NaN,
      bearR2: lenBear > 1 ? bearStack[lenBear - 2] : NaN
    };
  };

  global.Strategy3Day = Strat;

})(window);