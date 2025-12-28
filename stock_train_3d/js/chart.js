// js/strategy3day.js
(function (global) {
  "use strict";

  const Strat = {};

  function getRefHigh(data, index) {
    if (index < 2) return NaN;
    return Math.max(data[index - 1].high, data[index - 2].high);
  }

  function getRefLow(data, index) {
    if (index < 2) return NaN;
    return Math.min(data[index - 1].low, data[index - 2].low);
  }

  Strat.calculate = function (data) {
    const markers = [];
    
    let bullTrend = 0; 
    let bullSupport = NaN; 
    let bullBrokenCount = 0; 

    let bearTrend = 0;
    let bearResist = NaN; 
    let bearBrokenCount = 0; 

    for (let i = 0; i < data.length; i++) {
      const cur = data[i];
      const time = cur.time;

      if (i < 2) continue;

      const refHigh = getRefHigh(data, i);
      const refLow = getRefLow(data, i);

      // --- 多頭 ---
      if (!isNaN(refHigh) && cur.close > refHigh) {
        if (bullTrend === 0) {
          bullTrend = 1;
          markers.push({ time, position: 'aboveBar', color: '#DAA520', shape: 'arrowUp', text: '1' });
        } else {
          bullTrend = 2;
          markers.push({ time, position: 'aboveBar', color: '#CC0000', shape: 'arrowUp', size: 2 });
        }
        bullSupport = refHigh; 
        bullBrokenCount = 0; 

      } else {
        if (!isNaN(bullSupport)) {
          if (cur.close < bullSupport) {
            bullBrokenCount++;
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

      // --- 空頭 ---
      if (!isNaN(refLow) && cur.close < refLow) {
        if (bearTrend === 0) {
          bearTrend = 1;
          markers.push({ time, position: 'belowBar', color: '#000000', shape: 'arrowDown', text: '1' });
        } else {
          bearTrend = 2;
          markers.push({ time, position: 'belowBar', color: '#008000', shape: 'arrowDown', size: 2 });
        }
        bearResist = refLow;
        bearBrokenCount = 0;

      } else {
        if (!isNaN(bearResist)) {
          if (cur.close > bearResist) {
            bearBrokenCount++;
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

    return { 
      markers, 
      currentBullSupport: bullSupport, 
      currentBearResist: bearResist 
    };
  };

  global.Strategy3Day = Strat;

})(window);