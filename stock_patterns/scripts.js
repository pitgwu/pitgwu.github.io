// ==========================================
// 1. 型態分類索引 (Category Index)
// ==========================================
const categoryIndex = {
    // 🐂 看漲型態 (13個)
    bullish: [
        'vBottom', 'nBottom', 'hsBottom', 'complexHsBottom', 'doubleBottom', 
        'fryPanBottom', 'roundingBottom', 'ascRightTriBottom', 'descWedge', 
        'broadeningBottom', 'downBroadening', 'oneBarBottom', 'diamondBottom'
    ],
    // ⚖️ 整理型態 (17個)
    neutral: [
        'box', 'descTriPrevDrop', 'descRightTri', 'ascTriPrevRise', 'ascRightTri',
        // 快跌 (Bearish Continuation)
        'bearFlagUp', 'bearFlagFlat', 'bearFlagDown', 
        'bearPennantUp', 'bearPennantFlat', 'bearPennantDown',
        // 快漲 (Bullish Continuation)
        'bullFlagUp', 'bullFlagFlat', 'bullFlagDown', 
        'bullPennantUp', 'bullPennantFlat', 'bullPennantDown'
    ],
    // 🐻 下跌型態 (10個)
    bearish: [
        'vTop', 'nTop', 'hsTop', 'complexHsTop', 'doubleTop', 
        'roundingTop', 'ascRightTriTop', 'ascWedge', 'broadeningTop', 'diamondTop'
    ]
};

