// [js/strategy3day.js]
(function (global) {
  "use strict";

  const Strat = {};

  // 取得前兩日的高點 (用 NaN 代表無資料)
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
    
    // 狀態變數
    let bullTrend = 0; 
    let bullSupport = NaN; // 預設 NaN
    let bullBrokenCount = 0; 

    let bearTrend = 0;
    let bearResist = NaN; // 預設 NaN
    let bearBrokenCount = 0; 

    for (let i = 0; i < data.length; i++) {
      const cur = data[i];
      const time = cur.time;

      // 前兩根略過
      if (i < 2) continue;

      const refHigh = getRefHigh(data, i);
      const refLow = getRefLow(data, i);

      // ======================================
      // 1. 多頭邏輯
      // ======================================
      if (!isNaN(refHigh) && cur.close > refHigh) {
        // 創新高
        if (bullTrend === 0) {
          bullTrend = 1;
          markers.push({ time, position: 'aboveBar', color: '#DAA520', shape: 'arrowUp', text: '1' });
        } else {
          bullTrend = 2;
          markers.push({ time, position: 'aboveBar', color: '#CC0000', shape: 'arrowUp', size: 2 });
        }
        // 更新支撐為前兩日高點
        bullSupport = refHigh; 
        bullBrokenCount = 0; 

      } else {
        // 沒創新高，檢查是否跌破
        if (!isNaN(bullSupport)) {
          if (cur.close < bullSupport) {
            bullBrokenCount++;
            // 跌破滿 3 天，刪除支撐 (變回 NaN)
            if (bullBrokenCount >= 3) {
              bullSupport = NaN;
              bullTrend = 0;      
              bullBrokenCount = 0;
            }
          } else {
            bullBrokenCount = 0;
          }
        }
      }

      // ======================================
      // 2. 空頭邏輯
      // ======================================
      if (!isNaN(refLow) && cur.close < refLow) {
        // 創新低
        if (bearTrend === 0) {
          bearTrend = 1;
          markers.push({ time, position: 'belowBar', color: '#000000', shape: 'arrowDown', text: '1' });
        } else {
          bearTrend = 2;
          markers.push({ time, position: 'belowBar', color: '#008000', shape: 'arrowDown', size: 2 });
        }
        // 更新壓力為前兩日低點
        bearResist = refLow;
        bearBrokenCount = 0;

      } else {
        // 沒創新低，檢查是否突破
        if (!isNaN(bearResist)) {
          if (cur.close > bearResist) {
            bearBrokenCount++;
            // 突破滿 3 天，刪除壓力 (變回 NaN)
            if (bearBrokenCount >= 3) {
              bearResist = NaN;
              bearTrend = 0;
              bearBrokenCount = 0;
            }
          } else {
            bearBrokenCount = 0;
          }
        }
      }
    }

    // ⭐ 重點修改：不回傳整條線陣列，只回傳「最後一根 K 棒當下的支撐壓力值」
    // 這樣 chart.js 就只會畫出一條最新的水平線
    return { 
      markers, 
      currentBullSupport: bullSupport, 
      currentBearResist: bearResist 
    };
  };

  global.Strategy3Day = Strat;

})(window);