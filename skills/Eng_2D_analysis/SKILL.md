---
name: Eng_2D_analysis
description: >-
  2D 工程圖處理:①解析向量 PDF 工程圖為結構化 JSON(標題欄、尺寸、公差、GD&T、視圖、投影法/單位/標準判別)
  ②用 ezdxf 繪製工程圖(出 PDF + DXF,第一角/第三角,ASME/ISO/JIS 變體)③由 2D 圖面逆向 3D(FreeCAD PartDesign::Body)。
  另含④由 STEP/FreeCAD 3D 自動量測並出 2D 尺寸圖(drafter from-step,僅旋轉件)⑤非 PDF/點陣影像乾淨拒絕(exit 2)⑥閉環自檢流程。
  含標準自動判別(DIN/JIS/ASME)、驗證守則與誠實的已知限制。僅在單一 CAD 來源的少量向量 PDF 上驗證過,泛化未量測。
  觸發: 2D 工程圖, 圖面解析, 工程圖 PDF, 解析圖面, GD&T, 幾何公差, 特徵控制框, 標題欄, title block, 投影法,
  第一角, 第三角, first angle, third angle, 逆向 3D, 圖面轉 3D, 出圖, 繪製 DXF, 產生工程圖, STEP 轉 2D, 3D 轉 2D 圖, 尺寸圖, 點陣圖面, DIN, JIS, ASME, ISO 128, Y14.5, drawing parser, drafter.
---

# Eng_2D_analysis — 2D 工程圖 解析 / 繪製 / 逆向 3D

實作在本 repo 根目錄 `<PROJECT_ROOT>/`(`Parser/`、`Drafter/`、`Analysis/`)。
本 repo 為公開版:已去除專有圖面與衍生資料(見 `EXCLUDED.md`、`CHANGES_FROM_VALIDATED.md`);**公開版未經 QE 重驗**。影像相關(分診/OCR)屬另一個獨立工具,本 repo 不含。
先看本檔「已知限制」再決定能不能用——這套東西只在少量同 CAD 來源的向量圖上做出來,**不是通用解析器**。

## 何時使用
- 使用者給「向量 PDF 工程圖」要抽標題欄/尺寸/公差/GD&T/視圖/比例/投影法 → 流程 A
- 要從 FreeCAD 零件產生帶標題欄、尺寸、GD&T 框的 PDF+DXF 圖 → 流程 B
- 要由 STEP/FreeCAD 3D 模型產生帶尺寸的 2D 圖(僅旋轉件) → 流程 B2(`drafter from-step`)
- 要從 2D 圖面重建 3D(FreeCAD) → 流程 C
- 要判斷圖面屬 ASME / ISO(DIN) / JIS 體系 → 流程 A 的 `standard` 欄 + 下方判別步驟
- 要檢查「原圖→解析→3D→重新出圖→再解析」一致性 → 閉環流程
**不要用於**:掃描/點陣 PDF、影像檔、DXF/DWG 輸入(解析器乾淨拒絕並回 exit 2,**不會解析**)、非本工具驗證過的 CAD 匯出 PDF(未測,結果不可信)。遇到先告知使用者不支援;點陣圖面目前只能由人目視讀圖。

## 環境(強制)
- Python 使用官方簽章版直譯器(下文以 `<PYTHON>` 代稱)。作業系統的應用程式控制可能擋未簽章 python(含部分 venv/portable),被擋就換回簽章版,不要硬繞。
- 依賴:PyMuPDF 1.27.x、ezdxf 1.4.x(先確認已安裝;不假設有網路)。FreeCAD 走 `freecadcmd`(命令列),**不開 GUI/視窗**。
- 輸出報告類交付物放專案 `Reports/`;終端機編碼注意 UTF-8(`PYTHONIOENCODING=utf-8`),亂碼(如 °)多為 code page 假象,先查 JSON 本身。