// ==========================================
// 2. 完整型態資料庫 (Patterns Database)
// ==========================================
const patternsDB = {
    // ------------------------------------------
    // A. 看漲型態 (Bullish)
    // ------------------------------------------
    vBottom: {
        name: "1. V型底 (V-Bottom) - 慣性扭轉",
        type: "bull",
        inputs: [
            { id: "neckline", label: "頸線/起跌點 (綠線)", default: 100 },
            { id: "low", label: "最低點 (V尖)", default: 70 }
        ],
        note: `
            <strong style="color: #e74c3c;">【圖解特徵】</strong>股價出現<strong>「急跌」</strong>遠離乖離，隨後在低檔出現<strong>「爆量」</strong>換手，並以同樣速度<strong>「急漲」</strong>回到起跌點(頸線)。<br>
            <strong style="color: #9b59b6;">【關鍵細節】</strong>圖中特別標註<strong>「急跌及低檔爆量」</strong>。V型反轉速度極快，通常沒有明顯築底過程，依賴籌碼的劇烈換手來扭轉慣性。<br>
            <strong>【操作戰略】</strong><br>
            1. 激進：低檔爆量收長下影線時。<br>
            2. 穩健：<strong>突破頸線(綠線)並回測不破時</strong> (圖中右側N字轉折處)。<br>
            3. 測幅：頸線至最低點的垂直距離，從頸線向上等幅投射。
        `,
        calc: (v) => {
            const h = v.neckline - v.low; // V的深度
            const target = v.neckline + h;
            
            return {
                entry: v.neckline, 
                target: target, 
                stop: v.low,
                
                // 走勢優化：模擬 "急跌 -> V底 -> 急漲 -> 突破 -> 回測 -> 噴出"
                // 減少中間的盤整點，讓線條看起來更陡峭 (Sharp)
                points: [
                    v.neckline + h*0.5, // T0: 起始高點
                    v.neckline,         // T1: 跌破頸線
                    v.neckline - h*0.6, // T2: 急跌中
                    v.low,              // T3: V底 (低檔爆量區)
                    v.neckline - h*0.4, // T4: 急漲中
                    v.neckline,         // T5: 來到頸線
                    v.neckline + h*0.2, // T6: 突破衝高
                    v.neckline,         // T7: 回測頸線 (確認支撐)
                    target              // T8: 抵達目標
                ],
                
                trendlines: [
                    // 1. 綠色頸線 (壓力轉支撐)
                    { 
                        x1: 0, x2: 8, 
                        y1: v.neckline, y2: v.neckline, 
                        color: '#2ecc71', // 圖片中的亮綠色
                        label: '頸線 (壓力轉支撐)' 
                    },
                    
                    // 2. 藍色測幅虛線 (向下測量深度)
                    { 
                        x1: 3, x2: 3, 
                        y1: v.neckline, y2: v.low, 
                        color: '#3498db', 
                        dashed: true, 
                        label: '跌幅H' 
                    },
                    
                     // 3. 藍色測幅虛線 (向上投射目標)
                     { 
                        x1: 8, x2: 8, 
                        y1: v.neckline, y2: target, 
                        color: '#3498db', 
                        dashed: true, 
                        label: '等幅H' 
                    }
                ],
                
                // 藍色突破點
                extraMarkers: [
                    {
                        type: 'point',
                        xValue: 5, // 對應 T5 (剛好碰到頸線突破)
                        yValue: v.neckline,
                        backgroundColor: '#3498db',
                        radius: 6,
                        borderColor: 'white',
                        borderWidth: 2
                    }
                ]
            };
        }
    },
    nBottom: {
        name: "2. N字底 (N-Shaped Bottom) - 等幅攻擊",
        type: "bull",
        inputs: [
            { id: "h1", label: "第一波高點 (頸線)", default: 30 },
            { id: "l1", label: "第一波低點 (起漲)", default: 20 },
            { id: "l2", label: "回檔支撐 (建議1/2處)", default: 25 }
        ],
        note: `
            <strong style="color: #e74c3c;">【圖解特徵】</strong>股價呈「N」字型攻擊。重點在於第一波上漲後，<strong>回檔修正不破前低</strong>，且通常會在漲幅的 <strong>1/2 (50%)</strong> 處獲得支撐(紫色線)，隨後再次轉強。<br>
            <strong style="color: #9b59b6;">【關鍵細節】</strong>圖中藍色箭頭展示了<strong>「等幅測量」</strong>原則：第二波漲幅(目標)通常等於第一波漲幅。<br>
            <strong>【操作戰略】</strong><br>
            1. 佈局點：回檔至 1/2 位置出現止跌訊號時。<br>
            2. 加碼點：<strong>突破前波高點(藍點處)</strong> 時。<br>
            3. 目標價：回檔低點 + 第一波漲幅。
        `,
        calc: (v) => {
            // 計算第一波漲幅高度 (Amplitude)
            const amp = v.h1 - v.l1;
            // 計算目標價 (Target) = 回檔點 + 第一波漲幅
            const target = v.l2 + amp;
            
            // 計算 1/2 位置 (用於畫紫色線)
            const halfLevel = v.l1 + amp * 0.5;
            
            return {
                entry: v.h1, 
                target: target, 
                stop: v.l2,
                
                // 走勢優化：模擬 N 字波動
                // T0: 起漲 -> T1: 高點 -> T2: 回檔(1/2) -> T3: 突破 -> T4: 達標
                points: [
                    v.l1,             // T0: 起漲 L1
                    v.h1,             // T1: 高點 H1
                    v.l2,             // T2: 回檔 L2 (理想狀態下接近 halfLevel)
                    v.h1,             // T3: 挑戰頸線
                    v.h1 + (target - v.h1) * 0.2, // T4: 突破 (藍點位置)
                    target            // T5: 抵達等幅目標
                ],
                
                trendlines: [
                    // 1. 綠色切線群
                    { x1: 0, x2: 2, y1: v.l1, y2: v.l1, color: '#2ecc71', label: '底部起漲' },
                    { x1: 0, x2: 5, y1: v.h1, y2: v.h1, color: '#2ecc71', label: '頸線壓力' },
                    
                    // 回檔支撐線 (綠色) - 穿過 T2
                    { x1: 1, x2: 4, y1: v.l2, y2: v.l2, color: '#2ecc71', label: '回檔支撐' },
                    
                    // 目標價線 (綠色)
                    { x1: 4, x2: 5, y1: target, y2: target, color: '#2ecc71', label: '目標價' },

                    // 2. 紫色 1/2 支撐線
                    // 標示出幾何上的 50% 位置，方便使用者比對回檔深度
                    { 
                        x1: 1.5, x2: 2.5, 
                        y1: halfLevel, y2: halfLevel, 
                        color: '#9b59b6', 
                        label: '1/2 關卡' 
                    },

                    // 3. 藍色等幅測量虛線 (模擬箭頭)
                    // 第一波高度 (左側)
                    { x1: 0.5, x2: 0.5, y1: v.l1, y2: v.h1, color: '#3498db', dashed: true, label: '漲幅H' },
                    // 第二波高度 (右側投影)
                    { x1: 3.5, x2: 3.5, y1: v.l2, y2: target, color: '#3498db', dashed: true, label: '等幅H' }
                ],
                
                // 藍色突破點
                extraMarkers: [
                    {
                        type: 'point',
                        xValue: 3.2, // 剛好突破頸線的位置
                        yValue: v.h1,
                        backgroundColor: '#3498db',
                        radius: 6,
                        borderColor: 'white',
                        borderWidth: 2
                    }
                ]
            };
        }
    },
    hsBottom: {
        name: "3. 頭肩底 (Head & Shoulders Bottom) - 底部反轉",
        type: "bull",
        inputs: [
            { id: "neck", label: "頸線壓力", default: 100 },
            { id: "head", label: "頭部最低點", default: 80 },
            { id: "shoulder", label: "肩部低點 (建議1/2處)", default: 90 }
        ],
        note: `
            <strong style="color: #e74c3c;">【圖解特徵】</strong>由左肩、頭部、右肩組成。特徵是中間頭部最低，左右兩肩低點大致對稱(圖中紫色線)，且深度約為頭部的 <strong>1/2</strong>。<br>
            <strong style="color: #9b59b6;">【關鍵細節】</strong>圖中藍點為突破關鍵。右側紅線顯示，突破頸線後常有<strong>「回測」</strong>動作，確認頸線由壓力轉為支撐後，才開啟主升段。<br>
            <strong>【操作戰略】</strong><br>
            1. 潛伏點：右肩回檔至左肩對稱價位(紫色線)止跌時。<br>
            2. 買點：帶量突破頸線(藍點處)時。<br>
            3. 測幅：採「垂直等幅」測量。目標價 = 頸線 + (頸線 - 頭部最低點)。
        `,
        calc: (v) => {
            // 計算頭部深度 (H)
            const h = v.neck - v.head;
            const target = v.neck + h;
            
            return {
                entry: v.neck, 
                target: target, 
                stop: v.shoulder,
                
                // 走勢優化：左肩 -> 頸線 -> 頭 -> 頸線 -> 右肩 -> 突破 -> 回測 -> 目標
                // T0: 起始
                // T1: 左肩低
                // T2: 頸線
                // T3: 頭部低
                // T4: 頸線
                // T5: 右肩低 (對稱左肩)
                // T6: 挑戰頸線
                // T7: 突破 (藍點)
                // T8: 回測
                // T9: 達標
                points: [
                    v.neck,             // T0
                    v.shoulder,         // T1 (左肩)
                    v.neck,             // T2
                    v.head,             // T3 (頭)
                    v.neck,             // T4
                    v.shoulder,         // T5 (右肩)
                    v.neck,             // T6
                    v.neck + h * 0.2,   // T7 (突破)
                    v.neck + h * 0.05,  // T8 (回測頸線)
                    target              // T9
                ],
                
                trendlines: [
                    // 1. 三條綠色水平線
                    { x1: 3, x2: 3, y1: v.head, y2: v.head, color: '#2ecc71', label: '底部' },
                    { x1: 0, x2: 9, y1: v.neck, y2: v.neck, color: '#2ecc71', label: '頸線' },
                    { x1: 8, x2: 9, y1: target, y2: target, color: '#2ecc71', label: '目標價' },

                    // 2. 紫色肩部對稱線 (1/2)
                    // 連接左肩與右肩
                    { x1: 1, x2: 5, y1: v.shoulder, y2: v.shoulder, color: '#9b59b6', label: '肩部支撐 (1/2)' },

                    // 3. 藍色等幅測距虛線
                    // 測量頭部深度 (左側)
                    { x1: 3.5, x2: 3.5, y1: v.head, y2: v.neck, color: '#3498db', dashed: true, label: '高度H' },
                    // 投射漲幅 (右側)
                    { x1: 6.5, x2: 6.5, y1: v.neck, y2: target, color: '#3498db', dashed: true, label: '等幅H' }
                ],
                
                // 藍色突破點
                extraMarkers: [
                    {
                        type: 'point',
                        xValue: 6.2, // 剛好突破頸線的位置 (T6-T7之間)
                        yValue: v.neck,
                        backgroundColor: '#3498db',
                        radius: 6,
                        borderColor: 'white',
                        borderWidth: 2
                    }
                ]
            };
        }
    },
    complexHsBottom: {
        name: "4. 複式頭肩底 (Complex H&S Bottom) - 盤整蓄力",
        type: "bull",
        inputs: [
            { id: "neck", label: "頸線 (箱頂壓力)", default: 100 },
            { id: "head", label: "頭部最低點", default: 75 },
            { id: "shoulder", label: "肩部支撐 (箱底/紫色線)", default: 88 }
        ],
        note: `
            <strong style="color: #e74c3c;">【圖解特徵】</strong>這是標準頭肩底的變形與增強版。特徵在於左右肩部不是單一低點，而是出現<strong>「K線橫盤」</strong>與<strong>「密集盤整區」</strong>。這代表主力在肩膀位置花更多時間吸籌。<br>
            <strong style="color: #9b59b6;">【關鍵細節】</strong>圖中紫色線標示 <strong>"1/2"</strong>，顯示左右肩的箱底支撐具有高度對稱性。肩部整理越久，突破後的爆發力越強。<br>
            <strong>【操作戰略】</strong><br>
            1. 觀察：右肩進入橫盤整理時，關注箱底(紫色線)的支撐力道。<br>
            2. 買點：帶量突破頸線(藍點)時。<br>
            3. 測幅：頸線 + (頸線 - 頭部最低點)。
        `,
        calc: (v) => {
            // 計算頭部深度 (H)
            const h = v.neck - v.head;
            const target = v.neck + h;
            
            return {
                entry: v.neck, 
                target: target, 
                stop: v.shoulder,
                
                // 走勢優化：模擬 "箱型左肩 -> 深V頭部 -> 箱型右肩 -> 突破"
                // 增加點位來呈現 "橫盤" (neutral) 的感覺
                points: [
                    v.neck + 5,         // T0: 起始
                    v.neck,             // T1: 進入左肩
                    v.shoulder,         // T2: 左肩箱底 (★踩紫線)
                    (v.neck+v.shoulder)/2, // T3: 左肩震盪
                    v.neck,             // T4: 左肩箱頂 (★頂綠線)
                    v.head,             // T5: 頭部最低 (深跌)
                    v.neck,             // T6: 反彈至頸線
                    (v.neck+v.shoulder)/2, // T7: 右肩震盪
                    v.shoulder,         // T8: 右肩箱底 (★踩紫線 - 1/2處)
                    v.neck - 2,         // T9: 右肩盤整
                    v.neck,             // T10: 準備突破
                    v.neck + h * 0.2,   // T11: 突破 (藍點)
                    target              // T12: 達標
                ],
                
                trendlines: [
                    // 1. 綠色頸線 (壓力)
                    // 延伸覆蓋整個形態
                    { x1: 1, x2: 11, y1: v.neck, y2: v.neck, color: '#2ecc71', label: '頸線壓力' },
                    
                    // 2. 綠色頭部底線 & 目標線
                    { x1: 5, x2: 5, y1: v.head, y2: v.head, color: '#2ecc71', label: '頭部' },
                    { x1: 11, x2: 12, y1: target, y2: target, color: '#2ecc71', label: '目標價' },

                    // 3. 紫色肩部連線 (1/2 支撐)
                    // 連接左肩箱底 (T2) 與右肩箱底 (T8)
                    { x1: 2, x2: 8, y1: v.shoulder, y2: v.shoulder, color: '#9b59b6', label: '肩部箱底 (1/2)' },
                    
                    // 4. 文字標示 (模擬圖中的 "K線橫盤" 與 "盤整")
                    // 這裡用短虛線示意箱體範圍
                    // 左肩箱體
                    { x1: 1, x2: 4, y1: v.neck, y2: v.neck, color: 'rgba(255,255,255,0.3)', dashed: true }, 
                    { x1: 1, x2: 4, y1: v.shoulder, y2: v.shoulder, color: 'rgba(255,255,255,0.3)', dashed: true },
                    // 右肩箱體
                    { x1: 6, x2: 10, y1: v.neck, y2: v.neck, color: 'rgba(255,255,255,0.3)', dashed: true },
                    { x1: 6, x2: 10, y1: v.shoulder, y2: v.shoulder, color: 'rgba(255,255,255,0.3)', dashed: true },

                    // 5. 藍色測幅虛線
                    { x1: 5, x2: 5, y1: v.head, y2: v.neck, color: '#3498db', dashed: true, label: '高度H' },
                    { x1: 11.5, x2: 11.5, y1: v.neck, y2: target, color: '#3498db', dashed: true, label: '等幅H' }
                ],
                
                // 藍色突破點
                extraMarkers: [
                    {
                        type: 'point',
                        xValue: 10.3, // 剛突破頸線的位置
                        yValue: v.neck,
                        backgroundColor: '#3498db',
                        radius: 6,
                        borderColor: 'white',
                        borderWidth: 2
                    }
                ]
            };
        }
    },
    doubleBottom: {
        name: "5. 雙椿底/W底 (Double Bottom) - 雙腳確立",
        type: "bull",
        inputs: [
            { id: "neck", label: "頸線壓力 (中間高點)", default: 60 },
            { id: "low", label: "底部低點 (支撐)", default: 50 }
        ],
        note: `
            <strong style="color: #e74c3c;">【圖解特徵】</strong>股價兩次探底，形成「W」字型。圖中綠線顯示底部有強力支撐，且兩隻腳(雙椿)確立了多頭防線。<br>
            <strong style="color: #9b59b6;">【關鍵細節】</strong>圖中特別標示<strong>「雙椿需大量」</strong>，意指在打第二隻腳或<strong>突破頸線(藍點處)</strong>時，必須有成交量明顯放大，確認主力進場。<br>
            <strong>【操作戰略】</strong><br>
            1. 買點：帶量突破頸線時。<br>
            2. 測幅：採「垂直等幅」測量(藍色虛線)。目標價 = 頸線 + (頸線 - 底部)。
        `,
        calc: (v) => {
            const h = v.neck - v.low;
            const target = v.neck + h;
            return {
                entry: v.neck,
                target: target,
                stop: v.low,
                // 走勢優化：下跌 -> 第一腳 -> 反彈 -> 第二腳 -> 突破 -> 目標
                points: [
                    v.neck + h*0.8, // 起始高點
                    v.low,          // 第一隻腳 (樁)
                    v.neck,         // 頸線
                    v.low,          // 第二隻腳 (樁)
                    v.neck,         // 挑戰頸線
                    v.neck + h*0.2, // 突破 (藍點位置)
                    target          // 達標
                ],
                trendlines: [
                    // 1. 三條綠色水平線
                    { x1: 0, x2: 4, y1: v.low, y2: v.low, color: '#2ecc71', label: '底部支撐' }, 
                    { x1: 1, x2: 5, y1: v.neck, y2: v.neck, color: '#2ecc71', label: '頸線壓力' },
                    { x1: 5, x2: 6, y1: target, y2: target, color: '#2ecc71', label: '目標價' },

                    // 2. 藍色等幅測距虛線
                    // 底部到頸線的高度
                    { x1: 2, x2: 2, y1: v.low, y2: v.neck, color: '#3498db', dashed: true, label: '高度H' },
                    // 頸線到目標的高度
                    { x1: 5.5, x2: 5.5, y1: v.neck, y2: target, color: '#3498db', dashed: true, label: '等幅H' }
                ],
                // 藍色突破點
                extraMarkers: [
                    {
                        type: 'point',
                        xValue: 4.2, // 剛好突破頸線的位置 (介於挑戰頸線和突破後之間)
                        yValue: v.neck,
                        backgroundColor: '#3498db',
                        radius: 6,
                        borderColor: 'white',
                        borderWidth: 2
                    }
                ]
            };
        }
    },
    fryPanBottom: {
        name: "6. 煎鍋底 (Fry Pan Bottom) - 圓弧築底帶柄",
        type: "bull",
        inputs: [
            { id: "neck", label: "頸線壓力 (鍋蓋)", default: 20 },
            { id: "low", label: "鍋底最低點", default: 10 },
            { id: "handle_low", label: "鍋柄回檔低點", default: 17 } // 新增鍋柄低點輸入
        ],
        note: `
            <strong style="color: #e74c3c;">【圖解特徵】</strong>股價經過長時間的圓弧底盤整，右側上漲後出現小幅回檔整理，形成「鍋柄」。整體形狀如平底鍋。<br>
            <strong style="color: #9b59b6;">【關鍵細節】</strong>鍋柄是主力洗盤的過程，量能應萎縮。圖中綠色斜線顯示早期趨勢改變，水平綠線為頸線壓力。<br>
            <strong>【操作戰略】</strong><br>
            1. 買點：帶量突破鍋柄高點(頸線)時 (圖中藍點)。<br>
            2. 測幅：採「垂直等幅」測量(藍色虛線)。目標價 = 頸線 + (頸線 - 鍋底)。
        `,
        calc: (v) => {
            const h = v.neck - v.low;
            const target = v.neck + h;
            return {
                entry: v.neck,
                target: target,
                stop: v.handle_low, // 停損設在鍋柄低點
                // 走勢優化：下跌 -> 圓弧底 -> 上漲至頸線 -> 鍋柄回檔 -> 突破 -> 目標
                points: [
                    v.neck + h*0.5, // 起始高點
                    v.neck,         // 跌破頸線位置 (雖左側無頸線，但作為參考高度)
                    v.low + h*0.2,  // 下跌中
                    v.low,          // 鍋底 (最低)
                    v.low + h*0.2,  // 築底右側
                    v.neck,         // 來到頸線 (鍋柄起點)
                    v.handle_low,   // 鍋柄回檔
                    v.neck,         // 挑戰頸線 (鍋柄終點)
                    v.neck + h*0.2, // 突破 (藍點位置)
                    target          // 達標
                ],
                trendlines: [
                    // 1. 綠色切線
                    { x1: 3, x2: 3, y1: v.low, y2: v.low, color: '#2ecc71', label: '鍋底' },
                    { x1: 5, x2: 7, y1: v.neck, y2: v.neck, color: '#2ecc71', label: '頸線 (鍋蓋)' },
                    // 模擬圖中的下降趨勢線 (示意)
                    { x1: 0, x2: 5, y1: v.neck + h*0.5, y2: v.neck, color: '#2ecc71', label: '下降壓力' }, 
                    { x1: 9, x2: 9, y1: target, y2: target, color: '#2ecc71', label: '目標價' },

                    // 2. 藍色等幅測距虛線
                    // 鍋底到頸線的高度
                    { x1: 3, x2: 3, y1: v.low, y2: v.neck, color: '#3498db', dashed: true, label: '高度H' },
                    // 頸線到目標的高度
                    { x1: 8.5, x2: 8.5, y1: v.neck, y2: target, color: '#3498db', dashed: true, label: '等幅H' }
                ],
                // 藍色突破點
                extraMarkers: [
                    {
                        type: 'point',
                        xValue: 7.5, // 剛好突破頸線的位置
                        yValue: v.neck,
                        backgroundColor: '#3498db',
                        radius: 6,
                        borderColor: 'white',
                        borderWidth: 2
                    }
                ]
            };
        }
    },
    roundingBottom: {
        name: "7. 圓弧底 (Rounding Bottom) - 長線大底",
        type: "bull",
        inputs: [
            { id: "neck", label: "頸線壓力", default: 20 },
            { id: "low", label: "圓弧最低點", default: 10 }
        ],
        note: `
            <strong style="color: #e74c3c;">【圖解特徵】</strong>股價經過長時間的平緩下跌與盤整，形成一個圓滑的碗狀底部(U型)。圖中綠線為頸線壓力。<br>
            <strong style="color: #9b59b6;">【關鍵細節】</strong>圖片顯示突破頸線後，常會出現<strong>「回測頸線」</strong>的動作(紅色虛線箭頭)，確認支撐有效後才展開主升段。<br>
            <strong>【操作戰略】</strong><br>
            1. 買點：帶量突破頸線時(藍點處)。<br>
            2. 加碼點：突破後回測頸線不破時。<br>
            3. 測幅：採「垂直等幅」測量(藍色虛線)。目標價 = 頸線 + (頸線 - 底部)。
        `,
        calc: (v) => {
            const h = v.neck - v.low;
            const target = v.neck + h;
            return {
                entry: v.neck,
                target: target,
                stop: v.low,
                // 走勢優化：緩跌 -> 平緩底部 -> 緩漲 -> 突破 -> 回測 -> 目標
                // 使用更多點位來模擬圓弧感
                points: [
                    v.neck + h*0.3, // 起始
                    v.neck - h*0.2, // 緩跌
                    v.low + h*0.1,  // 接近底部
                    v.low,          // 底部
                    v.low + h*0.1,  // 離開底部
                    v.neck - h*0.2, // 緩漲
                    v.neck,         // 抵達頸線
                    v.neck + h*0.2, // 突破噴出
                    v.neck + h*0.05,// 回測頸線 (Retest)
                    target          // 達標
                ],
                trendlines: [
                    // 1. 綠色切線
                    { x1: 0, x2: 9, y1: v.neck, y2: v.neck, color: '#2ecc71', label: '頸線 (壓力轉支撐)' },
                    { x1: 2, x2: 5, y1: v.low, y2: v.low, color: '#2ecc71', label: '底部' },

                    // 2. 藍色等幅測距虛線
                    // 底部到頸線的高度
                    { x1: 3.5, x2: 3.5, y1: v.low, y2: v.neck, color: '#3498db', dashed: true, label: '高度H' },
                    // 頸線到目標的高度 (位於回測後)
                    { x1: 8.5, x2: 8.5, y1: v.neck, y2: target, color: '#3498db', dashed: true, label: '等幅H' }
                ],
                // 藍色突破點
                extraMarkers: [
                    {
                        type: 'point',
                        xValue: 6.5, // 剛好突破頸線的位置
                        yValue: v.neck,
                        backgroundColor: '#3498db',
                        radius: 6,
                        borderColor: 'white',
                        borderWidth: 2
                    }
                ]
            };
        }
    },
    ascRightTriBottom: {
        name: "8. 上升直角三角底 (Ascending Triangle) - 多頭步步進逼",
        type: "bull",
        inputs: [
            { id: "res", label: "水平壓力線 (頂)", default: 40 },
            { id: "low", label: "三角形起點 (底)", default: 30 }
        ],
        note: `
            <strong style="color: #e74c3c;">【圖解特徵】</strong>這是一個「多頭敲門」的強勢型態：<br>
            1. <strong>平頂壓力</strong>：空方在固定價位防守(綠色水平線)，所有反彈高點皆精確對齊此線。<br>
            2. <strong>上升支撐</strong>：多方買氣逐波增強，所有回檔低點皆精確落在上升斜線上。<br>
            <strong style="color: #9b59b6;">【關鍵細節】</strong>圖中紅色虛線箭頭顯示，突破後常有<strong>「回測水平線」</strong>的動作(Throwback)。這是確認壓力轉支撐的重要訊號。<br>
            <strong>【操作戰略】</strong><br>
            1. 買點：帶量衝過水平壓力線(藍點)。<br>
            2. 加碼：回測水平線不破時。<br>
            3. 測幅：三角形最寬處的高度向上等幅投射。
        `,
        calc: (v) => {
            const h = v.res - v.low; // 三角形高度
            const target = v.res + h;
            
            // ==========================================
            // 📐 幾何運算核心
            // ==========================================
            
            // 1. 定義時間軸
            // T0:起點 | T2:墊高1 | T4:墊高2 | T7:收斂頂點
            const t_start = 0;
            const t_intersect = 7; // 假設在 T7 交會

            // 2. 建立【上升支撐線】方程式 (y = mx + c)
            // 通過 (0, low) 和 (7, res)
            const m = (v.res - v.low) / (t_intersect - t_start);
            const c = v.low;
            
            // 函數：計算任意時間點的支撐位 (精確落在斜線上)
            const getSupportPrice = (t) => (m * t) + c;

            return {
                entry: v.res,
                target: target,
                stop: getSupportPrice(2), // 停損設在第一個墊高的低點
                
                // 走勢優化：點線合一
                // T0: 起始低
                // T1: 觸頂 (平)
                // T2: 墊高 (斜)
                // T3: 觸頂 (平)
                // T4: 再墊高 (斜)
                // T5: 突破 (藍點)
                // T6: 回測 (精確踩頂 - 模擬紅虛線箭頭)
                // T7: 達標
                points: [
                    getSupportPrice(0),     // T0: 起點 (★對齊斜線)
                    v.res,                  // T1: 觸頂 (★對齊水平)
                    getSupportPrice(2),     // T2: 墊高 (★對齊斜線)
                    v.res,                  // T3: 觸頂 (★對齊水平)
                    getSupportPrice(4),     // T4: 再墊高 (★對齊斜線)
                    v.res + h * 0.25,       // T5: 突破衝高
                    v.res,                  // T6: 回測水平線 (★精確支撐確認)
                    target                  // T7: 達標
                ],
                
                trendlines: [
                    // A. 水平壓力線 (頂) - 延伸覆蓋整個過程
                    { 
                        x1: 0, x2: 7, 
                        y1: v.res, y2: v.res, 
                        color: '#2ecc71', 
                        label: '水平壓力' 
                    },
                    
                    // B. 上升支撐線 (底) - 連接低點指向交會處
                    { 
                        x1: 0, x2: 6, 
                        y1: getSupportPrice(0), 
                        y2: getSupportPrice(6), 
                        color: '#2ecc71', 
                        label: '上升支撐' 
                    },

                    // C. 目標價線
                    { x1: 6, x2: 7.5, y1: target, y2: target, color: '#2ecc71', label: '目標價' },

                    // D. 測幅虛線 (左側 H)
                    { x1: 0.2, x2: 0.2, y1: v.low, y2: v.res, color: '#3498db', dashed: true, label: '高度H' },
                    
                    // E. 測幅虛線 (右側投射)
                    { x1: 7, x2: 7, y1: v.res, y2: target, color: '#3498db', dashed: true, label: '等幅H' }
                ],
                
                // 藍色突破點
                // 我們把它放在剛突破水平線的位置 (T4 和 T5 之間)
                extraMarkers: [
                    {
                        type: 'point',
                        xValue: 4.6, 
                        yValue: v.res,
                        backgroundColor: '#3498db',
                        radius: 6,
                        borderColor: 'white',
                        borderWidth: 2
                    }
                ]
            };
        }
    },
    descWedge: {
        name: "9. 下降楔型 (Falling Wedge) - 末端收斂",
        type: "bull",
        inputs: [
            { id: "breakout", label: "突破點 (壓力線)", default: 45 },
            { id: "low", label: "楔型尖端低點", default: 35 },
            { id: "width", label: "開口高度 (H)", default: 15 }
        ],
        note: `
            <strong style="color: #e74c3c;">【圖解特徵】</strong>高點與低點同時下降，但「上方壓力線(陡)」比「下方支撐線(緩)」下降得更快，導致型態向右收斂。這代表空頭雖強，但力道正在衰竭。<br>
            <strong style="color: #9b59b6;">【關鍵細節】</strong>圖中紅色虛線箭頭顯示，突破下降趨勢線後，常有<strong>「回測」</strong>動作(Throwback)。確認支撐不破後，才是最穩健的加碼點。<br>
            <strong>【操作戰略】</strong><br>
            1. 買點：突破上方壓力線時(藍點)。<br>
            2. 測幅：採「垂直等幅」測量(藍色虛線)。目標價 = 突破點 + 楔型最寬處高度。
        `,
        calc: (v) => {
            const target = v.breakout + v.width;
            
            // ==========================================
            // 📐 雙軌幾何運算 (Falling Wedge)
            // ==========================================
            
            // 定義時間軸
            // T0:起跌 | T1:低 | T2:高 | T3:尖端低 | T4:突破 | T5:衝高 | T6:回測
            const t0 = 0;
            const t3 = 3;
            const t4 = 4;

            // 1. 建立【上方壓力線】方程式 (陡)
            // 通過 T4 (Breakout)
            const p4 = v.breakout;
            // 設定 T0 (起跌點) 的高度 = 突破點 + 開口寬度
            const p0 = v.breakout + v.width;
            
            // 計算斜率 m_high (較陡的負斜率)
            const m_high = (p4 - p0) / (t4 - t0);
            const getHighLine = (t) => p0 + m_high * (t - t0);

            // 2. 建立【下方支撐線】方程式 (緩)
            // 通過 T3 (Low)
            const p3 = v.low;
            // 設定 T1 (前低)
            // 為了收斂，支撐線斜率必須比壓力線「平緩」
            // 也就是 m_low 的絕對值要小於 m_high
            // 我們設定 m_low 為 m_high 的 40%
            const m_low = m_high * 0.4; 
            
            // 反推支撐線截距: y = mx + c => c = y - mx
            // c_low = p3 - m_low * t3
            const c_low = p3 - (m_low * t3);
            const getLowLine = (t) => (m_low * t) + c_low;

            // 3. 計算關鍵點位
            // T1 (前低): 必須在支撐線上
            const p1 = getLowLine(1);
            // T2 (前高): 必須在壓力線上
            const p2 = getHighLine(2);
            // T6 (回測點): 回到突破點附近 (模擬回測趨勢線)
            const p6 = v.breakout;

            return {
                entry: v.breakout,
                target: target,
                stop: v.low,
                
                // 走勢優化：點線合一，收斂幾何
                // T0: 起始高點
                // T1: 前低 (★對齊支撐)
                // T2: 前高 (★對齊壓力)
                // T3: 尖端低 (★對齊支撐)
                // T4: 突破 (★對齊壓力 - 藍點)
                // T5: 衝高
                // T6: 回測 (模擬紅色虛線箭頭)
                // T7: 達標
                points: [
                    p0,                 // T0
                    p1,                 // T1
                    p2,                 // T2
                    p3,                 // T3
                    p4,                 // T4
                    p4 + v.width * 0.25,// T5
                    p6,                 // T6 (回測)
                    target              // T7
                ],
                
                trendlines: [
                    // A. 上方壓力線 (陡) - 連接 T0 -> T4
                    { 
                        x1: 0, x2: 4.5, 
                        y1: p0, y2: getHighLine(4.5), 
                        color: '#2ecc71', 
                        label: '下降壓力 (陡)' 
                    },
                    
                    // B. 下方支撐線 (緩) - 連接 T1 -> T3 -> 延伸顯示收斂
                    { 
                        x1: 0.5, x2: 6, 
                        y1: getLowLine(0.5), y2: getLowLine(6), 
                        color: '#2ecc71', 
                        label: '收斂支撐 (緩)' 
                    },

                    // C. 目標價線
                    { x1: 6, x2: 7.5, y1: target, y2: target, color: '#2ecc71', label: '目標價' },

                    // D. 測幅虛線 (左側開口 H)
                    // 測量 T0 到 對應下方的距離
                    { x1: 0.2, x2: 0.2, y1: getLowLine(0), y2: p0, color: '#3498db', dashed: true, label: '高度H' },
                    
                    // E. 測幅虛線 (右側投射)
                    { x1: 7, x2: 7, y1: p4, y2: target, color: '#3498db', dashed: true, label: '等幅H' }
                ],
                
                // 藍色突破點
                extraMarkers: [
                    {
                        type: 'point',
                        xValue: 4, // T4
                        yValue: p4,
                        backgroundColor: '#3498db',
                        radius: 6,
                        borderColor: 'white',
                        borderWidth: 2
                    }
                ]
            };
        }
    },
    broadeningBottom: {
        name: "10. 放射擴張喇叭底 (Broadening Bottom) - 波動爆發",
        type: "bull",
        inputs: [
            { id: "breakout", label: "突破點 (壓力線)", default: 60 },
            { id: "low", label: "最後低點 (支撐線)", default: 40 },
            { id: "amp", label: "最後一波振幅 (H)", default: 20 }
        ],
        note: `
            <strong style="color: #e74c3c;">【圖解特徵】</strong>高點一波比一波高，低點一波比一波低，形成向右開口的喇叭狀。這代表市場情緒從猶豫轉為極度激動，籌碼正在大換手。<br>
            <strong style="color: #9b59b6;">【關鍵細節】</strong>圖中紫色線標示最後一波攻擊的<strong>「1/2 位置」</strong>。這是多頭反攻的中繼站。此外，突破擴張壓力線後，常有<strong>「回測」</strong>動作(紅色虛線)，是確認買點。<br>
            <strong>【操作戰略】</strong><br>
            1. 買點：帶量突破上方擴張壓力線(藍點)。<br>
            2. 測幅：採「垂直等幅」測量。目標價 = 突破點 + 最後一波振幅。
        `,
        calc: (v) => {
            const target = v.breakout + v.amp;
            
            // ==========================================
            // 📐 雙軌幾何運算 (Broadening)
            // ==========================================

            // 定義時間軸
            // T1:前低 | T2:前高 | T3:最低 | T4:衝過1/2 | T6:突破 | T7:回測
            const t2 = 2; // 前高
            const t3 = 3; // 最低
            const t6 = 6; // 突破點 (藍點)

            // 1. 建立【上方壓力線】方程式 (y = m_high * x + c_high)
            // 通過 T6 (Breakout)
            // 為了畫出擴張，T2 (前高) 必須比 T6 低
            // 設定 T2 比 T6 低 30% 的振幅
            const p6 = v.breakout;
            const p2 = v.breakout - (v.amp * 0.3); 
            
            // 計算斜率 m_high (正斜率)
            const m_high = (p6 - p2) / (t6 - t2);
            const getHighLine = (t) => p2 + m_high * (t - t2);

            // 2. 建立【下方支撐線】方程式 (y = m_low * x + c_low)
            // 通過 T3 (Low)
            // 為了畫出擴張，T1 (前低) 必須比 T3 高
            const p3 = v.low;
            const p1 = v.low + (v.amp * 0.3); 
            const t1 = 1;

            // 計算斜率 m_low (負斜率)
            const m_low = (p3 - p1) / (t3 - t1);
            const getLowLine = (t) => p1 + m_low * (t - t1);

            // 3. 計算 1/2 關鍵位
            const halfLevel = v.low + (v.breakout - v.low) * 0.5;

            // 4. 計算回測點 (T7)
            // 突破後回踩延伸的壓力線
            const t_retest = 7.5;
            const p_retest = getHighLine(t_retest);

            return {
                entry: v.breakout,
                target: target,
                stop: v.low,
                
                // 走勢優化：點線合一
                // T0: 起始
                // T1: 前低 (★對齊支撐)
                // T2: 前高 (★對齊壓力)
                // T3: 最低 (★對齊支撐)
                // T4: 反彈至 1/2 附近震盪
                // T5: 續攻
                // T6: 突破 (★對齊壓力 - 藍點)
                // T7: 衝高
                // T8: 回測 (★精確踩在壓力線上 - 模擬紅虛線)
                // T9: 達標
                points: [
                    getHighLine(0.5),   // T0
                    p1,                 // T1
                    p2,                 // T2
                    p3,                 // T3
                    halfLevel,          // T4 (經過 1/2)
                    v.breakout - 2,     // T5 (接近突破)
                    p6,                 // T6 (突破)
                    p6 + v.amp * 0.2,   // T7 (衝高)
                    p_retest,           // T8 (回測延伸壓力線)
                    target              // T9
                ],
                
                trendlines: [
                    // A. 上方擴張壓力線 (連接 T2 -> T6 -> 延伸)
                    { 
                        x1: 1.5, x2: 8, 
                        y1: getHighLine(1.5), y2: getHighLine(8), 
                        color: '#2ecc71', 
                        label: '擴張壓力' 
                    },
                    
                    // B. 下方擴張支撐線 (連接 T1 -> T3)
                    { 
                        x1: 0.5, x2: 4, 
                        y1: getLowLine(0.5), y2: getLowLine(4), 
                        color: '#2ecc71', 
                        label: '擴張支撐' 
                    },
                    
                    // C. 1/2 關鍵位 (紫色)
                    { x1: 3, x2: 6, y1: halfLevel, y2: halfLevel, color: '#9b59b6', label: '1/2 關卡' },

                    // D. 目標價線
                    { x1: 8.5, x2: 9.5, y1: target, y2: target, color: '#2ecc71', label: '目標價' },

                    // E. 測幅虛線 (中間振幅 H)
                    { x1: 4.5, x2: 4.5, y1: v.low, y2: getHighLine(4.5), color: '#3498db', dashed: true, label: '振幅H' },
                    
                    // F. 測幅虛線 (右側投射 H)
                    { x1: 9, x2: 9, y1: p6, y2: target, color: '#3498db', dashed: true, label: '等幅H' }
                ],
                
                // 藍色突破點
                extraMarkers: [
                    {
                        type: 'point',
                        xValue: 6, // T6
                        yValue: p6,
                        backgroundColor: '#3498db',
                        radius: 6,
                        borderColor: 'white',
                        borderWidth: 2
                    }
                ]
            };
        }
    },
    downBroadening: {
        name: "11. 向下擴張喇叭底 (Descending Broadening) - 末端蓄力",
        type: "bull",
        inputs: [
            { id: "breakout", label: "突破點 (壓力線)", default: 50 },
            { id: "low", label: "最後低點 (支撐線)", default: 40 },
            { id: "amp", label: "最後一波振幅 (H)", default: 15 }
        ],
        note: `
            <strong style="color: #e74c3c;">【圖解特徵】</strong>兩條綠色趨勢線同時向下，但下方支撐線跌勢更猛(更陡)，形成擴張狀。這通常發生在空頭末端的非理性殺盤。<br>
            <strong style="color: #9b59b6;">【關鍵細節】</strong>請注意圖中紫色線標示的<strong>「1/2」</strong>。股價在觸碰壓力線後，回檔<strong>不再破底</strong>，而是守在漲幅的 1/2 處蓄力。這是多頭接管戰場的訊號。<br>
            <strong>【操作戰略】</strong><br>
            1. 潛伏點：回測 1/2 紫色線不破時。<br>
            2. 買點：帶量突破上方壓力線(藍點)。<br>
            3. 測幅：突破點 + 最後一波振幅(藍色虛線)。
        `,
        calc: (v) => {
            const target = v.breakout + v.amp;
            
            // ==========================================
            // 📐 雙軌幾何運算
            // ==========================================
            
            // 定義時間軸
            // T1:前低 | T2:前高 | T3:最低 | T4:觸壓(蓄力起點) | T5:回測1/2 | T6:突破
            const t2 = 2; // 前高
            const t3 = 3; // 最低
            const t4 = 4; // 觸壓
            const t6 = 6; // 突破

            // 1. 建立【上方壓力線】方程式 (y = m_high * x + c_high)
            // 通過 T6 (Breakout)
            // 設定斜率為負 (向下)，但較緩
            const p6 = v.breakout;
            // 假設 T2 (前高) 比 T6 高 (因為是向下趨勢)
            // 設定 T2 比 T6 高出振幅的 20%
            const p2 = v.breakout + (v.amp * 0.2); 
            
            const m_high = (p6 - p2) / (t6 - t2); // 負斜率
            const getHighLine = (t) => p2 + m_high * (t - t2);

            // 2. 建立【下方支撐線】方程式 (y = m_low * x + c_low)
            // 通過 T3 (Low)
            // 斜率要比上方更陡 (向下擴張)
            const p3 = v.low;
            // T1 (前低) 比 T3 高
            // 且擴張幅度要夠明顯
            const p1 = v.low + (v.amp * 0.4); 
            const t1 = 1;

            const m_low = (p3 - p1) / (t3 - t1); // 負斜率 (更陡)
            const getLowLine = (t) => p1 + m_low * (t - t1);

            // 3. 計算關鍵點位：T4 (突破前的反彈觸壓)
            // T4 必須剛好打在壓力線上
            const p4 = getHighLine(t4);

            // 4. 計算 1/2 中關 (蓄力點)
            // 這是從 T3(低) 到 T4(高) 這一段反彈的 1/2
            // 公式: p3 + (p4 - p3) * 0.5
            const halfLevel = p3 + (p4 - p3) * 0.5;

            return {
                entry: v.breakout,
                target: target,
                stop: v.low,
                
                // 走勢優化：點線合一，完美演繹蓄力突破
                // T0: 起始
                // T1: 前低 (★貼支撐)
                // T2: 前高 (★貼壓力)
                // T3: 最低 (★貼支撐)
                // T4: 觸壓 (★貼壓力 - 準備蓄力)
                // T5: 1/2 (★踩紫線 - Higher Low)
                // T6: 突破 (藍點)
                // T7: 達標
                points: [
                    getHighLine(0.5),   // T0
                    p1,                 // T1: 前低
                    p2,                 // T2: 前高
                    p3,                 // T3: 最低點
                    p4,                 // T4: 觸碰壓力線 (High)
                    halfLevel,          // T5: 回測 1/2 (Higher Low)
                    p6,                 // T6: 突破壓力線 (藍點)
                    p6 + v.amp * 0.2,   // T7: 衝高
                    p6,                 // T8: 回測突破點
                    target              // T9: 達標
                ],
                
                trendlines: [
                    // A. 上方壓力線 (連接 T2 -> T4 -> T6)
                    { 
                        x1: 1.5, x2: 7, 
                        y1: getHighLine(1.5), y2: getHighLine(7), 
                        color: '#2ecc71', 
                        label: '向下壓力' 
                    },
                    
                    // B. 下方支撐線 (連接 T1 -> T3)
                    { 
                        x1: 0.5, x2: 4, 
                        y1: getLowLine(0.5), y2: getLowLine(4), 
                        color: '#2ecc71', 
                        label: '向下支撐 (陡)' 
                    },
                    
                    // C. 1/2 關鍵蓄力位 (紫色)
                    // 畫在 T4 和 T6 之間，位於壓力線下方
                    { x1: 4, x2: 6, y1: halfLevel, y2: halfLevel, color: '#9b59b6', label: '1/2 蓄力' },

                    // D. 目標價線
                    { x1: 8, x2: 9, y1: target, y2: target, color: '#2ecc71', label: '目標價' },

                    // E. 測幅虛線 (左側 H)
                    { x1: 3, x2: 3, y1: p3, y2: getHighLine(3), color: '#3498db', dashed: true, label: '振幅H' },
                    
                    // F. 測幅虛線 (右側投射)
                    { x1: 8.5, x2: 8.5, y1: p6, y2: target, color: '#3498db', dashed: true, label: '等幅H' }
                ],
                
                // 藍色突破點
                extraMarkers: [
                    {
                        type: 'point',
                        xValue: 6, // T6
                        yValue: p6,
                        backgroundColor: '#3498db',
                        radius: 6,
                        borderColor: 'white',
                        borderWidth: 2
                    }
                ]
            };
        }
    },
    oneBarBottom: {
        name: "12. 一字底 (One-Bar Bottom) - 橫盤爆發",
        type: "bull",
        inputs: [
            { id: "boxHigh", label: "盤整區高點 (壓力)", default: 35 },
            { id: "boxLow", label: "盤整區低點 (支撐)", default: 30 }
        ],
        note: `
            <strong style="color: #e74c3c;">【圖解特徵】</strong>股價進入一個極度狹窄的箱體，如死水般波動極小。圖中強調<strong>「狹幅盤整 2 個月以上」</strong>，時間越長，籌碼換手越乾淨，爆發力越強。<br>
            <strong style="color: #9b59b6;">【關鍵細節】</strong>這是一個耐力戰。圖中藍點為突破訊號，突破後常伴隨<strong>回測箱頂</strong>(紅色箭頭處)，這是最後的上車機會。<br>
            <strong>【操作戰略】</strong><br>
            1. 觀望：盤整期間資金效率極低，不建議進場。<br>
            2. 買點：帶量突破箱體上緣(藍點)。<br>
            3. 測幅：橫盤有多長，豎起來就有多高 (長期目標)。
        `,
        calc: (v) => {
            const range = v.boxHigh - v.boxLow;
            const target = v.boxHigh + range * 2; // 橫盤越久，漲幅通常越大
            
            return {
                entry: v.boxHigh,
                target: target,
                stop: v.boxLow,
                
                // 走勢優化：模擬漫長的 "2個月" 盤整
                // 使用多個點位來回震盪，且精確對齊上下緣
                points: [
                    v.boxHigh + range * 2,   // T0: 下跌入場
                    v.boxLow,                // T1: 踩底 (★對齊)
                    v.boxHigh,               // T2: 觸頂 (★對齊)
                    v.boxLow,                // T3: 踩底 (★對齊)
                    v.boxHigh,               // T4: 觸頂 (★對齊)
                    v.boxLow,                // T5: 踩底 (★對齊)
                    v.boxHigh,               // T6: 觸頂 (★對齊)
                    v.boxLow,                // T7: 踩底 (★對齊)
                    v.boxHigh,               // T8: 觸頂 (★對齊)
                    v.boxLow,                // T9: 踩底 (★對齊)
                    v.boxHigh,               // T10: 觸頂 (準備突破)
                    v.boxLow + range * 0.5,  // T11: 最後蹲跳 (蓄力)
                    v.boxHigh,               // T12: 突破 (藍點)
                    v.boxHigh + range * 0.3, // T13: 衝高
                    v.boxHigh,               // T14: 回測箱頂 (★精確支撐確認)
                    target                   // T15: 噴出達標
                ],
                
                trendlines: [
                    // A. 箱體上緣 (壓力) - 延伸覆蓋整個盤整區
                    { 
                        x1: 1, x2: 12, 
                        y1: v.boxHigh, y2: v.boxHigh, 
                        color: '#2ecc71', 
                        label: '箱體壓力' 
                    },
                    
                    // B. 箱體下緣 (支撐)
                    { 
                        x1: 1, x2: 12, 
                        y1: v.boxLow, y2: v.boxLow, 
                        color: '#2ecc71', 
                        label: '箱體支撐' 
                    },

                    // C. 目標價線
                    { x1: 14, x2: 15, y1: target, y2: target, color: '#2ecc71', label: '目標價' },
                    
                    // D. 時間標示 (模擬圖中的文字概念)
                    { 
                        x1: 2, x2: 10, 
                        y1: (v.boxHigh + v.boxLow)/2, y2: (v.boxHigh + v.boxLow)/2, 
                        color: 'rgba(155, 89, 182, 0.5)', 
                        dashed: true, 
                        label: '盤整2個月以上' 
                    }
                ],
                
                // 藍色突破點
                extraMarkers: [
                    {
                        type: 'point',
                        xValue: 12, // T12
                        yValue: v.boxHigh,
                        backgroundColor: '#3498db',
                        radius: 6,
                        borderColor: 'white',
                        borderWidth: 2
                    }
                ]
            };
        }
    },
    diamondBottom: {
        name: "13. 菱形底 (Diamond Bottom) - 混亂轉折",
        type: "bull",
        inputs: [
            { id: "breakout", label: "突破點價格", default: 50 },
            { id: "midHigh", label: "菱形最高點", default: 55 },
            { id: "midLow", label: "菱形最低點", default: 35 }
        ],
        note: `
            <strong style="color: #e74c3c;">【圖解特徵】</strong>這是一個結合「擴張喇叭」與「對稱三角」的稀有型態，形狀如鑽石。代表市場從「極度混亂(左半)」轉為「冷靜觀望(右半)」，是強烈反轉訊號。<br>
            <strong style="color: #9b59b6;">【關鍵細節】</strong>圖中右側顯示，突破右上方的壓力線後，常有<strong>「回測」</strong>動作(紅色虛線箭頭)。目標價計算方式為「菱形最寬處」的垂直高度。<br>
            <strong>【操作戰略】</strong><br>
            1. 觀望：菱形內部多空不明，切勿追價。<br>
            2. 買點：帶量突破右上方壓力線(藍點)。<br>
            3. 測幅：突破點 + 菱形中間最大振幅。
        `,
        calc: (v) => {
            const height = v.midHigh - v.midLow;
            const p_center = (v.midHigh + v.midLow) / 2;

            // ==========================================
            // 📐 菱形幾何運算 (跌勢入場版)
            // ==========================================

            // 定義時間軸
            // 幾何起點設在 t=0.5 (讓 T0 可以畫在 t=0 的高處)
            const t_geom_start = 0.5; 
            const t_top = 3;    // T3: 頂點
            const t_btm = 4;    // T4: 底點
            const t_conv = 11;  // 收斂點

            // --- 1. 左側擴張方程式 (從 0.5 開始) ---
            // 左上線: (0.5, p_center) -> (3, midHigh)
            const m_lu = (v.midHigh - p_center) / (t_top - t_geom_start);
            const getLeftUpper = (t) => p_center + m_lu * (t - t_geom_start);

            // 左下線: (0.5, p_center) -> (4, midLow)
            const m_ld = (v.midLow - p_center) / (t_btm - t_geom_start);
            const getLeftLower = (t) => p_center + m_ld * (t - t_geom_start);

            // --- 2. 右側收斂方程式 ---
            // 右上線: (3, midHigh) -> (11, p_center)
            const m_ru = (p_center - v.midHigh) / (t_conv - t_top);
            const getRightUpper = (t) => v.midHigh + m_ru * (t - t_top);

            // 右下線: (4, midLow) -> (11, p_center)
            const m_rd = (p_center - v.midLow) / (t_conv - t_btm);
            const getRightLower = (t) => v.midLow + m_rd * (t - t_btm);


            // --- 3. 計算點位 ---
            
            // T0: 入場點 (人為設定比 T1 高，模擬跌勢)
            // 不代入方程式，直接設在 LeftUpper(1) 之上
            const p1 = getLeftUpper(1);
            const p0 = p1 + (v.midHigh - v.midLow) * 0.3; 

            // 其他點位代入方程式 (保持對齊)
            const p2 = getLeftLower(2);
            const p3 = v.midHigh;
            const p4 = v.midLow;
            const p5 = getRightUpper(5); // T5: Lower High
            const p6 = getRightLower(6); // T6: Higher Low
            const p_entry = getRightUpper(7); // Entry
            const target = p_entry + height;
            const p_retest = getRightUpper(7.5);

            return {
                entry: p_entry,
                target: target,
                stop: v.midLow,
                
                // points 對應:
                // T0: 入場 (高)
                // T1: 左上碰線
                // T2: 左下碰線
                // T3: 頂
                // T4: 底
                // T5: 右高 (貼線)
                // T6: 右低 (貼線)
                // T7: 突破 (貼線)
                points: [
                    p0,             // T0: ★高於 T1 (跌勢入場)
                    p1,             // T1: ★對齊左上
                    p2,             // T2: ★對齊左下
                    p3,             // T3: ★對齊頂
                    p4,             // T4: ★對齊底
                    p5,             // T5: ★對齊右上
                    p6,             // T6: ★對齊右下
                    p_entry,        // T7: ★對齊右上 (突破)
                    p_entry + height*0.2, 
                    p_retest,       // T9: 回測
                    target          // T10
                ],
                
                trendlines: [
                    // A. 左上邊界 (從 0.5 開始畫)
                    { x1: 0.5, x2: 3, y1: p_center, y2: v.midHigh, color: '#2ecc71', label: '擴張' },
                    
                    // B. 左下邊界 (從 0.5 開始畫)
                    { x1: 0.5, x2: 4, y1: p_center, y2: v.midLow, color: '#2ecc71' },
                    
                    // C. 右上邊界
                    { x1: 3, x2: 8, y1: v.midHigh, y2: getRightUpper(8), color: '#2ecc71', label: '收斂壓力' },
                    
                    // D. 右下邊界
                    { x1: 4, x2: 8, y1: v.midLow, y2: getRightLower(8), color: '#2ecc71', label: '收斂支撐' },

                    // E. 目標價
                    { x1: 8, x2: 9, y1: target, y2: target, color: '#2ecc71', label: '目標價' },

                    // F. 測幅 H
                    { x1: 3.5, x2: 3.5, y1: v.midLow, y2: v.midHigh, color: '#3498db', dashed: true, label: '高度H' },
                    
                    // G. 投射 H
                    { x1: 7.5, x2: 7.5, y1: p_entry, y2: target, color: '#3498db', dashed: true, label: '等幅H' }
                ],
                
                extraMarkers: [
                    {
                        type: 'point',
                        xValue: 7, 
                        yValue: p_entry,
                        backgroundColor: '#3498db',
                        radius: 6,
                        borderColor: 'white',
                        borderWidth: 2
                    }
                ]
            };
        }
    },

    // ------------------------------------------
    // B. 整理型態 (neutral)
    // ------------------------------------------
    box: {
        name: "1. 箱型整理 (Rectangle) - 區間震盪",
        type: "neutral", // 改為中性，代表方向未定
        inputs: [
            { id: "boxHigh", label: "箱體頂部 (壓力)", default: 50 },
            { id: "boxLow", label: "箱體底部 (支撐)", default: 40 }
        ],
        note: `
            <strong style="color: #e74c3c;">【圖解特徵】</strong>股價限制在兩條平行線之間，多空力量暫時均衡。圖左顯示股價急跌後進入整理，但後市方向未定。<br>
            <strong style="color: #9b59b6;">【關鍵細節】</strong>此型態為「中性」。圖中右側顯示了<strong>雙向劇本</strong>：可能向上突破，也可能向下破底。務必等待方向確認。<br>
            <strong>【操作戰略 (雙軌)】</strong><br>
            1. <strong>多方劇本</strong>：突破箱頂(藍點)進場。目標價 = 箱頂 + 箱高(H)。<br>
            2. <strong>空方劇本</strong>：跌破箱底放空。目標價 = 箱底 - 箱高(H)。<br>
            3. 測幅：不論方向，滿足點皆為「一倍箱體高度」。
        `,
        calc: (v) => {
            const height = v.boxHigh - v.boxLow;
            const targetBull = v.boxHigh + height; // 多方目標
            const targetBear = v.boxLow - height;  // 空方目標
            
            // ==========================================
            // 📐 雙向幾何運算
            // ==========================================
            
            return {
                entry: v.boxHigh, // 預設顯示多方突破點
                target: targetBull,
                stop: v.boxLow,
                
                // 走勢優化：急跌入場 -> 箱內震盪 -> 來到關鍵決策點
                // T0: 入場
                // T1~T5: 碰觸上下緣 (幾何對齊)
                // T6: 決策點 (Decision Point)
                // T7: 多方路徑 (實線)
                // T8: 多方達標
                points: [
                    v.boxHigh + height * 0.8, // T0: 急跌入場
                    v.boxLow,                 // T1: 測支撐 (★對齊)
                    v.boxHigh,                // T2: 測壓力 (★對齊)
                    v.boxLow,                 // T3: 測支撐 (★對齊)
                    v.boxHigh,                // T4: 測壓力 (★對齊)
                    v.boxLow,                 // T5: 測支撐 (★對齊)
                    (v.boxHigh + v.boxLow)/2, // T6: 回到中間 (觀望期)
                    v.boxHigh,                // T7: 準備測試箱頂
                    v.boxHigh + height * 0.3, // T8: 假定向上突破 (示意)
                    targetBull                // T9: 達標
                ],
                
                trendlines: [
                    // A. 箱體上緣 (壓力)
                    { x1: 1, x2: 7, y1: v.boxHigh, y2: v.boxHigh, color: '#2ecc71', label: '箱頂壓力' },
                    
                    // B. 箱體下緣 (支撐)
                    { x1: 1, x2: 7, y1: v.boxLow, y2: v.boxLow, color: '#2ecc71', label: '箱底支撐' },

                    // C. 多方目標線 (上方)
                    { x1: 7, x2: 9, y1: targetBull, y2: targetBull, color: '#e74c3c', label: '多方目標 (+H)' },

                    // D. 空方目標線 (下方)
                    { x1: 7, x2: 9, y1: targetBear, y2: targetBear, color: '#2ecc71', label: '空方目標 (-H)' },

                    // E. 測幅虛線 (箱內高度 H)
                    { x1: 3.5, x2: 3.5, y1: v.boxLow, y2: v.boxHigh, color: '#3498db', dashed: true, label: '高度H' },
                    
                    // F. 多方路徑示意 (藍色虛線)
                    { x1: 7, x2: 7, y1: v.boxHigh, y2: targetBull, color: '#3498db', dashed: true, label: '向上測幅' },
                    
                    // G. 空方路徑示意 (藍色虛線 - 向下)
                    // 從箱底畫到空方目標，模擬圖片中的向下箭頭
                    { x1: 7, x2: 7, y1: v.boxLow, y2: targetBear, color: '#3498db', dashed: true, label: '向下測幅' },

                    // H. 空方走勢模擬 (紅色虛線)
                    // 為了讓使用者看到另一種可能，我們畫一條隱約的跌破線
                    { x1: 6, x2: 6.5, y1: (v.boxHigh+v.boxLow)/2, y2: v.boxLow, color: 'rgba(231, 76, 60, 0.5)', dashed: true },
                    { x1: 6.5, x2: 7.5, y1: v.boxLow, y2: targetBear, color: 'rgba(231, 76, 60, 0.5)', dashed: true }
                ],
                
                // 標示兩個關鍵突破點
                extraMarkers: [
                    // 多方突破點 (藍點)
                    {
                        type: 'point',
                        xValue: 7.2, // 約略位置
                        yValue: v.boxHigh,
                        backgroundColor: '#3498db',
                        radius: 5,
                        borderColor: 'white',
                        borderWidth: 2
                    },
                    // 空方跌破點 (灰點/紅點示意)
                    {
                        type: 'point',
                        xValue: 6.5, 
                        yValue: v.boxLow,
                        backgroundColor: '#95a5a6', // 灰色代表另一種可能
                        radius: 4,
                        borderColor: 'white',
                        borderWidth: 1
                    }
                ]
            };
        }
    },
	descTriPrevDrop: {
        name: "2. 前跌三角形 (Descending Triangle/Wedge) - 跌勢收斂",
        type: "bear", // 定義為中性偏空，等待方向
        inputs: [
            { id: "high", label: "開口高點 (壓力)", default: 50 },
            { id: "low", label: "開口低點 (支撐)", default: 35 },
            { id: "duration", label: "收斂長度", default: 8 }
        ],
        note: `
            <strong style="color: #e74c3c;">【圖解特徵】</strong>股價經歷一段急跌後，波幅開始縮小。高點越來越低(壓力線下降)，低點也緩步走低或持平，形成收斂三角形。這代表市場正在觀望。<br>
            <strong style="color: #9b59b6;">【關鍵細節】</strong>此為<strong>「中性偏空」</strong>型態。圖中顯示突破方向未定，因此必須設定<strong>「雙向劇本」</strong>。直到帶量突破其中一條線，方向才算確立。<br>
            <strong>【操作戰略 (雙軌)】</strong><br>
            1. <strong>多方目標</strong>：突破上方壓力線進場。目標 = 突破點 + 開口高度(H)。<br>
            2. <strong>空方目標</strong>：跌破下方支撐線進場。目標 = 跌破點 - 開口高度(H)。<br>
            3. 測幅：依據圖中藍色虛線，取三角形最左側開口的高度做等幅測量。
        `,
        calc: (v) => {
            const height = v.high - v.low; // 開口 H
            
            // 時間軸
            const t_break = 7; // 收斂末端
            const t_target = v.duration - 1;

            // 1. 建立幾何方程式
            // 設收斂末端開口剩 20%
            const spread_end = height * 0.2;
            const mid = (v.high + v.low) / 2;
            const res_end = mid + spread_end / 2;
            const sup_end = mid - spread_end / 2;
            
            // 壓力線 (Top)
            const m_top = (res_end - v.high) / t_break;
            const getTopLine = (t) => v.high + m_top * t;

            // 支撐線 (Btm)
            const m_btm = (sup_end - v.low) / t_break;
            const getBtmLine = (t) => v.low + m_btm * t;

            // 2. 計算目標價
            const breakPrice = mid; 
            const targetBull = breakPrice + height;
            const targetBear = breakPrice - height;

            // 3. 建構 K 線
            let chartPoints = [];
            
            // 前跌段 (從上跌下來)
            chartPoints[0] = v.high + (height * 0.5); 
            
            // 收斂震盪 (幾何對齊)
            chartPoints[1] = v.low;         // T1: 碰底
            chartPoints[2] = getTopLine(2); // T2: 碰頂
            chartPoints[3] = getBtmLine(3); // T3: 碰底
            chartPoints[4] = getTopLine(4); // T4: 碰頂
            chartPoints[5] = getBtmLine(5); // T5: 碰底
            chartPoints[6] = getTopLine(6); // T6: 碰頂
            chartPoints[7] = breakPrice;    // T7: 收斂中心

            // 填充空白以顯示預測線
            for (let i = 8; i <= t_target; i++) {
                chartPoints.push(null); 
            }

            return {
                entry: breakPrice, // 系統運算用，但不顯示 Marker
                target: targetBull,
                stop: sup_end,
                
                points: chartPoints,
                
                trendlines: [
                    // A. 壓力線
                    { x1: 1, x2: t_break, y1: v.low, y2: sup_end, color: '#2ecc71', label: '收斂支撐' },
                    // 為了美觀，從 T0 之後開始畫壓力
                    { x1: 0.5, x2: t_break, y1: v.high, y2: res_end, color: '#2ecc71', label: '收斂壓力' },

                    // B. 前跌趨勢線 (T0 -> T1)
                    { x1: 0, x2: 1, y1: chartPoints[0], y2: v.low, color: '#2ecc71', label: '前跌段' },

                    // C. 目標價線-多
                    { x1: t_break, x2: t_target, y1: targetBull, y2: targetBull, color: '#e74c3c', label: '目標價-多' },
                    
                    // D. 目標價線-空
                    { x1: t_break, x2: t_target, y1: targetBear, y2: targetBear, color: '#2ecc71', label: '目標價-空' },

                    // E. 測幅 H
                    { x1: 1, x2: 1, y1: v.low, y2: v.high, color: '#3498db', dashed: true, label: '高度H' },
                    
                    // F. 多方路徑 (虛線)
                    { x1: t_break, x2: t_target, y1: breakPrice, y2: targetBull, color: '#e74c3c', dashed: true, label: '突破' },
                    
                    // G. 空方路徑 (虛線)
                    { x1: t_break, x2: t_target, y1: breakPrice, y2: targetBear, color: '#2ecc71', dashed: true, label: '跌破' }
                ],
                
                extraMarkers: [
                    // ★ 移除了決策點 (Entry Point)
                    
                    // 1. 多方目標點 (紅色)
                    {
                        type: 'point',
                        xValue: t_target,
                        yValue: targetBull,
                        backgroundColor: '#e74c3c',
                        radius: 8,
                        borderColor: 'white',
                        borderWidth: 2,
                        label: '多方'
                    },
                    // 2. 空方目標點 (綠色)
                    {
                        type: 'point',
                        xValue: t_target,
                        yValue: targetBear,
                        backgroundColor: '#2ecc71',
                        radius: 8,
                        borderColor: 'white',
                        borderWidth: 2,
                        label: '空方'
                    }
                ]
            };
        }
    },
    descRightTri: {
        name: "3. 下跌直角三角形 (Descending Triangle) - 賣壓測試",
        type: "bear", // 中性偏空型態
        inputs: [
            { id: "high", label: "開口高點 (起跌)", default: 50 },
            { id: "flatLow", label: "水平支撐 (底)", default: 35 },
            { id: "duration", label: "收斂長度", default: 8 }
        ],
        note: `
            <strong style="color: #e74c3c;">【圖解特徵】</strong>這是一個「空方步步進逼」的型態。下方支撐是一條水平線(多頭防守)，但上方高點不斷降低(空方壓價)。<br>
            <strong style="color: #9b59b6;">【關鍵細節】</strong>此為<strong>「中性偏空」</strong>型態。雖然名為下跌三角，但若水平支撐不破，市場可能反轉。圖中藍色虛線顯示，無論是往上突破或往下跌破，<strong>目標價皆為一個開口高度(H)</strong>。<br>
            <strong>【操作戰略 (雙軌)】</strong><br>
            1. <strong>多方劇本</strong>：帶量突破下降壓力線。目標 = 突破點 + 開口高度。<br>
            2. <strong>空方劇本</strong>：收盤跌破水平支撐線。目標 = 水平線 - 開口高度。<br>
            3. 觀望：在三角形收斂末端(決策點)前，切勿重倉押注。
        `,
        calc: (v) => {
            const height = v.high - v.flatLow; // H
            
            // ==========================================
            // 📐 幾何對齊核心運算
            // ==========================================
            
            // 設定決策點在 Index 7 (T7)
            const t_break = 7; 
            const t_target = v.duration - 1; // 畫布最右邊

            // 1. 建立壓力線方程式 (Start -> Break)
            // 斜率 m = (y2 - y1) / (x2 - x1)
            const m_res = (v.flatLow - v.high) / t_break; 
            
            // 函數：輸入時間 t，算出壓力線上精確的價格
            const getResLine = (t) => v.high + m_res * t;

            // 2. 計算目標價
            const breakPrice = v.flatLow; 
            const targetBull = breakPrice + height; 
            const targetBear = breakPrice - height;

            // 3. 手動構建幾何完美的 K 線路徑
            let chartPoints = [];
            
            // --- 幾何約束區 (0 ~ 7) ---
            chartPoints[0] = v.high;          // T0: 起跌點 (在線上)
            chartPoints[1] = v.flatLow;       // T1: 測底
            
            chartPoints[2] = getResLine(2);   // T2: ★強制對齊壓力線
            
            chartPoints[3] = v.flatLow;       // T3: 測底
            chartPoints[4] = v.flatLow;       // T4: 盤整測底 (拉長底部)
            
            chartPoints[5] = getResLine(5);   // T5: ★強制對齊壓力線
            
            chartPoints[6] = v.flatLow;       // T6: 測底
            chartPoints[7] = breakPrice;      // T7: 決策點 (收斂末端)

            // --- 預測路徑區 (8 ~ End) ---
            // 用 null 填充，撐開圖表寬度以顯示虛線
            for (let i = 8; i <= t_target; i++) {
                chartPoints.push(null); 
            }

            return {
                entry: breakPrice,
                target: targetBull,
                stop: v.high,
                
                points: chartPoints,
                
                trendlines: [
                    // A. 上方壓力線 (連接 T0 -> T2 -> T5 -> T7)
                    // 使用數學計算的座標，保證連成一線
                    { x1: 0, x2: t_break, y1: v.high, y2: v.flatLow, color: '#2ecc71', label: '下降壓力' },
                    
                    // B. 下方支撐線
                    { x1: 0, x2: t_break, y1: v.flatLow, y2: v.flatLow, color: '#2ecc71', label: '水平支撐' },

                    // C. 目標價線-多
                    { x1: t_break, x2: t_target, y1: targetBull, y2: targetBull, color: '#e74c3c', label: '目標價-多' },
                    
                    // D. 目標價線-空
                    { x1: t_break, x2: t_target, y1: targetBear, y2: targetBear, color: '#2ecc71', label: '目標價-空' },

                    // E. 測幅虛線 (H)
                    { x1: 0.5, x2: 0.5, y1: v.flatLow, y2: v.high, color: '#3498db', dashed: true, label: '高度H' },
                    
                    // F. 多方走勢模擬
                    { x1: t_break, x2: t_target, y1: breakPrice, y2: targetBull, color: '#e74c3c', dashed: true, label: '突破路徑' },
                    
                    // G. 空方走勢模擬
                    { x1: t_break, x2: t_target, y1: breakPrice, y2: targetBear, color: '#2ecc71', dashed: true, label: '跌破路徑' }
                ],
                
                extraMarkers: [
                    // 1. 決策點
                    {
                        type: 'point',
                        xValue: t_break, 
                        yValue: breakPrice,
                        backgroundColor: '#95a5a6',
                        radius: 6,
                        borderColor: 'white',
                        borderWidth: 2
                    },
                    // 2. 多方目標點
                    {
                        type: 'point',
                        xValue: t_target,
                        yValue: targetBull,
                        backgroundColor: '#e74c3c',
                        radius: 8,
                        borderColor: 'white',
                        borderWidth: 2,
                        label: '多方目標'
                    },
                    // 3. 空方目標點
                    {
                        type: 'point',
                        xValue: t_target,
                        yValue: targetBear,
                        backgroundColor: '#2ecc71',
                        radius: 8,
                        borderColor: 'white',
                        borderWidth: 2,
                        label: '空方目標'
                    }
                ]
            };
        }
    },
	ascTriPrevRise: {
        name: "4. 前漲三角形 (Symmetrical Triangle) - 中繼再漲",
        type: "bull", // 中性偏多型態，等待突破
        inputs: [
            { id: "high", label: "開口高點 (壓力)", default: 55 },
            { id: "low", label: "開口低點 (支撐)", default: 35 },
            { id: "duration", label: "顯示週期", default: 12 }
        ],
        note: `
            <strong style="color: #e74c3c;">【圖解特徵】</strong>股價經歷一波上漲後進入休息。高點降低(壓力降)、低點墊高(支撐升)，多空雙方在一個收斂的三角區間內拉鋸。<br>
            <strong style="color: #9b59b6;">【關鍵細節】</strong>這是一個典型的<strong>中性偏多</strong>。圖中灰色點為決策點，雖然前勢是漲的，但收斂末端仍可能出現反轉，務必設定<strong>雙向劇本</strong>。<br>
            <strong>【操作戰略 (雙軌)】</strong><br>
            1. <strong>多方(紅)</strong>：帶量突破下降壓力線。目標 = 突破點 + H。<br>
            2. <strong>空方(綠)</strong>：收盤跌破上升支撐線。目標 = 突破點 - H。<br>
            (H 為左側開口高度)
        `,
        calc: (v) => {
            const height = v.high - v.low; // 開口高度 H
            
            // ==========================================
            // 📐 幾何對齊核心運算
            // ==========================================
            
            // 時間軸設定
            // T0: 起漲點
            // T1: 進入三角形的第一個高點 (Trend Start)
            // T7: 決策點
            const t_start = 1; // 三角形從 T1 開始算
            const t_break = 7; 
            const t_target = v.duration - 1;

            // 計算收斂中心點
            const midPoint = (v.high + v.low) / 2;

            // 1. 建立兩條方程式
            // 壓力線 (Top): 從 (1, high) 到 (7, midPoint)
            const m_top = (midPoint - v.high) / (t_break - t_start);
            const getTopLine = (t) => v.high + m_top * (t - t_start);

            // 支撐線 (Btm): 從 (1, low) 到 (7, midPoint)
            const m_btm = (midPoint - v.low) / (t_break - t_start);
            const getBtmLine = (t) => v.low + m_btm * (t - t_start);

            // 2. 計算雙向目標價
            const breakPrice = midPoint;
            const targetBull = breakPrice + height;
            const targetBear = breakPrice - height;

            // 3. 建構 K 線路徑
            let chartPoints = [];
            
            // T0: 起漲點 (低於 T1，營造上漲入場氣勢)
            // 設定為比 low 再低一點的位置
            chartPoints[0] = v.low - (height * 0.3); 

            // T1: 三角形頂點 (高)
            chartPoints[1] = v.high;
            
            // T2: 三角形底點 (低) - 對齊支撐線
            chartPoints[2] = getBtmLine(2);
            
            // T3: Lower High - 對齊壓力線
            chartPoints[3] = getTopLine(3);
            
            // T4: Higher Low - 對齊支撐線
            chartPoints[4] = getBtmLine(4);
            
            // T5: Lower High - 對齊壓力線
            chartPoints[5] = getTopLine(5);
            
            // T6: Higher Low - 對齊支撐線
            chartPoints[6] = getBtmLine(6);
            
            // T7: 決策點 (中心)
            chartPoints[7] = breakPrice;

            // 填充預測區
            for (let i = 8; i <= t_target; i++) {
                chartPoints.push(null); 
            }

            return {
                entry: breakPrice,
                target: targetBull,
                stop: v.low,
                
                points: chartPoints,
                
                trendlines: [
                    // A. 上方壓力線 (從 T1 開始畫)
                    { x1: 1, x2: t_break, y1: v.high, y2: midPoint, color: '#2ecc71', label: '收斂壓力' },
                    
                    // B. 下方支撐線 (從 T1 的 x 座標開始對齊視覺，實際連線是 T2, T4...)
                    // 為了美觀，我們從 x=1 開始畫，這會形成一個標準開口
                    { x1: 1, x2: t_break, y1: v.low, y2: midPoint, color: '#2ecc71', label: '收斂支撐' },

                    // C. 進場趨勢線 (T0 -> T1)
                    { x1: 0, x2: 1, y1: chartPoints[0], y2: v.high, color: '#e74c3c', label: '前漲段' },

                    // D. 目標價線-多
                    { x1: t_break, x2: t_target, y1: targetBull, y2: targetBull, color: '#e74c3c', label: '目標價-多' },
                    
                    // E. 目標價線-空
                    { x1: t_break, x2: t_target, y1: targetBear, y2: targetBear, color: '#2ecc71', label: '目標價-空' },

                    // F. 測幅虛線 (H) - 畫在 T1 位置
                    { x1: 1, x2: 1, y1: v.low, y2: v.high, color: '#3498db', dashed: true, label: '高度H' },
                    
                    // G. 多方路徑模擬
                    { x1: t_break, x2: t_target, y1: breakPrice, y2: targetBull, color: '#e74c3c', dashed: true, label: '突破路徑' },
                    
                    // H. 空方路徑模擬
                    { x1: t_break, x2: t_target, y1: breakPrice, y2: targetBear, color: '#2ecc71', dashed: true, label: '跌破路徑' }
                ],
                
                extraMarkers: [
                    // 1. 決策點
                    {
                        type: 'point',
                        xValue: t_break, 
                        yValue: breakPrice,
                        backgroundColor: '#95a5a6',
                        radius: 6,
                        borderColor: 'white',
                        borderWidth: 2
                    },
                    // 2. 多方目標點
                    {
                        type: 'point',
                        xValue: t_target,
                        yValue: targetBull,
                        backgroundColor: '#e74c3c',
                        radius: 8,
                        borderColor: 'white',
                        borderWidth: 2,
                        label: '多方目標'
                    },
                    // 3. 空方目標點
                    {
                        type: 'point',
                        xValue: t_target,
                        yValue: targetBear,
                        backgroundColor: '#2ecc71',
                        radius: 8,
                        borderColor: 'white',
                        borderWidth: 2,
                        label: '空方目標'
                    }
                ]
            };
        }
    },
	ascRightTri: {
        name: "5. 上升直角三角形 (Ascending Triangle) - 多頭緩攻",
        type: "bull", // 中性偏多等待表態
        inputs: [
            { id: "flatHigh", label: "水平壓力 (頂)", default: 50 },
            { id: "low", label: "起漲低點 (底)", default: 35 },
            { id: "duration", label: "顯示週期", default: 12 }
        ],
        note: `
            <strong style="color: #e74c3c;">【圖解特徵】</strong>多頭步步進逼，回檔低點不斷墊高(上升支撐)，但空方死守特定價位(平頭壓力)。這是一個「買方積極、賣方被動」的收斂型態。<br>
            <strong style="color: #9b59b6;">【關鍵細節】</strong>此為<strong>「中性偏多」</strong>型態。圖中<strong>灰色點</strong>為決策點。雖然此型態看漲機率較高，但若跌破上升趨勢線，仍須執行<strong>空方劇本</strong>。<br>
            <strong>【操作戰略 (雙軌)】</strong><br>
            1. <strong>多方(紅)</strong>：突破水平壓力線。目標 = 突破點 + H。<br>
            2. <strong>空方(綠)</strong>：跌破上升支撐線。目標 = 突破點 - H。<br>
            (H 為左側開口高度)
        `,
        calc: (v) => {
            const height = v.flatHigh - v.low; // 開口高度 H
            
            // ==========================================
            // 📐 幾何對齊核心運算
            // ==========================================
            
            // 設定決策點在 Index 7 (T7)
            const t_break = 7; 
            const t_target = v.duration - 1; // 畫布最右邊

            // 1. 建立上升支撐線方程式 (Start -> Break)
            // 起點 (0, low) -> 終點 (7, flatHigh)
            // 斜率 m = (y2 - y1) / (x2 - x1)
            const m_sup = (v.flatHigh - v.low) / t_break;
            
            // 函數：輸入時間 t，算出上升支撐線上精確的價格
            const getSupLine = (t) => v.low + m_sup * t;

            // 2. 計算雙向目標價
            // 基準突破價 (設定為收斂末端的水平位，即 flatHigh)
            const breakPrice = v.flatHigh; 
            
            const targetBull = breakPrice + height; // 上方目標 (+H)
            const targetBear = breakPrice - height; // 下方目標 (-H)

            // 3. 手動構建幾何完美的 K 線路徑
            let chartPoints = [];
            
            // --- 幾何約束區 (0 ~ 7) ---
            // 模擬：低 -> 高 -> 高底 -> 高 -> 高底...
            chartPoints[0] = v.low;           // T0: 起漲點 (在支撐線上)
            chartPoints[1] = v.flatHigh;      // T1: 第一次測頂 (Flat)
            
            chartPoints[2] = getSupLine(2);   // T2: ★強制對齊上升支撐線 (Higher Low)
            
            chartPoints[3] = v.flatHigh;      // T3: 二次測頂 (Flat)
            
            chartPoints[4] = getSupLine(4);   // T4: ★強制對齊上升支撐線 (Higher Low)
            
            chartPoints[5] = v.flatHigh;      // T5: 三次測頂 (Flat)
            
            chartPoints[6] = getSupLine(6);   // T6: ★強制對齊上升支撐線 (Higher Low)
            
            chartPoints[7] = breakPrice;      // T7: 決策點 (收斂末端，頂到底)

            // --- 預測路徑區 (8 ~ End) ---
            // 用 null 填充，撐開圖表寬度以顯示虛線
            for (let i = 8; i <= t_target; i++) {
                chartPoints.push(null); 
            }

            return {
                entry: breakPrice,
                target: targetBull,
                stop: v.low,
                
                points: chartPoints,
                
                trendlines: [
                    // A. 上方壓力線 (水平)
                    { x1: 0, x2: t_break, y1: v.flatHigh, y2: v.flatHigh, color: '#2ecc71', label: '水平壓力' },
                    
                    // B. 下方支撐線 (上升)
                    // 使用幾何座標，保證 T0, T2, T4, T6 完美連線
                    { x1: 0, x2: t_break, y1: v.low, y2: v.flatHigh, color: '#2ecc71', label: '上升支撐' },

                    // C. 目標價線-多 (紅線)
                    { x1: t_break, x2: t_target, y1: targetBull, y2: targetBull, color: '#e74c3c', label: '目標價-多' },
                    
                    // D. 目標價線-空 (綠線)
                    { x1: t_break, x2: t_target, y1: targetBear, y2: targetBear, color: '#2ecc71', label: '目標價-空' },

                    // E. 測幅虛線 (H)
                    { x1: 1.5, x2: 1.5, y1: getSupLine(1.5), y2: v.flatHigh, color: '#3498db', dashed: true, label: '高度H' },
                    
                    // F. 多方走勢模擬 (紅色虛線路徑)
                    { x1: t_break, x2: t_target, y1: breakPrice, y2: targetBull, color: '#e74c3c', dashed: true, label: '突破路徑' },
                    
                    // G. 空方走勢模擬 (綠色虛線路徑)
                    { x1: t_break, x2: t_target, y1: breakPrice, y2: targetBear, color: '#2ecc71', dashed: true, label: '跌破路徑' }
                ],
                
                extraMarkers: [
                    // 1. 決策點 (灰色中性)
                    {
                        type: 'point',
                        xValue: t_break, 
                        yValue: breakPrice,
                        backgroundColor: '#95a5a6',
                        radius: 6,
                        borderColor: 'white',
                        borderWidth: 2
                    },
                    // 2. 多方目標點 (紅色)
                    {
                        type: 'point',
                        xValue: t_target,
                        yValue: targetBull,
                        backgroundColor: '#e74c3c',
                        radius: 8,
                        borderColor: 'white',
                        borderWidth: 2,
                        label: '多方目標'
                    },
                    // 3. 空方目標點 (綠色)
                    {
                        type: 'point',
                        xValue: t_target,
                        yValue: targetBear,
                        backgroundColor: '#2ecc71',
                        radius: 8,
                        borderColor: 'white',
                        borderWidth: 2,
                        label: '空方目標'
                    }
                ]
            };
        }
    },

    // --- 快跌飄旗系列 (Bear Flags) ---
    bearFlagUp: {
        name: "6. 快跌上升飄旗", type: "neutral",
        inputs: [{ id: "pole", label: "旗桿頂", default: 100 }, { id: "brk", label: "跌破點", default: 80 }],
        note: "<strong>特徵</strong>：急跌後，旗面向上傾斜。<br><strong>戰略</strong>：跌破下緣。",
        calc: (v) => ({ entry: v.brk, target: v.brk - (v.pole-v.brk), stop: v.brk+5, points: [v.pole, v.brk, v.brk+5, v.brk+2, v.brk+7, v.brk+4, v.brk-5], trendlines: [{x1:1,x2:5,y1:v.brk,y2:v.brk+4,color:'#27ae60'}] })
    },
    bearFlagFlat: {
        name: "7. 快跌水平飄旗", type: "neutral",
        inputs: [{ id: "pole", label: "旗桿頂", default: 100 }, { id: "brk", label: "跌破點", default: 80 }],
        note: "<strong>特徵</strong>：急跌後，旗面水平橫移。<br><strong>戰略</strong>：跌破下緣。",
        calc: (v) => ({ entry: v.brk, target: v.brk - (v.pole-v.brk), stop: v.brk+5, points: [v.pole, v.brk, v.brk+5, v.brk, v.brk+5, v.brk, v.brk-5], trendlines: [{x1:1,x2:5,y1:v.brk,y2:v.brk,color:'#27ae60'}] })
    },
    bearFlagDown: {
        name: "8. 快跌下降飄旗", type: "neutral",
        inputs: [{ id: "pole", label: "旗桿頂", default: 100 }, { id: "brk", label: "跌破點", default: 80 }],
        note: "<strong>特徵</strong>：急跌後，旗面向下傾斜(較少見)。<br><strong>戰略</strong>：跌破下緣。",
        calc: (v) => ({ entry: v.brk, target: v.brk - (v.pole-v.brk), stop: v.brk+5, points: [v.pole, v.brk+5, v.brk+8, v.brk+3, v.brk+6, v.brk, v.brk-5], trendlines: [{x1:3,x2:5,y1:v.brk+3,y2:v.brk,color:'#27ae60'}] })
    },
    // --- 快跌三角飄旗系列 (Bear Pennants) ---
    bearPennantUp: {
        name: "9. 快跌上升三角飄旗", type: "neutral",
        inputs: [{ id: "pole", label: "旗桿頂", default: 100 }, { id: "brk", label: "跌破點", default: 80 }],
        note: "<strong>特徵</strong>：急跌後收斂，重心略升。<br><strong>戰略</strong>：跌破下緣。",
        calc: (v) => ({ entry: v.brk, target: v.brk - (v.pole-v.brk), stop: v.brk+5, points: [v.pole, v.brk, v.brk+5, v.brk+2, v.brk+4, v.brk, v.brk-5], trendlines: [{x1:1,x2:5,y1:v.brk,y2:v.brk,color:'#27ae60'}] })
    },
    bearPennantFlat: {
        name: "10. 快跌水平三角飄旗", type: "neutral",
        inputs: [{ id: "pole", label: "旗桿頂", default: 100 }, { id: "brk", label: "跌破點", default: 80 }],
        note: "<strong>特徵</strong>：急跌後標準收斂三角。<br><strong>戰略</strong>：跌破下緣。",
        calc: (v) => ({ entry: v.brk, target: v.brk - (v.pole-v.brk), stop: v.brk+5, points: [v.pole, v.brk, v.brk+6, v.brk+1, v.brk+3, v.brk, v.brk-5], trendlines: [{x1:1,x2:5,y1:v.brk,y2:v.brk,color:'#27ae60'}] })
    },
    bearPennantDown: {
        name: "11. 快跌下降三角飄旗", type: "neutral",
        inputs: [{ id: "pole", label: "旗桿頂", default: 100 }, { id: "brk", label: "跌破點", default: 80 }],
        note: "<strong>特徵</strong>：急跌後收斂，重心下降。<br><strong>戰略</strong>：跌破下緣。",
        calc: (v) => ({ entry: v.brk, target: v.brk - (v.pole-v.brk), stop: v.brk+5, points: [v.pole, v.brk+2, v.brk+6, v.brk+1, v.brk+3, v.brk, v.brk-5], trendlines: [{x1:3,x2:5,y1:v.brk+1,y2:v.brk,color:'#27ae60'}] })
    },

    // --- 快漲飄旗系列 (Bull Flags) ---
    bullFlagUp: {
        name: "12. 快漲上升飄旗", type: "neutral",
        inputs: [{ id: "pole", label: "旗桿底", default: 40 }, { id: "brk", label: "突破點", default: 60 }],
        note: "<strong>特徵</strong>：急漲後，旗面向上傾斜(較少見)。<br><strong>戰略</strong>：突破上緣。",
        calc: (v) => ({ entry: v.brk, target: v.brk + (v.brk-v.pole), stop: v.brk-5, points: [v.pole, v.brk-5, v.brk-8, v.brk-2, v.brk-5, v.brk, v.brk+5], trendlines: [{x1:3,x2:5,y1:v.brk-2,y2:v.brk,color:'#c0392b'}] })
    },
    bullFlagFlat: {
        name: "13. 快漲水平飄旗", type: "neutral",
        inputs: [{ id: "pole", label: "旗桿底", default: 40 }, { id: "brk", label: "突破點", default: 60 }],
        note: "<strong>特徵</strong>：急漲後，旗面水平橫移。<br><strong>戰略</strong>：突破上緣。",
        calc: (v) => ({ entry: v.brk, target: v.brk + (v.brk-v.pole), stop: v.brk-5, points: [v.pole, v.brk, v.brk-5, v.brk, v.brk-5, v.brk, v.brk+5], trendlines: [{x1:1,x2:5,y1:v.brk,y2:v.brk,color:'#c0392b'}] })
    },
    bullFlagDown: {
        name: "14. 快漲下降飄旗", type: "neutral",
        inputs: [{ id: "pole", label: "旗桿底", default: 40 }, { id: "brk", label: "突破點", default: 60 }],
        note: "<strong>特徵</strong>：急漲後，旗面向下傾斜(最標準)。<br><strong>戰略</strong>：突破上緣。",
        calc: (v) => ({ entry: v.brk, target: v.brk + (v.brk-v.pole), stop: v.brk-5, points: [v.pole, v.brk, v.brk-5, v.brk-2, v.brk-7, v.brk-4, v.brk+5], trendlines: [{x1:1,x2:5,y1:v.brk,y2:v.brk-4,color:'#c0392b'}] })
    },
    // --- 快漲三角飄旗系列 (Bull Pennants) ---
    bullPennantUp: {
        name: "15. 快漲上升三角飄旗", type: "neutral",
        inputs: [{ id: "pole", label: "旗桿底", default: 40 }, { id: "brk", label: "突破點", default: 60 }],
        note: "<strong>特徵</strong>：急漲後收斂，重心上升。<br><strong>戰略</strong>：突破上緣。",
        calc: (v) => ({ entry: v.brk, target: v.brk + (v.brk-v.pole), stop: v.brk-5, points: [v.pole, v.brk-2, v.brk-6, v.brk-1, v.brk-3, v.brk, v.brk+5], trendlines: [{x1:3,x2:5,y1:v.brk-1,y2:v.brk,color:'#c0392b'}] })
    },
    bullPennantFlat: {
        name: "16. 快漲水平三角飄旗", type: "neutral",
        inputs: [{ id: "pole", label: "旗桿底", default: 40 }, { id: "brk", label: "突破點", default: 60 }],
        note: "<strong>特徵</strong>：急漲後標準收斂三角。<br><strong>戰略</strong>：突破上緣。",
        calc: (v) => ({ entry: v.brk, target: v.brk + (v.brk-v.pole), stop: v.brk-5, points: [v.pole, v.brk, v.brk-6, v.brk-1, v.brk-3, v.brk, v.brk+5], trendlines: [{x1:1,x2:5,y1:v.brk,y2:v.brk,color:'#c0392b'}] })
    },
    bullPennantDown: {
        name: "17. 快漲下降三角飄旗", type: "neutral",
        inputs: [{ id: "pole", label: "旗桿底", default: 40 }, { id: "brk", label: "突破點", default: 60 }],
        note: "<strong>特徵</strong>：急漲後收斂，重心下降。<br><strong>戰略</strong>：突破上緣。",
        calc: (v) => ({ entry: v.brk, target: v.brk + (v.brk-v.pole), stop: v.brk-5, points: [v.pole, v.brk, v.brk-5, v.brk-2, v.brk-4, v.brk, v.brk+5], trendlines: [{x1:1,x2:5,y1:v.brk,y2:v.brk,color:'#c0392b'}] })
    },

    // ------------------------------------------
    // C. 下跌型態 (Bearish)
    // ------------------------------------------
    vTop: {
        name: "1. 倒V字型 (Inverted V)", type: "bear",
        inputs: [{ id: "peak", label: "尖頂", default: 100 }, { id: "sup", label: "起漲支撐", default: 80 }],
        note: "<strong>特徵</strong>：急漲急跌。<br><strong>戰略</strong>：跌破起漲支撐。",
        calc: (v) => ({ entry: v.sup, target: v.sup - (v.peak-v.sup), stop: v.peak, points: [v.sup, v.peak, v.sup, v.sup-20], trendlines: [{x1:0,x2:2,y1:v.sup,y2:v.sup,color:'#e67e22'}] })
    },
    nTop: {
        name: "2. 倒N字頂 (Inverted N)", type: "bear",
        inputs: [{ id: "l1", label: "前低 (L1)", default: 80 }, { id: "h2", label: "反彈高 (H2)", default: 90 }],
        note: "<strong>特徵</strong>：跌→彈不過高→跌破低。<br><strong>戰略</strong>：跌破L1進場。",
        calc: (v) => ({ entry: v.l1, target: v.l1 - (v.h2-v.l1), stop: v.h2, points: [100, v.l1, v.h2, v.l1, v.l1-10], trendlines: [{x1:1,x2:3,y1:v.l1,y2:v.l1,color:'#e67e22'}] })
    },
    hsTop: {
        name: "3. 頭肩頂 (Head & Shoulders Top)", type: "bear",
        inputs: [{ id: "neck", label: "頸線", default: 80 }, { id: "head", label: "頭部高", default: 100 }, { id: "rs", label: "右肩高", default: 90 }],
        note: "<strong>特徵</strong>：右肩不過頭。<br><strong>戰略</strong>：跌破頸線進場。",
        calc: (v) => ({ entry: v.neck, target: v.neck - (v.head-v.neck), stop: v.rs, points: [v.neck, 88, v.neck, v.head, v.neck, v.rs, v.neck, v.neck-5], trendlines: [{x1:0,x2:6,y1:v.neck,y2:v.neck,color:'#e67e22'}] })
    },
    complexHsTop: {
        name: "4. 複式頭尖頂", type: "bear",
        inputs: [{ id: "neck", label: "頸線", default: 50 }, { id: "head", label: "最高點", default: 60 }, { id: "rs", label: "右肩高", default: 55 }],
        note: "<strong>特徵</strong>：多重頭部或肩部。<br><strong>戰略</strong>：跌破長期頸線。",
        calc: (v) => ({ entry: v.neck, target: v.neck - (v.head-v.neck), stop: v.rs, points: [52, v.neck, 54, v.neck, v.head, v.neck, 56, v.neck, v.rs, v.neck, v.neck-5], trendlines: [{x1:0,x2:10,y1:v.neck,y2:v.neck,color:'#e67e22'}] })
    },
    doubleTop: {
        name: "5. 雙重頂/M頭 (Double Top)", type: "bear",
        inputs: [{ id: "neck", label: "頸線", default: 80 }, { id: "high", label: "頂部高點", default: 100 }],
        note: "<strong>特徵</strong>：兩次攻頂不過。<br><strong>戰略</strong>：跌破中間頸線。",
        calc: (v) => ({ entry: v.neck, target: v.neck - (v.high-v.neck), stop: v.high, points: [v.neck, v.high, v.neck, v.high-2, v.neck, v.neck-5], trendlines: [{x1:0,x2:4,y1:v.neck,y2:v.neck,color:'#e67e22'}] })
    },
    roundingTop: {
        name: "6. 圓弧頂 (Rounding Top)", type: "bear",
        inputs: [{ id: "neck", label: "支撐線", default: 80 }, { id: "high", label: "圓弧頂", default: 100 }],
        note: "<strong>特徵</strong>：緩漲緩跌。<br><strong>戰略</strong>：跌破支撐線。",
        calc: (v) => ({ entry: v.neck, target: v.neck - (v.high-v.neck), stop: v.high, points: [85, 95, 98, v.high, 98, 95, 85, v.neck, v.neck-5], trendlines: [{x1:0,x2:7,y1:v.neck,y2:v.neck,color:'#e67e22'}] })
    },
    ascRightTriTop: {
        name: "7. 上升直角三角頂", type: "bear",
        inputs: [{ id: "res", label: "水平壓力", default: 100 }, { id: "sup", label: "上升支撐破點", default: 90 }],
        note: "<strong>特徵</strong>：壓力水平，低點墊高但最後失敗。<br><strong>戰略</strong>：跌破上升支撐線。",
        calc: (v) => ({ entry: v.sup, target: v.sup - (v.res-v.sup), stop: v.res, points: [80, v.res, 85, v.res, v.sup, 88, v.sup-5], trendlines: [{x1:0,x2:4,y1:v.res,y2:v.res,color:'#c0392b'},{x1:0,x2:4,y1:80,y2:v.sup,color:'#27ae60'}] })
    },
    ascWedge: {
        name: "8. 上升楔型 (Ascending Wedge)", type: "bear",
        inputs: [{ id: "brk", label: "跌破點", default: 80 }, { id: "high", label: "最高點", default: 90 }, { id: "width", label: "開口寬度", default: 10 }],
        note: "<strong>特徵</strong>：高過高但收斂。<br><strong>戰略</strong>：跌破下緣支撐。",
        calc: (v) => ({ entry: v.brk, target: v.brk - v.width, stop: v.high, points: [70, v.brk+5, 75, v.high, v.brk, 88, v.brk-5], trendlines: [{x1:1,x2:5,y1:v.brk+5,y2:88,color:'#27ae60'},{x1:0,x2:4,y1:70,y2:v.high,color:'#c0392b'}] })
    },
    broadeningTop: {
        name: "9. 上升擴張喇叭型頂", type: "bear",
        inputs: [{ id: "brk", label: "跌破點", default: 80 }, { id: "high", label: "最後高", default: 90 }, { id: "amp", label: "振幅", default: 20 }],
        note: "<strong>特徵</strong>：波動擴大，高檔失控。<br><strong>戰略</strong>：跌破下緣支撐。",
        calc: (v) => ({ entry: v.brk, target: v.brk - v.amp, stop: v.high, points: [85, 82, 88, 80, v.high, v.brk, v.brk-5], trendlines: [{x1:3,x2:5,y1:80,y2:v.brk,color:'#27ae60'}] })
    },
    diamondTop: {
        name: "10. 前漲菱型 (Diamond Top)", type: "bear",
        inputs: [{ id: "brk", label: "跌破點", default: 80 }, { id: "high", label: "菱形高", default: 90 }, { id: "low", label: "菱形低", default: 70 }],
        note: "<strong>特徵</strong>：頭部出現擴張後收斂。<br><strong>戰略</strong>：跌破右側支撐。",
        calc: (v) => ({ entry: v.brk, target: v.brk - (v.high-v.low), stop: v.high, points: [85, v.low, 85, v.high, 82, v.brk, v.brk-5], trendlines: [{x1:1,x2:5,y1:v.high,y2:v.brk,color:'#27ae60'}] })
    }
};

