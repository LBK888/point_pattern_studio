# Point Pattern Studio v1.2｜點分布與線條點化評分工具

[English](readme.md) | 繁體中文

Windows / macOS / Linux 的 PyQt6 圖形介面程式；另有無介面 CLI。所有功能在電腦本機執行，不需要上傳資料至伺服器。

## 1. 安裝與啟動

建議 Python 3.10 以上（已在 Windows 11 + Python 3.14 測試），Windows 10/11 64 位元。

**Windows**：雙擊 `run_windows.bat`。它會優先使用 `py` 啟動器找 Python，只有在缺少套件時才執行 `pip install`（第一次需要網路，之後可離線啟動），任何步驟失敗都會停下來顯示原因。

> `run_windows.bat` 必須維持 Windows 的 CRLF 換行。v1.0 的檔案是 LF 換行，`chcp 65001` 加上中文訊息會讓 cmd 切錯行，因此雙擊後永遠執行不到 `app.py`。若用編輯器修改此檔，請確認存檔格式為 CRLF、UTF-8（無 BOM）。GitHub 倉庫以 `.gitattributes` 原樣保存此檔，clone 或下載 ZIP 都會維持 CRLF。

若已安裝依賴，也可以直接在命令提示字元執行：

```powershell
cd point_pattern_studio
python -m pip install -r requirements.txt
python app.py
```

**macOS / Linux**：

```bash
cd point_pattern_studio
python3 -m pip install -r requirements.txt
python3 app.py
```

GUI 預設使用 PyQt6，若環境已裝 PySide6，程式也有相容 fallback。L(r) 圖使用 matplotlib（v1.2 新增的套件；`run_windows.bat` 偵測到缺少時會自動安裝）。v1.2 已在 Windows 11 以離屏模式自動操作三個頁籤（批次產生含全部 11 種模式、匯入分析、內建圖形放點／最佳化／匯出、右鍵複製圖片）完成測試。macOS／Linux 的啟動腳本未實機測試；若 Homebrew Python 拒絕 `pip install`（externally-managed-environment），請先建立虛擬環境：`python3 -m venv ~/.venvs/pps && source ~/.venvs/pps/bin/activate`。

## 2. 三個頁籤

### ① 批次產生 N 張點圖

- 設定生成張數 N、每張點數、亂數種子、分布類別、強度與畫布大小。
- 支援 `random` 完全空間隨機、`cluster` 群聚、`regular` 格線加擾動、混合類型（見下表）、`surprise` 每張隨機選類別。
- 「混合 (Hybrid)」每張從下表 7 種混合類型隨機挑一種；也可以在下拉選單直接指定其中一種。
- 儲存每張 `pattern_XXXX.png`、相應的 `pattern_XXXX_xy.csv`、L(r) 圖 `pattern_XXXX_Lr.png`、彙整 `all_metrics.csv`（含 L(r) 數值結果，見下方），以及所有圖的 L(r) 曲線 `Lr_curves.csv`（每列一個 pattern 的一個 r，與圖上畫的數值完全相同，含隨機模擬範圍）。
- 點選表格某一列時，右側可看點圖、L(r) 圖及全部統計值。資料存至程式的 `output/batch_日期時間/`。
- **所有頁籤的圖片都可以按滑鼠右鍵「複製圖片」貼到 PowerPoint／Word，或「另存圖片」**。複製的是原尺寸圖（批次點圖＝設定的畫布大小，③ 的點圖＝匯出 PNG 的尺寸），不是畫面上縮小的預覽。

#### 混合類型（多尺度）

「小尺度」指幾個點間距以內的排列，「大尺度」指整張畫布上的分布。CSV 的 `pattern_type` 代碼為 `ms_小尺度_大尺度`。