## 流程 A:圖面解析(PDF → JSON)
```
cd <PROJECT_ROOT>/Parser
<PYTHON> -m drawing_parser <drawing.pdf> -o out.json     # 自動 schema 驗證
<PYTHON> -m unittest discover -s tests                   # 公開 repo 僅含合成輸入的拒絕/lexicon 測試(其餘需自備圖面與 golden,見 tests/README.md)
```
**結束碼(Parser 0.2.1)**:

| 碼 | 意義 |
|---|---|
| 0 | 成功 |
| 1 | 內部錯誤或寫檔錯誤 |
| 2 | 不支援的輸入(乾淨拒絕) |
| 3 | 輸出未通過 schema 驗證(0.2.0 以前為 2,已改 3) |

**影像/不支援輸入的拒絕**:依檔頭魔術位元組(副檔名只作提示)辨識 PNG/JPEG/WebP/GIF/BMP/TIFF/DXF/DWG、空檔、不存在檔、損毀/截斷/加密 PDF、純影像(掃描)PDF → 輸出合 schema 的 JSON(`status: unsupported_input`、`detected_type`、`reason`、建議),stderr 一行,**無 traceback、無任何猜測尺寸**。註:掃描 PDF 只在 CLI 路徑(`parse_input`)被拒;函式 `parse_pdf()` 保留「警告+空結果」行為。

輸出 JSON 摘要(schema 見 `Parser/drawing_parser/schema.py`):
- 每個事實都是 `field = {value, confidence 0..1, evidence[], basis}`;`basis` ∈ `independent_text`(印在圖上的字)、`geometry_measured`(從向量量得)、`decoded`(筆劃字形自解,上限 0.85,不算獨立)、`inferred`(上限 0.90)、`unverified`(≤0.30)。
- 頂層鍵:`schema_version, parser, source, honesty, pdf, sheet(paper, inner_frame, regions), titleblock(drawing_number, version, scale, format, sheet, lifecycle_status, drawing_name, mass, material, projection_text, notes, revisions, bom), standard(projection, unit, decimal_marker, paper_family, thread_notation, gdt_standard_cited, overall), views[], dimensions[], dimensions_skipped[], tables[], gdt(fcf[], datums[], basic_dimensions[], symbols_unplaced), validation_summary, warnings[]`。
- `dimensions[]`:`text, kind(linear|diameter|radius|unknown), value, count(2X), reference, basic, tolerance(sym|stacked), geometry{status, scale_used, ...}`。
- `geometry.status`:`agree`(文字值=箭頭/圓弧量得值,兩源)、`agree_other_printed_scale`(較弱,0.90)、`consistent_unprinted_scale`(0.80,**不算獨立確認**)、`disagree`(0.5)、`unmeasured`。**必讀 warnings 與 dimensions_skipped**:角度、倒角、HEX、螺紋、粗糙度(Ra)目前不抽成尺寸,只列入 skipped(含分類與數字),不會靜默消失。
- 不要把 `disagree` 直接當「文字錯」:常是視圖比例綁錯(見限制)。

## 流程 B:繪製(FreeCAD 零件 → PDF + DXF)
```
cd <PROJECT_ROOT>/Drafter
<PYTHON> -m drafter <part.FCStd | features.json | geom.json | spec.json> --standard asme|iso|jis --projection first|third -o out [--spec s.json] [--template t.json] [--scale n] [--refresh]
```
- 引擎=ezdxf(真 DIMENSION 實體、GD&T 以 BLOCK 向量符號、PDF 附不可見文字層);FreeCAD 僅當幾何來源(HLR 投影,唯讀開檔,input 須含 `PartDesign::Body`)。
- 預設投影:asme→第三角、iso→第一角、jis→第三角(**低信心**,只有二手來源)。圖面內容由 `*.spec.json` 指定(視圖、尺寸位置、GD&T 位置、註記);無 spec 時只有自動 3 視圖+外形尺寸,**未驗證**。尺寸/GD&T 位置為手調,無自動避讓。
- 標題欄是模板驅動(公開版為 `generic_a3.template.json`,無品牌字樣);Drafter 自加的參考尺寸必須括號並在圖上註明來源。
- 產出狀態一律 `DRAFT (GENERATED)`,不得標 RELEASED。

