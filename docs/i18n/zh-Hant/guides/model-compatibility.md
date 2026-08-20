---
title: "模型相容性"
sidebar_position: 2
---

<!-- 由 scripts/build_supported_operators_md.py 自動產生。請勿手動編輯。 -->

# 模型相容性

SiMa.ai 編譯工具鏈會導入 **ONNX** 模型，並為機器學習加速器 (MLA) 準備運算子。請使用此頁面來檢查運算子支援情況，然後再為 Modalix 準備模型。

## 支援的運算子

請使用表格來檢查 MLA 編譯器是否支援特定運算子和精確度方案。**INT8** 可以在 MLA 上執行。**BF16** 則可在 Modalix 上使用（開發者預覽版）。**5D** 表示接受 5D（N、D、H、W、C）張量的運算子。**Opset** 是 ONNX 的 opset 版本。

| 操作者 | INT8 | BF16 | 5D | 運營集 |
| --- | :---: | :---: | :---: | :---: |
| `Add` | ✅ | ✅ | — | 14 |
| `ArgMax` | ✅ | ✅ | — | 13 |
| `AveragePool` | ✅ | ✅ | — | 11 |
| `BatchNorm` | — | — | — | 15 |
| `BroadcastTo` | ✅ | ✅ | ✅ | — |
| `Clip` | ✅ | ✅ | — | 13 |
| `Concat` | ✅ | ✅ | ✅ | 13 |
| `Conv` | ✅ | ✅ | ✅ | 11 |
| `ConvTranspose` | ✅ | ✅ | ✅ | 11 |
| `CumSum` | — | — | — | 14 |
| `DepthToSpace` | ✅ | ✅ | — | 13 |
| `Div` | ✅ | — | — | 14 |
| `Einsum` | ✅ | ✅ | — | 12 |
| `Elu` | ✅ | — | — | 6 |
| `Erf` | ✅ | ✅ | — | 13 |
| `Exp` | ✅ | — | — | 13 |
| `Gather` | ❌ | ✅ | — | 13 |
| `Gelu` | ✅ | — | — | 20 |
| `GlobalAveragePool` | ✅ | ✅ | — | — |
| `GlobalMaxPool` | ✅ | ✅ | — | — |
| `GridSample` | — | ✅ | — | 16 |
| `HardSigmoid` | ✅ | — | — | 6 |
| `HardSwish` | ✅ | — | — | 14 |
| `InstanceNorm` | ✅ | ✅ | ✅ | 6 |
| `LayerNorm` | ✅ | ✅ | — | 17 |
| `LeakyRelu` | ✅ | — | — | 16 |
| `Log` | ✅ | — | — | 13 |
| `Log10` | ✅ | — | — | — |
| `Log2` | ✅ | — | — | — |
| `LRN` | ✅ | — | — | 13 |
| `MatMul` | ✅ | ✅ | — | 13 |
| `MaxPool` | ✅ | ✅ | — | 12 |
| `Mul` | ✅ | ✅ | — | 14 |
| `Pad` | ✅ | ✅ | — | 13 |
| `Pow` | ✅ | ✅ | ✅ | 15 |
| `PRelu` | ✅ | ✅ | — | 16 |
| `QuickGelu` | ✅ | ✅ | ✅ | — |
| `Reciprocal` | ✅ | — | — | 13 |
| `ReduceMax` | ✅ | ✅ | — | 13 |
| `ReduceMean` | ✅ | — | — | 13 |
| `ReduceMin` | ❌ | ❌ | — | 13 |
| `ReduceSum` | ✅ | ✅ | — | 13 |
| `Relu` | ✅ | ✅ | — | 14 |
| `Reshape` | ✅ | ✅ | ✅ | 14 |
| `Resize` | ✅ | ✅ | — | 13 |
| `RMSNorm` | ✅ | ✅ | — | 23 |
| `Rsqrt` | ✅ | — | — | — |
| `Sigmoid` | ✅ | ✅ | — | 13 |
| `Slice` | ✅ | ✅ | — | 13 |
| `Softmax` | ✅ | ✅ | — | 13 |
| `Softplus` | ✅ | — | — | 1 |
| `SpaceToDepth` | ✅ | ✅ | — | 13 |
| `Split` | ✅ | ✅ | — | 13 |
| `Sqrt` | ✅ | — | — | 13 |
| `Sub` | ✅ | ✅ | — | 14 |
| `Swish` | ✅ | ✅ | — | 24 |
| `Take` | ✅ | ✅ | — | — |
| `Tanh` | ✅ | — | — | 13 |
| `Transpose` | ✅ | ✅ | — | 13 |
| `Variance` | ✅ | ✅ | ✅ | — |