| 類型 | 產生方式 | L(r) 圖特徵 | 分數（強度 0.3 / 0.6 / 0.9，180 點） |
|---|---|---|---|
| 群聚＋隨機背景點（`hybrid`，v1.1 原有） | 一部分點群聚、其餘隨機 | 全程在虛線上方 | −0.18 / −0.47 / −0.76 |
| 小尺度群聚／大尺度隨機（`ms_cluster_random`） | 每團約 5 點的小緊密團，團的位置完全隨機 | 小 r 急升到虛線上方，大 r 逐漸回到虛線 | −0.92 / −0.98 / −1.00 |
| 小尺度隨機／大尺度群聚（`ms_random_cluster`） | 2～4 個大區塊，區塊內完全隨機，區塊外沒有點 | 斜率大於 1 的直線，一路在虛線上方 | −0.98 / −1.00 / −1.00 |
| 小尺度均勻／大尺度群聚（`ms_regular_cluster`） | 同上的大區塊，區塊內點與點保持最小距離 | 最小距離以內 L=0，之後急升到虛線上方 | −0.95 / −0.99 / −1.00 |
| 小尺度群聚／大尺度均勻（`ms_cluster_regular`） | 小緊密團排在規則格點上，每團點數相同 | 小 r 在上方，接著出現平台（團與團之間沒有點），到團間距再上升 | −0.49 / −0.73 / −0.93 |
| 小尺度均勻／大尺度隨機（`ms_regular_random`） | 硬核過程：隨機放點但任兩點不得太近，沒有格子 | 最小距離以內 L=0，大 r 回到虛線 | +0.58 / +0.74 / +0.87 |
| 小尺度隨機／大尺度均勻（`ms_random_regular`） | 粗格子每格點數相同（4～10 點），格內完全隨機 | 幾乎貼著虛線，大 r 略低於虛線 | +0.14 / +0.16 / +0.15 |

**這些類型說明了 PPDI 主要看小尺度。** Hopkins 看最近鄰距離，Ripley 只在 0.5～1.5 倍平均點距取值（L(r) 圖上的淡黃色帶）。因此：
- 只要小尺度有緊密團，大尺度怎麼排都會被判為群聚（第 2、5 列）。
- 大尺度群聚會留下大片空白，Hopkins 的探針落在空白處，所以即使區塊內是均勻的，分數仍接近 −1（第 3、4 列）。
- 大尺度的均勻（第 7 列）幾乎看不出來：肉眼、分數都接近隨機，只有 `quadrat_vmr_4x4` 明顯小於 1。

#### L(r) 圖怎麼看

- **虛線（45°）**：完全隨機時 L(r)=r。兩軸刻度相同，所以虛線就是對角線。
- **藍線在虛線上方**：在半徑 r 內的鄰居比隨機多，也就是群聚；**在下方**：鄰居比隨機少，也就是均勻（規律）。
- **灰色帶**：同點數、同畫布比例的 39 張完全隨機圖的 L(r) 最小～最大範圍（逐點 95% 範圍）。藍線落在灰帶內，代表在該尺度和隨機無法區分。
- **淡黃色帶**：分數中 Ripley 部分實際使用的半徑範圍（0.5～1.5 倍平均點距）。
- **正方形、兩軸範圍與刻度相同**：r 的單位以畫布高度為 1。隨機與規律圖兩軸都是 0 到畫布短邊的 1/4（Ripley 常用範圍，800×800 時為 0～0.25）；群聚圖的 L(r) 會超過這個範圍，這時兩軸一起放大到下一個整數刻度（例如 0～0.40），r 也計算到同樣的值（最多到短邊的 1/2）。在常用範圍內曲線一定完整顯示；更大的 r 處，強群聚的曲線可能從上緣離開圖框。點數極多時範圍會縮短以控制計算量。
- 圖上文字為英文，標題為圖形類型（匯入時為檔名）與分數。估計方式與分數相同（平移式邊界修正）。

#### L(r) 數值結果

每張圖的 L(r) 判讀也以數字輸出（批次的 `all_metrics.csv`、匯入頁的指標表與匯出 CSV、CLI）：