## 流程 B2:STEP/3D → 2D 尺寸圖(`drafter from-step`,僅旋轉件)
```
cd <PROJECT_ROOT>/Drafter
<PYTHON> -m drafter from-step <part.step> [--projection first|third]
```
- 做法:`freecadcmd` 讀 STEP,**由幾何自動量測**旋轉軸、各段直徑/長度、溝槽、倒角、六角孔、螺紋(據螺旋幾何推公制規格、螺距、旋向;鏡像副本會翻成左旋),再用 ezdxf 畫:側視圖、端視圖、剖視(剖面線)、局部放大、真 DXF 尺寸、材料/比例/質量(質量用命令列指定的密度計)。輸出 PDF+DXF+PNG,交付複本放 `Reports/`。
- 驗證現況:僅以一個簡單旋轉件示範;與原 PDF 比對,大多數尺寸同值、少數量測基準不同;自加參考尺寸以括號標示、不計獨立;結構檢查、突變檢查、鏡像/旋轉副本測試通過。**未經獨立 QE**。
- 限制:**單一旋轉件示範**,尺寸位置手調;STEP 不含的公差/螺紋等級/粗糙度不畫;一般公差(ISO 2768-m)是**標明的佔位**非由模型導出;材料取自原圖/參數非 STEP;螺紋依真實螺旋畫,不是符號畫法;圖面標示 `DRAFT (AUTO-GENERATED)... NOT A RELEASED DRAWING`。**不可宣稱可處理非旋轉件、鈑金件或組件。**

## 流程 C:逆向 3D(2D 圖 → FreeCAD PartDesign::Body)
方法論全文:`Analysis/REVERSE_3D_METHOD.md`。管線:`extract_features.py`(PDF 向量→geom.json)→ `chain.py`(封閉迴圈)→ **特徵配方**(`make_features.py`,零件專屬函式,**無通用路徑**,新零件要新寫;公開版不附)→ `build_fcstd.py`(`freecadcmd build_fcstd.py`,環境變數 `BOT_PARTS`、`BOT_ROOT`)→ 回投影驗證。
要點:視圖依投影法對位成零件座標;封閉迴圈→Pad;圓+貫穿邊→Pocket;軸對稱→Revolution;多視圖輪廓柱→視圖交集;順序 基體→減料→附加→邊修飾;圓角保留在 Sketch 輪廓內,不拆 Fillet(topological naming 風險)。
(第二批不同圖面曾需要大量改碼,見限制;該報告未隨公開版提供。)

### FreeCAD 規則(強制)
- 主體必為 `PartDesign::Body`;特徵(Pad/Pocket/Revolution/Groove…)全掛特徵樹;腳本路徑 `Body → Sketch → Pad`,Sketch 附著原點基準面。
- **禁止** `Part.makeSolid` / BRep 直接造體當主幾何;Part 只可做 Mirror/Array 等輔助或量測(slice/common 僅量測)。Sketch 幾何元素 `Part.LineSegment/Circle/ArcOfCircle` 允許。
- 多零件組件用 `App::Part` 容器包多 Body;單 Body 不能含互不相連實體。
- 從 STEP 匯入時需 Part Design 重建,告知使用者,不要把殼包成 Body 了事。
- 覆蓋模型檔前先備份(`build_fcstd.py` 會備份到 `Models/_backup/<時間戳>/`)。

