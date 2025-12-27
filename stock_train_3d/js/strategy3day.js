// js/strategy3day.js
(function (global) {
  "use strict";

  const Strat = {};

  // 取得包含自己在內的過去 N 天最高/最低
  // 演算法需求：今日收盤價 > 三日K棒(含今日)的高點
  // 這其實等於：今日收盤價 > 前兩日的高點 (因為若大於前兩日高點，且是紅K，通常就是三日最高)
  function getRefHigh(data, index) {
    if (index < 2) return null; // 修正：回傳 null 而不是 Infinity
    // 取前兩日 (i-1, i-2) 的最高點做比較基準
    return Math.max(data[index - 1].high, data[index - 2].high);
  }

  function getRefLow(data, index) {
    if (index < 2) return null; // 修正：回傳 null 而不是 Infinity
    return Math.min(data[index - 1].low, data[index - 2].low);
  }

  Strat.calculate = function (data) {
    const markers = [];
    const bullLine = []; // 紅色支撐線數據
    const bearLine = []; // 綠色壓力線數據

    // --- 多頭狀態變數 ---
    let bullTrend = 0; // 0:無, 1:第一次(黃), 2:第二次+(紅)
    let bullSupport = null; // 紅色支撐線數值
    let bullBrokenCount = 0; // 跌破天數計數

    // --- 空頭狀態變數 ---
    let bearTrend = 0; // 0:無, 1:第一次(黑), 2:第二次+(綠)
    let bearResist = null; // 綠色壓力線數值
    let bearBrokenCount = 0; // 突破天數計數

    for (let i = 0; i < data.length; i++) {
      const cur = data[i];
      const time = cur.time;

      // 前兩根略過
      if (i < 2) {
        bullLine.push({ time, value: null });
        bearLine.push({ time, value: null });
        continue;
      }

      const refHigh = getRefHigh(data, i); // 前兩日高
      const refLow = getRefLow(data, i);   // 前兩日低

      // ======================================
      // 1. 多頭邏輯 (三日高點)
      // ======================================
      
      // 條件：收盤價 > 三日高 (即大於前兩日高)
      if (cur.close > refHigh) {
        // 只要創新高，空頭結構直接破壞 (視策略而定，這裡先重置空頭)
        // bearTrend = 0; bearResist = null; 

        if (bullTrend === 0) {
          // 第一次
          bullTrend = 1;
          markers.push({ time, position: 'aboveBar', color: '#DAA520', shape: 'arrowUp', text: '1' }); // 金黃色
        } else {
          // 第二次以上 (連續上攻)
          bullTrend = 2;
          markers.push({ time, position: 'aboveBar', color: '#CC0000', shape: 'arrowUp', size: 2 }); // 紅色大箭頭
        }
        
        // 更新支撐線：依規則「以前三日K棒高點畫一條線」
        // 當下創新高，這裡定義「前三日」為包含今天的最高點，或昨天的前三日高？
        // 依照移動停利邏輯，通常是上移到新的防守點。
        // 這裡設定為：前兩日的高點 (Breakout point) 作為支撐
        bullSupport = refHigh; 
        bullBrokenCount = 0; // 重置跌破計數

      } else {
        // 沒有創新高，檢查是否跌破支撐
        if (bullSupport !== null) {
          if (cur.close < bullSupport) {
            bullBrokenCount++;
			
			// ⭐ 修正重點：滿 3 天就刪除 (原本是 >3)
            if (bullBrokenCount >= 3) {
              // 跌破三天 -> 刪除線
              bullSupport = null;
              bullTrend = 0;
              bullBrokenCount = 0;
            }
          } else {
            // 雖然沒創新高，但也沒跌破，或者跌破後站回 -> 重置跌破計數
            bullBrokenCount = 0;
          }
        }
      }
      bullLine.push({ time, value: bullSupport });

      // ======================================
      // 2. 空頭邏輯 (三日低點)
      // ======================================

      if (cur.close < refLow) {
        // 創新低
        if (bearTrend === 0) {
          bearTrend = 1;
          markers.push({ time, position: 'belowBar', color: '#000000', shape: 'arrowDown', text: '1' }); // 黑色
        } else {
          bearTrend = 2;
          markers.push({ time, position: 'belowBar', color: '#008000', shape: 'arrowDown', size: 2 }); // 綠色大箭頭
        }

        // 更新壓力線：前兩日低點
        bearResist = refLow;
        bearBrokenCount = 0;

      } else {
        // 沒創新低，檢查是否突破壓力
        if (bearResist !== null) {
          if (cur.close > bearResist) {
            bearBrokenCount++;
			
			// ⭐ 修正重點：滿 3 天就刪除
            if (bearBrokenCount >= 3) {
              bearResist = null;
              bearTrend = 0;
              bearBrokenCount = 0;
            }
          } else {
            bearBrokenCount = 0;
          }
        }
      }
      bearLine.push({ time, value: bearResist });
    }

    return { markers, bullLine, bearLine };
  };

  global.Strategy3Day = Strat;

})(window);