// ==========================================
// 3. 核心邏輯 (Logic)
// ==========================================
let myChart = null;

document.addEventListener('DOMContentLoaded', () => {
    updatePatternList(); // 初始化：根據預設分類載入型態列表
});

// 連動選單邏輯：當分類改變時，更新型態列表
function updatePatternList() {
    const category = document.getElementById('categorySelect').value;
    const patternSelect = document.getElementById('patternSelect');
    
    // 清空現有選項
    patternSelect.innerHTML = '';
    
    // 根據分類索引填充新選項
    const patterns = categoryIndex[category];
    patterns.forEach(key => {
        const option = document.createElement('option');
        option.value = key;
        option.text = patternsDB[key].name;
        patternSelect.appendChild(option);
    });
    
    // 載入第一個型態的配置
    loadPatternConfig();
}

function loadPatternConfig() {
    const patternId = document.getElementById('patternSelect').value;
    const pattern = patternsDB[patternId];
    
    if (!pattern) return;

    document.getElementById('patternTitle').innerText = pattern.name;
    document.getElementById('patternNote').innerHTML = pattern.note;
    
    const badge = document.getElementById('patternBadge');
    badge.innerText = pattern.type === 'bull' ? '看漲 (Bullish)' : (pattern.type === 'bear' ? '看跌 (Bearish)' : '中性 (Neutral)');
    badge.className = `badge ${pattern.type}`;

    const inputsDiv = document.getElementById('dynamicInputs');
    inputsDiv.innerHTML = '';
    
    pattern.inputs.forEach(input => {
        const div = document.createElement('div');
        div.className = 'input-group';
        div.innerHTML = `
            <label>${input.label}</label>
            <input type="number" id="input_${input.id}" value="${input.default}" step="0.5">
        `;
        inputsDiv.appendChild(div);
    });

    calculateAndDraw();
}