## 標準自動判別步驟(`standard_detect.py`;KB 見下)
依序觀察並投票;**它是 KB 表格投票,不是分類器,KB 信心未校準**。
1. 投影法:讀標題欄文字 THIRD/FIRST ANGLE → 第三角=US/JP,第一角=DE/ISO(KB 72)。**美/日無法由此區分**。符號圖形方向 **UNVERIFIED**(單一二手來源),不使用。
2. 單位:`ALL DIMENSIONS ARE mm` → mm(對 JP/DE/ISO 僅弱證據,公制 ASME 圖存在);分數/`.XXX` 英吋 → US。
3. 小數標記:逗號 → DE 正證據(對 US);句點不能分 JP 與 DE。**JP 小數點慣例 UNVERIFIED**。
4. 紙張:A 系列(短/長≈0.707)→ JP/DE/ISO;ANSI → US(0.90)。
5. 螺紋:`M<d>x<p>`(含 ×、*)→ 公制(ISO/JIS/DIN);分數-TPI-UNC/UNF → ASME。
6. 引用標準:`ISO 2768`/`DIN ISO 128/5456` → ISO/DE;標題欄聲明 `ASME Y14.5-2009` → 依 ASME 解讀(0.85)。
7. 組合:第三角+公制+A 系列 → 傾向 JP;第三角+英吋/UNC+ANSI → 傾向 US;第一角+公制+A+逗號/DIN → DE;第一角+公制+A 無 DIN 特徵 → ISO 通用,不硬判 DE。
**低信心(KB `DRAFTING_STANDARDS_COMPARE_KB.md` §6 UNVERIFIED,僅作 ≤0.30 提示,不入票)**:線型/線寬比差異、投影符號圖形方向、日本小數點與千分位、日文一般公差等級名、JP/DE 標題欄詞彙、ISO 129-1 小數標記是否強制逗號、JIS B 0001 是否容許第一角、JP 專屬可偵測特徵、尺寸文字方向(aligned vs unidirectional)國別慣例。**JIS 預設第三角法僅 72%(二手來源)**。
報告時:觀察(文字/頁面量測)與推論(投票)分開講,不要把 `overall` 當事實。

## 閉環流程:原圖 → 解析 → 3D → 重新出圖 → 再解析 → 比對(單次小樣本試驗經驗,**僅 3 個零件,不外推**)
經獨立 QE 審查,結論以 QE 為準。標記:[已驗]=實跑且 QE 重現;[推論];[未重測]=QE 判定證據不足。

**一致率的誠實表述**
- 旋轉件 A(legacy 專用路徑):「人依原圖預選一組尺寸位置,STEP 量值與名義值大多相符;公差項 0 件相符。尺寸**選擇是人寫死的(循環)**,不證明能自動選尺寸。」
- 簡單旋轉件 B:「自動窮舉出尺寸,原圖尺寸全數涵蓋(recall 滿分),但 precision 不滿;都是外形尺寸,資訊量低,不外推。」不給 `--from-parse` 結果相同,故尺寸選擇獨立。`--rev` 表頭「SAME」是從原圖 parse 抄來的,**不算閉環證據**。
- 螺旋彈簧類零件:出圖階段不支援(閉環 0/0);表格值與 3D 獨立量測相符。
- **一致率是 recall,不是保真度**;比對器**沒有 pass/fail、exit code 永遠 0**;投影法/標準/比例/單位只在 md 表頭顯示 DIFF,不影響一致率。

**步驟與契約**(在專案的分析資料夾內執行;可用一鍵腳本串接,不含獨立 3D 量測約數十秒內 [已驗])
1. `<PYTHON> -m drawing_parser <原圖.pdf> -o <p>.parse.json`
2. 獨立 3D 量測(freecadcmd,`measure_independent.py` 弦長法,唯讀 STEP,**與 Drafter 的 face-table 量測不同方法**)
3. 出圖:`<PYTHON> -m drafter from-step <step> --rev --from-parse <parse.json> -o <dir> --stem <S>`(旋轉件;其中一件走 legacy 專用路徑)
4. 對新 PDF 再解析
5. `compare_loop.py` 比對:分母=原圖 `dimensions` 筆數;分子=同 kind、同值(容差約 ±0.006);自加參考尺寸、公差/GD&T 不計。三態規則:UNCONFIRMED / NOT-MEASURABLE / DEVIATION,量不到不得記成通過或偏差。