| 欄位 | 內容 |
|---|---|
| `lr_clustered_r` | 藍線高於灰色帶的 r 區間，例如 `0.007-0.120`＝在這些尺度顯著群聚；`none`＝沒有 |
| `lr_regular_r` | 藍線低於灰色帶的 r 區間＝在這些尺度顯著均勻 |
| `lr_max_L_minus_r`、`lr_r_at_max` | L(r)−r 的最大值與出現的 r（群聚最強的尺度） |
| `lr_min_L_minus_r`、`lr_r_at_min` | L(r)−r 的最小值與出現的 r（均勻最強的尺度） |
| `lr_r_max` | 計算到的最大 r |

灰色帶是逐點的 95% 範圍，在許多 r 同時比較時，完全隨機的圖偶爾也會有一小段超出；只有連續至少 2 個格點超出才列出。

### ② 匯入圖片／座標分析

支援白底黑點 PNG / JPG / TIFF / BMP；按「反轉」可分析黑底白點。
黑點偵測使用閾值加連通區重心：**黏連、重疊黑點可能被合併**；精確研究請優先使用原始座標 CSV。例如群聚類與小緊密團類的批次 PNG（800 px、點半徑 3）平均有 20～35 個點互相重疊而合併，重新匯入 PNG 的分數會和批次表不同；匯入同名的 `_xy.csv` 則完全相同。

分析後右側顯示 L(r) 圖（看法見上一節）。下方狀態列會用一句話寫出 L(r) 的結論（例如「L(r)：r = 0.019-0.104 顯著群聚」），指標表最上方也列出上一節的 L(r) 數值結果。「匯出」另外輸出 `analysed_Lr.png` 與 `analysed_Lr_curve.csv`（r、L、L−r、K 與隨機模擬範圍）。

座標格式：

`CSV`：

```csv
x,y
0.12,0.25
0.43,0.82
0.89,0.11
```

`JSON`：

```json
{"width": 800, "height": 800, "points": [[100, 150], [245, 360], [580, 400]]}
```

也支援純座標矩陣 JSON、TXT（每列 `x y` 或 `x,y`）。座標若已在 0～1，不再次縮放；否則根據使用者提供的畫布寬、高正規化。**不要在不了解實際畫布邊界的情況下勾選「自身邊界縮放」**，因為這會改變 Hopkins 等統計量。

### ③ 線條圖 → 指定分數

1. 上傳黑線白底圖（透明背景 PNG 也可以，透明處視為白紙），或按「載入內建示範」選擇內建圖形：魚、人臉、同心圓、愛心、一箭穿心、小貓臉、小狗臉、小熊臉、兔子臉、笑臉、星星、房子、花朵、樹、太陽、雪花、蝴蝶、月亮星星、雨傘（程式碼在 `presets.py`，可自行增加）。
2. 設點數，例如 180，按 ① 將線條細化成骨架後用近似均勻間距策略布點。
3. 設目標分數，例如 `-0.13`，誤差 `0.035`，迭代次數 `3600`。
4. 設定「最大離線距離」和「最低線條保留率」（如 0.65）。當兩項保形限制令指定分數不可行，程式會明確顯示「未達標」並提示可放寬的設定。**實測：預設最大離線距離 0.09 時，人臉約只能到 −0.42、魚約 −0.96；要達到 −0.13 這類接近隨機的分數，需勾選「允許離線移動不限距離」**（`preview_face_optimization.png` 即為此模式）。
5. 按 ② 最佳化；比較原始線條、起始點圖與調整後點圖；查看 Hopkins、Ripley、總位移、平均位移、形狀保留率等。
6. 按 ③ 匯出結果：`before_points.png`、`optimized_points.png`、`optimized_overlay.png`、兩組 CSV 座標、前後完整指標 CSV、`optimization_report.json`。

**重要：** 這是隨機提案、退火接受率與回移微調結合的**啟發式約束搜尋**；它會懲罰偏離目標、原位移、離線距離，且設有輪廓保留率硬約束，但不保證數學上的全域最小總移動距離。某些分布（例如單一狹長閉合曲線）若仍須維持輪廓，可能根本無法達到接近 0 或 +1。這是需求本身的幾何衝突，並非所有情況都有精確解。

## 3. 分數如何計算？

**主要分數只使用 Hopkins + Ripley’s L**；其他統計只是輔助報表，不參與主分數。