## 限制

- **加** — 具有相同形狀，或恰好只有一個輸入是純量，或兩個輸入都可以進行廣播運算。
- **ArgMax** — 將 keepdim 設為 True，並沿著通道軸進行降維。
- **平均池化層 (AveragePool)** — 膨脹率 (Dilation) = 1，向上取整模式 (ceil_mode) = False，大小 (size) 小於 128，是否包含填充 (count_include_pad) = True。如果為全域池化，則沒有大小限制。
- **BatchNorm** — 訓練模式 = 0 (SW)
- **Concat** — 不沿批次軸執行
- **Conv** — 步幅（Stride）的範圍為 [1, 31]。擴張率（Dilation）的範圍為 [1, 63]。
- **ConvTranspose** — 所有膨脹率均為 1。深度卷積或群組數為 1。步幅範圍：[1, 2, 4, 8, 16]。如果使用深度卷積，步幅必須為 1 或 2。
- **CumSum** — reverse = 0（軟體）在求和軸上，大小必須小於或等於 257。（軟體）必須恰好有一個求和軸。（軟體）軸必須是常數。（硬體）
- **Div** — 兩個輸入的形狀相同，或者恰好只有一個輸入是純量，或者兩個輸入都可以進行廣播運算。
- **Einsum** — Einsum 方程式是一種批次矩陣乘法。
- **收集**——索引必須是常數，且必須為 0D 或 1D。（硬體）
- **Gelu** — 近似值 =「無」（西南方）
- **GridSample**——模式為「線性」，且填充模式不為「反射」。
- **InstanceNorm** — 僅適用於 4 維和 5 維的張量。（SW）
- **LayerNorm** — 僅針對通道軸進行正規化
- **MaxPool** — 膨脹率（Dilation）=1，向上取整模式（ceil_mode）=False，大小小於 128。如果為全域池化，則沒有大小限制。
- **Mul** — 具有相同形狀，或恰好只有一個輸入是純量，或兩個輸入都可以進行廣播運算。
- **填充**——透過轉換為平均池化層。不支援在批次或通道維度上進行填充。僅支援「常數」模式，數值為 0。
- **Pow** — 輸入的指數為純量常數 0.5、-0.5、2 或 3。（SW）
- **PRelu** — 在通道軸上使用常數 alpha 值
- **ReduceMean** — 保持 keepdims=True，且僅針對空間維度進行降維，且維度大小小於 128。
- **ReduceMin** — 目前尚不支援。（SW）
- **ReduceSum** — 對於一維降維運算，軸僅限於空間維度。（SW）如果所有空間軸都沒有大小限制；否則，空間軸上的大小必須小於 128。（SW）
- **重新塑形** — allowzero = 0（SW）形狀不能為空。
- **調整大小**——不支援 coordinate_transformation_mode='tf_crop_and_resize'。如果方法是「線性」或「雙線性」，則 coordinate_transformation_mode 必須是「半像素」……
- **RMSNorm** — 不支援 stash_type = 10（FLOAT16）。（軟體）
- **Slice**——積極的進展。（西南地區）
- **Softmax** — 沿通道軸
- **Sub** — 具有相同形狀，或者恰好只有一個輸入是純量，或者兩個輸入都可以進行廣播運算。
- **取值**——索引必須為常數，且必須為 0D 或 1D。（SW）
- **轉置**——不涉及批次軸。
- **變異數** — 對所有空間維度進行計算