**但 QE 發現**:有真偏差的件只會判 UNCONFIRMED,不會是 DEVIATION;`--rev` 沒有任何測試,也不檢查 STEP 與 parse 是否同一零件(拿 A 的 STEP 配 B 的 parse,會畫出標 B 圖號的圖)。

**斷鏈清單(可直接用)**
1. 標題欄**標籤字樣是閉環的契約**:出圖模板標籤對不上 Parser 時,新圖圖號/品名/比例讀成 None;`--rev` 模板改成 `DRAWING NUMBER`、`DRAWING NAME / DESCRIPTION`、單行 `FORMAT: A3 SCALE: n:1 SHEET: 1 / 1` 並保留分隔線後,表頭各欄與原圖相同 [已驗]。
2. 材質格被一般公差文字污染會讓 `material`、`gdt_standard_cited` 讀錯(例如把原圖的 ASME Y14.5 讀成 ISO 2768)[已驗]。
3. 視圖:新圖畫了 3 個視圖,Parser 只讀回 2 個(漏端視圖);Drafter 不支援等角圖/細部圖/剖視以外的視圖;逐視圖比例不復現。
4. 圖紙/比例:僅 A3 模板(原圖為 A2 時不符);`--rev` 繼承 parse 比例 [已驗]。
5. 投影法只比文字(符號畫反抓不到)[已驗+推論]。
6. 解析器不當尺寸的類別:倒角、螺紋規格、`HEX`、粗糙度 `Ra` 進 `dimensions_skipped`,閉環只能比「類別存在與否」[已驗]。備註文字(溫濕度等)會被誤分類為雜訊。
7. 公差遺失:原圖帶公差的尺寸,STEP 不帶 → 新圖 0;公差/基準/GD&T/粗糙度/螺紋等級/材質屬「3D 不可恢復」,必須人工補 [已驗]。
8. 自加參考尺寸的註記字串會被 Parser 當 `unparsed_numeric` 雜訊;**「比對時忽略此條」目前只是建議,比對器沒實作**(因此出現假配對)。
9. GD&T:Drafter 產出的 GD&T 非原 CAD 的 0.14pt 筆畫,Parser 讀不到(`no 0.14pt stroke text found`)[已驗警告]。
10. 螺旋件無旋轉軸:`step_probe` 以 cylinder/cone/torus 面找軸,彈簧只有 B-spline 面 → `not a body of revolution`,拒絕出圖;**慣性矩對稱不能當旋轉件判據** [已驗]。要支援需新「彈簧模式」(HLR 視圖+彈簧數據表)[推論]。
11. 尺寸在表格:Parser `dimensions=0`,數值在 `tables`,比對器須另走表格路徑;材料標準編號可能被誤收為 GD&T 標準 [已驗]。
12. FreeCAD `BoundBox` 對環面偏鬆(半徑量得值明顯大於真值):長度/直徑改用垂直軸平面與圓柱面參數,不要用 bbox [已驗]。
13. [未重測] Windows 陷阱:console cp950 印 `Ø` 會 UnicodeEncodeError → `PYTHONIOENCODING=utf-8`;freecadcmd 路徑含空白要加引號;PowerShell `$ErrorActionPreference=Stop` 會把拒絕出圖的 stderr 當例外,出圖階段改看 exit code(QE 判:無紀錄佐證,視為經驗提示)。

