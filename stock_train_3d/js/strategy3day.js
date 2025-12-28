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
    
    // 使用堆疊 (Stack) 記憶關卡
    // 陣列尾端 = 最新的關卡
    const bullStack = []; 
    let bullBrokenCount = 0; 

    const bearStack = [];
    let bearBrokenCount = 0; 

    let bullTrend = 0; 
    let bearTrend = 0;

    for (let i = 0; i < data.length; i++) {
      const cur = data[i];
      const time = cur.time;

      if (i < 2) continue;

      const refHigh = getRefHigh(data, i);
      const refLow = getRefLow(data, i);

      // 取得當前生效的支撐 (S1) 與 壓力 (R1)
      let currentSupport = bullStack.length > 0 ? bullStack[bullStack.length - 1] : NaN;
      let currentResist = bearStack.length > 0 ? bearStack[bearStack.length - 1] : NaN;

      // ======================================
      // 1. 多頭邏輯
      // ======================================
      
      // A. 創新高：加入新支撐
      if (!isNaN(refHigh) && cur.close > refHigh) {
        // 如果目前沒支撐，或突破了比現有支撐更高的高點，就堆疊上去
        if (isNaN(currentSupport) || refHigh > currentSupport) {
            bullStack.push(refHigh); // Push S1
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
            // 跌破滿 3 天 -> 移除最上面的支撐 (Pop S1)
            // 原本的 S2 會自動遞補成為新的 S1
            if (bullBrokenCount >= 3) {
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
            bearStack.push(refLow); // Push R1
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
                bearStack.pop(); // Pop R1
                bearBrokenCount = 0;
                bearTrend = 0;
            }
        } else {
            bearBrokenCount = 0;
        }
      }
    }

    // ⭐ 回傳堆疊中最後兩筆資料 (S1, S2)
    const lenBull = bullStack.length;
    const lenBear = bearStack.length;

    return { 
      markers, 
      // S1: 最新 (Stack Top)
      bullS1: lenBull > 0 ? bullStack[lenBull - 1] : NaN,
      // S2: 次新 (Stack Top - 1)
      bullS2: lenBull > 1 ? bullStack[lenBull - 2] : NaN,
      
      bearR1: lenBear > 0 ? bearStack[lenBear - 1] : NaN,
      bearR2: lenBear > 1 ? bearStack[lenBear - 2] : NaN
    };
  };

  global.Strategy3Day = Strat;

})(window);