function calculateAndDraw() {
    const patternId = document.getElementById('patternSelect').value;
    const pattern = patternsDB[patternId];
    const values = {};
    
    pattern.inputs.forEach(input => {
        values[input.id] = parseFloat(document.getElementById(`input_${input.id}`).value);
    });

    const result = pattern.calc(values);

    document.getElementById('entryDisplay').innerText = `$${result.entry.toFixed(2)}`;
    document.getElementById('targetDisplay').innerText = `$${result.target.toFixed(2)}`;
    document.getElementById('stopDisplay').innerText = `$${result.stop.toFixed(2)}`;
    
    let dirText = "";
    if (pattern.type === 'bull') dirText = "做多 (Long)";
    else if (pattern.type === 'bear') dirText = "做空 (Short)";
    else dirText = "順勢操作 (Follow Trend)";
    
    document.getElementById('directionDisplay').innerText = dirText;

    renderChart(result, pattern.type);
}

function renderChart(result, type) {
    const ctx = document.getElementById('tradeChart').getContext('2d');
    if (myChart) myChart.destroy();

    const isBull = type === 'bull';
    const mainColor = isBull ? '#27ae60' : (type === 'bear' ? '#c0392b' : '#f39c12');
    
    // 產生 X 軸標籤
    const labels = result.points.map((_, i) => i === result.points.length - 2 ? 'Entry' : `T${i}`);
    
    const annotations = {
        targetLine: {
            type: 'line', yMin: result.target, yMax: result.target,
            borderColor: '#2980b9', borderWidth: 2, borderDash: [6, 4],
            label: { display: true, content: `Target: ${result.target.toFixed(2)}`, position: 'end', backgroundColor: '#2980b9' }
        },
        stopLine: {
            type: 'line', yMin: result.stop, yMax: result.stop,
            borderColor: '#e74c3c', borderWidth: 1, borderDash: [4, 4],
            label: { display: true, content: `Stop: ${result.stop.toFixed(2)}`, position: 'start', backgroundColor: '#e74c3c', font: {size: 10} }
        },
        entryMarker: {
            type: 'point', xValue: result.points.length - 2, yValue: result.entry,
            backgroundColor: mainColor, radius: 6, borderWidth: 2, borderColor: 'white'
        }
    };
	
	// === 新增功能：支援額外的自定義標記 (Extra Markers) ===
    if (result.extraMarkers) {
        result.extraMarkers.forEach((marker, index) => {
            annotations[`extraMarker${index}`] = marker;
        });
    }

    if (result.trendlines) {
        result.trendlines.forEach((line, index) => {
            annotations[`trendline${index}`] = {
                type: 'line',
                xMin: line.x1, xMax: line.x2,
                yMin: line.y1, yMax: line.y2,
                borderColor: line.color, borderWidth: 2,
                borderDash: line.dashed ? [5, 5] : [],
                label: { display: false }
            };
        });
    }

    myChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: '模擬走勢',
                data: result.points,
                borderColor: '#34495e',
                backgroundColor: 'rgba(52, 73, 94, 0.05)',
                borderWidth: 2.5,
                tension: 0.2,
                fill: true,
                pointRadius: 3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                annotation: { annotations: annotations },
                tooltip: { callbacks: { label: (ctx) => `價格: ${ctx.raw.toFixed(2)}` } }
            },
            scales: { y: { grace: '20%' }, x: { display: false } }
        }
    });
}