**人工介入點**:公差/基準/GD&T/粗糙度/材質/螺紋等級;legacy 路徑要畫哪些尺寸;圖紙大小(A2)與逐視圖比例、等角圖、細部圖;螺旋件與非旋轉件(無出圖路徑)。
**QE 的 minor**:螺紋比對靠寫死的小容差;新圖標註文字貼線;原圖備註/修訂欄/等角圖未再現;測不到的突變類:視圖增刪、把 DRAFT 換成 RELEASED、視圖綁定打亂、真偏差件。

## 驗證守則(honest-gates)
1. **獨立 vs 自驗**:獨立=與產生模型的資料來源無關(圖上印的文字 vs 向量;原 PDF 以 PyMuPDF 另行讀字)。自驗=同一向量既建模又量測(偏差必≈0),只證建模無誤,**不計入通過率**。回投影覆蓋率、Drafter 自加參考尺寸、凍結的 GD&T 文字都屬此類。
2. **循環驗證陷阱**:golden 不得由被測程式輸出貼成;修缺陷時看過的圖,事後就是迴歸集、**不得再當盲測/泛化分數**。模型由 PDF 建、再用同 PDF 驗,100% 覆蓋不代表語意正確(曾有一件因主視圖是點陣圖而整個錯、且比例錯數倍,向量覆蓋率完全抓不到)。
3. **突變檢查**:新增斷言先「弄紅一次」(改期望值/受測碼);Parser 有 `tests/mutation_check.py`(挑選突變)、Drafter 有 `verify_outputs.py --selftest`。**突變分數是挑選樣本分數,非覆蓋率**:QE 用新突變打 Parser 只殺 15/24。單向斷言(只測 agree、不測 disagree)是假綠。
4. 回報時分列:獨立項通過數 / 自驗項 / 推論 / 未驗;GD&T 附著目標、all-around、範圍符號都是推論。
5. 錯誤要大聲:靜默丟棄是缺陷(已修的 `±` 筆劃字、零限值公差曾靜默丟尺寸)。

## 已知限制(誠實清單,回報時不得省略)
1. 只在**少量(個位數)同 CAD 來源的向量 PDF**(A3 與 A2)上開發驗證;同標題欄模板、同單線字型。其他公司/CAD/標題欄 = **未測**。目前沒有可用的非同源向量盲測樣本,**要量測泛化,仍需一批新來源的向量圖面**。
2. **泛化 0/4**:第一批流程套到第二批 4 張不同圖面,零改碼端到端 0/4(第一個腳本就當掉),需修補 build 並全新寫配方與驗證;Parser 首輪盲測 0/4 完全正確、公差正確率 44%。該批已被拿去修缺陷,**不再是盲測**,目前無任何泛化百分比可引用。**泛化未量測。**
3. **影像(PNG/JPG/WebP/GIF/BMP/TIFF)、點陣/掃描 PDF、DXF/DWG 不支援,只做乾淨拒絕**(v0.2.1 起 CLI:exit 2、JSON `status:"unsupported_input"`,不解析、不 OCR;exit 碼 0/1/2/3;函式 `parse_pdf` 對點陣頁仍只給 `scanned/raster` 警告與空結果);僅讀第 1 頁。向量 PDF 內**嵌入的點陣視圖仍會被靜默忽略**(曾有一件成形主視圖即是)。
   - 點陣圖面的人工目視讀圖受解析度上限限制(約 6px 的文字不可讀),演算法無法補;簡易 OCR 探針召回率差、無標準答案,**不可當解析結果**。點陣分診/OCR 候選不屬本工具。