**Hopkins H**：2D 最近鄰距離平方比。

\[
H=\frac{\overline{u^2}}{\overline{u^2}+\overline{w^2}}
\]

\(u\)：均勻探針到最近資料點的距離；\(w\)：每個資料點到最近其他資料點的距離。v1.1 的 \(w\) 使用**全部**資料點，探針為固定種子（2026）的分層抖動網格，數量 \(\max(2048,\ 24\lceil 0.1n\rceil)\)。所有頁籤、CLI 與最佳化器共用同一組探針，因此**同一組點、同一畫布比例，在任何地方算出的分數都相同**，也與點的排列順序無關。

> v1.0 依「點的索引」抽 10% 點計算 \(w\)：同一組點只要換順序（例如由 PNG 匯入時依掃描順序排列），分數就會變動（隨機圖標準差 0.036、最大 0.11）；批次頁與匯入頁又使用不同種子（差異標準差 0.042）；最佳化器也能只移動被抽中的點來「假達標」。v1.1 的期望值不變（隨機圖平均分數仍約 +0.01），只去除了抽樣雜訊；單張中間型圖形的分數約變動 ±0.03（最大約 0.09），極端群聚／規律圖形與線條圖起始分數不變。

（原始 Hopkins 檢定只抽 ~10% 點，是為了讓 \(H\) 在 CSR 下服從 Beta 分布以計算 p 值；本工具只把 \(H\) 當描述性指標，不計算 p 值，因此使用全部點較合適。）

\[
S_H = \begin{cases}
-\operatorname{clip}((H-0.5)/(0.95-0.5),0,1), & H\geq0.5 \\
\operatorname{clip}((0.5-H)/(0.5-0.20),0,1), & H<0.5
\end{cases}
\]

**Ripley L**：使用矩形觀察窗的 translation edge correction（平移式邊界修正），在五個半徑取平均；基準長度 `d=sqrt(A/n)`，半徑比例 `0.50, 0.75, 1.0, 1.25, 1.50`。

\[
D_L=\frac{1}{5}\sum_{i=1}^{5}\frac{r_i-L(r_i)}{r_i},\qquad S_L=\tanh(D_L/0.28)
\]

最後合成：

\[
\boxed{PPDI=\mathrm{clip}(0.70 S_H+0.30 S_L,-1,1)}
\]

Hopkins 0.95／0.20、Ripley 縮放 0.28 與權重 70%／30% 是**固定工程參數**，不是統計標準的唯一解，也不是經人類視覺評分訓練的結果。理論上完全隨機的期望分數接近 0，但**每張真正隨機產生的圖不必剛好等於 0**；這種偏離包含抽樣變異與估計變異。±1 是設計的有界方向，並非可以可靠達到的絕對物理極限。

### 附帶全部統計欄位

| 類別 | CSV 欄位 | 內容 |
|---|---|---|
| 主指數 | `score`, `hopkins_h`, `hopkins_component`, `ripley_index`, `ripley_component` | Hopkins + 多尺度 Ripley 複合評分 |
| Ripley 各尺度 | `ripley_r_*`, `ripley_k_*`, `ripley_l_*`, `ripley_l_minus_r_*` | 5 個半徑的 K, L, L−r |
| Pair correlation | `pair_g_*` | 5 個半徑環帶的 pair correlation 估計，非平滑密度估計 |
| Clark–Evans | `nni`, `nni_edge_corrected`, `nn_mean`, `nn_std`, `nn_cv` | 最近鄰指數與距離分布；`nni_edge_corrected` 使用 Donnelly 邊界修正（未修正的 `nni` 在 n=180 時約高估 3%） |
| Voronoi | `voronoi_area_mean`, `voronoi_area_std`, `voronoi_area_cv`, `voronoi_area_min`, `voronoi_area_max`, `voronoi_zero_cells`, `voronoi_resolution` | 用**最近鄰網格分區**近似裁切後 Voronoi 面積（至少 160×160，點數多時自動加密到每點約 64 格），並非精確多邊形求解 |
| Quadrat | `quadrat_vmr_4x4`, `quadrat_vmr_8x8`, `quadrat_vmr_12x12` 等 | 4×4、8×8、12×12 方格點數的變異數/平均數 |
| Fourier | `structure_factor_low_k`, `structure_factor_mid_k`, `spectral_peak_ratio`, `spectral_anisotropy` | Structure Factor 與頻譜尖峰／方向特徵 |
| XY 座標 | `x_mean`,`x_std`,`x_var`, `y_mean`,`y_std`,`y_var`,`xy_cov`,`xy_corr` | x、y 分別在 0～1 坐標下的平均、標準差、母體變異數、共變異數與相關係數 |

