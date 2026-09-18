---
title: "圖形手術"
sidebar_position: 3
---

# 圖形手術

大多數模型在運算子和張量形狀受到 Model Compiler 的支援時，可以直接進行編譯。在變更模型之前，請檢查 [模型相容性](./model-compatibility.md) 清單，並首先嘗試標準的編譯流程。

圖的修改是一種進階步驟，適用於需要在編譯之前或在 SiMa 裝置上高效執行之前，對圖進行有針對性的變更的模型。您可以對原始 Python 模型程式碼進行這些變更，然後再次匯出模型，或者您可以直接編輯匯出的 ONNX 圖。

SDK 包含一個預先建置的 `sima-model-surgery` 技能，適用於 Codex 和 Claude。請要求代理程式檢查您的模型，它可以檢查相容性、提出並應用所需的圖修改，驗證結果，並為另一次編譯嘗試準備模型。此技能對於 YOLO 模型特別有用，因為圖的修改可以提高編譯器的相容性，並優化模型輸出，以用於 SiMa 執行時間。

例如，您可以這樣詢問：

```text
Use the sima-model-surgery skill to inspect my YOLO model, optimize unsupported
graph sections, and validate the modified model.
```

## 了解圖的修改操作。

圖結構修改會改變神經網路運算圖的結構。當模型在量化、編譯或部署之前，需要進行有針對性的修改時，請使用此功能。

常見的原因包括：

- 客製化一個預先訓練好的模型。
- 替換一個 Model Compiler 不支援的運算子。
- 重新設計或重寫圖形運算，以避免阻礙高效的編譯。
- 優化模型圖，讓更多模型能在 MLA 上執行。
- 針對目標裝置或部署限制，調整模型。

## 選擇要變更的位置。

這個 Model Compiler 會定期更新，以支援更多運算子。
有些模型在所有層都能在 MLA 上執行，或是在模型達到效能目標之前，仍然需要進行圖結構的調整。

如果可能，請在原始模型程式碼中進行變更，例如： PyTorch 或
TensorFlow 產生已匯出模型的模組。通常，對原始碼層級進行的修改更容易進行審查、測試和維護。

當無法對原始碼層級進行修改時，請編輯已匯出的模型。 ONNX 圖。接下來的內容將著重於。 ONNX 圖的結構是因為 ONNX 是 Model Compiler例如，您可以將非 4D 張量重新塑形為 4D，或將不受支援的運算子替換為受支援的替代運算子。 Model Compiler 包含 `sima-utils` 套件。匯入 ONNX 輔助工具
在您修改圖之前使用的模組：

``` python
from sima_utils.onnx import onnx_helpers as oh
```

如需了解 Model Compiler API，請參閱 [ AFE API 參考資料 ](/reference/model-sdk-api/)。

## 分析 MLA 的涵蓋範圍。

西馬 MLSoC 使用以下執行後端：

- 現代語言學會
- CVU（EV74）
- APU（A65）

在編譯期間，Model Compiler 會在可行時將運算子指派給 MLA。無法在 MLA 上執行的運算子會對應到 CVU 或 APU。這可能會將模型分割成多個 MLA 區段，並產生多個 `.elf` 檔案。

為了獲得最佳效能，請修改模型，以便更多部分在 MLA 上執行。如果整個模型都對應到 MLA，則編譯會產生單一 `.elf` 檔案。

首先，找出不對應到 MLA 的層。然後決定要替換或重新塑形的運算子。這需要同時使用 Model Compiler 的輸出，以及對 ML 運算子、DSP 處理和 MLA 支援的了解。

## 修改圖。

在您執行圖結構修改時，請使用此工作流程：

1. 使用 Model Compiler 編譯模型。
2. 找出那些無法對應到 MLA 的圖層。儲存並檢查 SiMa IR 圖。
   在 Netron 中，或啟用詳細的 Model Compiler 日誌記錄。
3. 修改已識別的圖層。如果這些圖層遍佈整個模型，
   首先將模型分割，然後一次修改一個部分。
4. 儲存修改後的模型。如果您將模型分割，請合併修改後的模型。
   子圖。
5. 使用原始模型和修改後的模型進行推論。比較
   輸出。
6. 使用 Model Compiler 編譯修改後的模型。
7. 確認在啟用完整 MLA 功能時，編譯程序會產生單一的 `.elf` 檔案。
   這是目標。

對於資料重塑的變更，例如 `Reshape`、`Slice`、`Concat` 和 `Transpose`，原始輸出和修改後的輸出在數值上應一致。如果變更影響數學運算的順序，則不預期完全匹配。在這些情況下，請評估數值差異和模型層級的準確性。

有關 MLA 運算子的支援，請參閱 [模型相容性](./model-compatibility.md)。

## 檢閱 ONNX 圖的結構。

ONNX 是一種 [開放規格](https://onnx.ai/onnx/)，其基礎為協定緩衝區 (Protocol Buffers)。一個 ONNX 模型包含：

- 一個可擴展的計算圖模型
- 標準資料類型
- 內建運算子

圖模型和資料類型構成了 ONNX 中間表示 (IR)。內建運算子由 OPSET 規格定義。

![ ONNX IR 層級結構 ](./media/graph-surgery/ONNX_IR_Hierarchy.png)

一個 ONNX 圖定義了模型的計算。它包含節點，這些節點通過它們的輸入和輸出形成一個有向非循環圖。這等同於其他深度學習框架中的「網路」或「圖」。

ONNX 圖實體通過名稱進行引用：

- 值名稱包含圖的輸入、圖的輸出、節點的輸入、節點的輸出。
  以及常數。
- 節點名稱使用一個獨立的命名空間。
- 當一個節點的輸出和另一個節點的輸入都指向同一個目標時，圖中的邊就存在。
  具有相同值的名稱。

## 存取圖的欄位。

在載入模型後，您可以透過以下方式存取圖層級的欄位：

- `model.graph.node`：節點
- `model.graph.input`：圖的輸入。
- `model.graph.output`：圖的輸出結果
- `model.graph.initializer`：常數

您可以移除、修改或新增圖層級的元件。

透過以下方式存取節點層級的欄位：

- `node.name`：節點名稱
- `node.op_type`：運算子類型
- `node.input`：節點輸入
- `node.output`：節點輸出
- `node.attribute`：節點屬性

您可以移除、修改或新增節點層級的元件。

## 驗證修改後的模型。

一個 ONNX 檔案是一個 protobuf 訊息。您可以使用任何能夠讀取或寫入 protobuf 訊息的工具來檢查它。要驗證一個 ONNX 模型，請使用 `onnx.checker.check_model`。

模型檢查器會驗證：

- 紅外線（IR）版本的相容性
- OPSET 相容性
- 模型一致性

在對圖進行修改後，且在將修改後的模型儲存到磁碟之前，務必執行模型檢查器。

請使用以下最終驗證流程：

1. 載入 ONNX 模型。
2. 執行圖的修改操作。
3. 移除現有的推論形狀資訊。
4. 使用 `onnx.checker.check_model` 驗證修改後的模型。
5. 儲存修改後的模型。
6. 驗證修改後的模型是否準確。