4. 許多常數是特定 CAD 匯出版面專用:0.14pt 單線字、17pt FCF 列高、實心等腰箭頭 6–14pt、標題欄錨定框角、10pt 視圖合併距離;無框線表格找不到。
5. **尺寸→視圖綁定僅用文字距離**(最近視圖 bbox ≤250pt),不看箭頭所在;錯綁時正確值會被標 `disagree`。視圖比例精修需 ≥2/≥3 個可量測尺寸;單尺寸視圖維持標題比例。`geometry.scale_used` 與精修後視圖比例可互相矛盾,只看狀態欄。
6. **GD&T 只讀 0.14pt 筆劃字形**,且需要**使用者自行用 `Parser/tools/build_lexicon.py` 由自己的圖面產生字形字典**(公開版不附;缺字典時 Parser 優雅降級:warnings 註明「lexicon 未提供」、FCF confidence 上限 0.3、僅能辨識該 PDF 自身文字層可標註的字形)。原開發用字典在樣本內;未見過未知 FCF(僅 leave-one-out)。非同類單線字型 CAD 匯出,或字型向量化不同,則解 0 個(Drafter 產出的 PDF 回讀 FCF 為 0/4)。符號種類僅見位置度、輪廓度(面)、平面度;其餘 11 種 Drafter 有畫但從未對標準檢驗。
7. 不當作尺寸抽取:角度、倒角、HEX、螺紋、Ra、座標/鏈式/基線尺寸、焊接符號、同心/對稱/跳動、`3X` FCF 前綴、引線到特徵附著(僅列入 skipped 或不處理)。
8. **QE 非正常過閘**(內部版本結果):Parser 第二輪 QE 78/100(SE 自評 90,QE 認為高約 10 分)、Drafter 第二輪 QE 84/100(ME 自評 90、SE 75);均未達正常過閘線,以「已知缺陷揭露」交付,不是全綠。Parser 新突變 15/24 殺、8 個真存活;Drafter 閘幾何保真度未受閘(移孔 1.5mm、刪輪廓線仍綠)。`from-step` 與 0.2.1 影像拒絕為自評,**未經獨立 QE**。**本公開版另經去衍生內容修改,未經 QE 重驗**,分數不適用於本版。
9. **Drafter**:僅在 2 個零件(旋轉件、折彎沖壓件)驗證(外加 `from-step` 單件旋轉件示範,QE 未審);其中 12 個尺寸有 4 個非原圖印製(自加參考尺寸);asme 變體只是「近似某 CAD 圖面」,標題欄非像素級、無 logo/剖面/等角圖;iso/jis 僅投影預設、聲明文字、一般公差註記與文字置放不同;公開版一般公差表為通用 ISO 2768-1 m 公開值(可自行替換);ISO 聲明字句為 Drafter 自擬。**投影法無法分美/日**。
10. 逆向 3D:**鈑金折彎件成形件僅約 40%**(缺凸耳/端板/包覆/寬度變化);**PCBA 為包絡級**(元件高度無獨立來源,部分元件不建;不可作干涉/BOM 依據);圓角不能在特徵樹改 R;`make_features.py`/`verify_models.py` 為零件專屬(公開版不附),無通用配方;部分圖面視圖分割需人工視窗檔;尺寸文字 ≠ 真實值的情形(展開圖紙面值為真實值數倍)流程無法自動偵測;公差帶/GD&T 無法由名義模型驗證。
11. 某件圖的 `3X` 複合框與可見缺口數矛盾,未解;JIS 第三角預設、ISO 5456-2 符號方向皆僅二手來源。

## 知識庫與文件(指向,不複製)
KB(使用者自備的 references 資料夾,未隨本 repo 提供):`DRAFTING_STANDARDS_US_JP_DE_KB.md`、`DRAFTING_STANDARDS_COMPARE_KB.md`(判別決策表與 §6 UNVERIFIED)、`DRAFTING_AUTOMATION_KB.md`、`DRAWING_PARSING_KB.md`、`GDT_GEOMETRIC_TOLERANCING_KB.md`。
本 repo 文件:`README.md`、`Analysis/REVERSE_3D_METHOD.md`、`EXCLUDED.md`、`CHANGES_FROM_VALIDATED.md`。原內部文件(Parser/Drafter README、解碼結果、QE 報告、泛化報告、閉環教訓)未隨公開版提供。