幾何距離型統計會按照 `aspect=width/height` 校正真實像素長寬比；CSV 的 x、y 均為正規化座標。

## 4. 非圖形模式 CLI（可在無 PyQt6 環境運行）

```bash
python cli.py generate --count 20 --points 180 --mode surprise --out output/experiment
python cli.py generate --count 12 --mode hybrid_any            # 7 種混合類型隨機
python cli.py generate --count 6 --mode ms_cluster_regular     # 指定一種多尺度類型
python cli.py analyze output/experiment/pattern_0001_xy.csv --width 1 --height 1
python cli.py analyze input_dots.png
python cli.py optimize samples/example_face.png --points 180 --target -0.13 --iterations 3500 --free
python cli.py presets                      # 列出內建圖形（中文名稱或英文代號皆可）
python cli.py presets --out samples        # 將全部內建圖形存成 PNG
python cli.py optimize 小貓臉 --target -0.13 --free
python cli.py optimize heart_arrow --target -0.5 --free
```

`--free` 取消「每一點最大離開線條距離」限制，但**仍保留** `--min-retention 0.65` 最低貼近線條比例；若要完全放開，搭配 `--min-retention 0`（可能無法辨識原圖）。`analyze` 另有 `--invert`（黑底白點）與 `--auto-bbox`；`optimize` 另有 `--invert`（黑底白線）。`generate` 與 `analyze` 也會輸出 L(r) 圖與數值（`*_Lr.png`、`Lr_curves.csv`／`Lr_curve.csv`）。`--mode` 可用：`random`、`cluster`、`regular`、`hybrid`、`ms_cluster_random`、`ms_random_cluster`、`ms_regular_cluster`、`ms_cluster_regular`、`ms_regular_random`、`ms_random_regular`、`hybrid_any`、`surprise`。

## 5. 方法的限制與建議

- 評分的基準是**整張指定畫布**，而不是只在圖像有墨線的局部區域評估。只在魚形輪廓上放點，統計上本來就可能呈現強群聚，即使沿魚身線條相當均勻。
- 非均勻強度的點過程、點數過少、邊界不明、長寬比誤判，都可能讓單一統計量產生誤導。建議同時觀察 NNI、g(r)、Fourier 等輔助統計。
- 目標分數是一個單一 scalar，不代表圖形完全相同；同樣的分數可以對應不同的局部空間結構。
- 把多張圖片做科學比較時，最好固定點數、畫布長寬比、演算法版本與亂數種子。
- PNG 上黑點相互接觸會合併，PNG 不是座標的無損表示；請保存 `_xy.csv` 做可重現的研究分析。
- 高點數、多張影像、大型線條圖，執行速度及記憶體成本會增加。

## 6. v1.2 新增（2026-10-30）

- 圖片按右鍵可「複製圖片」到剪貼簿或「另存圖片」（所有頁籤；複製原尺寸圖）。③ 的點圖預覽改用與匯出 PNG 相同的尺寸與點樣式。
- ① 批次與 ② 匯入分析新增 L(r) 圖：45° 虛線為完全隨機，灰帶為 39 次隨機模擬範圍，淡黃帶為評分使用的尺度。圖為正方形，X、Y 軸範圍與刻度相同；圖上文字為英文，標題不含編號。
- L(r) 數值結果（`lr_clustered_r`、`lr_regular_r` 等，見第 2 節）加入指標表與 CSV；匯入頁狀態列顯示一句話結論。L(r) 曲線另存 CSV（長表格式：pattern、r、L、L−r、K、隨機範圍）。
- 新增 6 種多尺度混合類型（見第 2 節表格）與「混合類型隨機」模式。原有 `hybrid` 的定義不變；`surprise` 現在有 1/4 機率抽到 7 種混合類型之一，所以**同一個亂數種子產生的 surprise 批次會和 v1.1 不同**。
- 主分數的計算完全沒有改：v1.1 與 v1.2 對同一組點的所有統計值逐位元相同。
- 修正：`hybrid` 在點數很少（3～4 點）時會當掉。
- 新增套件 matplotlib（L(r) 繪圖）。

## 7. v1.1 修正紀錄（2026-10-29）

原始 v1.0 檔案保留在本機資料夾 `backup_v1.0_original/`（未上傳到 GitHub）。

**啟動**
- `run_windows.bat` 雙擊無法啟動：檔案為 LF 換行，cmd 解析錯亂。改為 CRLF，並改用 `py` 啟動器、缺套件才安裝、失敗時暫停顯示原因。

**計算**
- Hopkins 分數依點的排列順序而變、各頁籤種子不一致、最佳化器可「假達標」：見第 3 節，已改為全部點計算 \(w\)＋全域固定探針。
- 群聚／混合模式把超出畫布的點夾到邊框上（強度 0.3 時約 6.8% 的點疊在邊線上）：改為重新抽樣；群聚形狀與規律格點抖動依畫布寬高比校正，寬圖的群聚不再被拉成橢圓。
- Fourier 方向異向性以各方向扇區的「總和」計算，而各扇區像素數不同（200～250），隨機圖也顯得有方向性：改用平均值（隨機圖異向性 0.40 → 0.31）。
- 新增 `nni_edge_corrected`；Voronoi 網格依點數自動加密。
- 「自身邊界縮放」原本強制寬高比 = 1，改為依資料邊界的實際寬高比。CSV 支援加引號的欄位。

**最佳化器**
- 移除「交換兩點」提案（幾何完全不變，只是在鑽 Hopkins 索引抽樣的漏洞），改為局部最佳移動；「跳到空位」的候選點改在允許的離線範圍內產生，減少白費的提案。同樣條件下人臉可達分數由 −0.54 改善到 −0.42。
- 修正 `iterations=0` 會當掉、提前達標時保留率寫死 100%、提案被拒時進度不更新、取消時迭代數多算 1。

**圖片與介面**
- 透明背景 PNG 原本整張變黑（全部視為線條）：透明處改視為白紙；手機照片依 EXIF 自動轉正。
- 非正方形圖片的預覽與匯出 PNG 原本固定 680×680／800×800 而變形：改為保持原比例。
- 「① 解析線條」改在背景執行，點數多時視窗不會凍結；錯誤訊息先顯示簡短原因，詳細 traceback 收在「Show Details」。
- 新增 16 種內建線條圖（`presets.py`），CLI 可直接用名稱呼叫。

**尚未處理的建議**
- Ripley 的 \(L=\sqrt{K/\pi}\) 是凹函數，有輕微 Jensen 偏差，使隨機圖平均分數略為正（約 +0.01），影響很小。
- Fourier 與 quadrat 指標在正規化座標 [0,1]² 計算；非正方形畫布時，方向與方格形狀是在拉伸後的空間量測。
- 評分以整張畫布為觀察窗：只有線條的圖必然偏群聚，若想比較「沿線條的均勻度」，需要另外定義以線條為基底的指標。

## 8. 參考資料

- [R Journal (2022): Will the Real Hopkins Statistic Please Stand Up?](https://journal.r-project.org/articles/RJ-2022-055/)
- [spatstat：Ripley L](https://search.r-project.org/CRAN/refmans/spatstat.explore/html/Lest.html)
- [spatstat：pair correlation](https://search.r-project.org/CRAN/refmans/spatstat.explore/html/pcf.html)

以上參考說明方法定義，**不代表這些文獻提出或驗證本專案的 PPDI 合成公式**。

## 9. 授權

GNU Affero General Public License v3.0（見 `LICENSE`）。
