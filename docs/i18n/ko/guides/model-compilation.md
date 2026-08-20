---
title: "컴파일"
sidebar_position: 5
---

# 컴파일

`Model.compile`을 사용하여 **양자화된** 모델을 SiMa MLSoC에서 실행할 수 있는 이진 형식으로 변환합니다.

```python
from afe.apis.model import Model

# Load a previously quantized model
quant_model = Model.load("<quant_model_name>", "<path to quantized model file>")
```

## 기본 옵션으로 컴파일합니다.

출력 폴더를 지정하세요.

```python
quant_model.compile(output_path="<output_folder_path>")
```

출력 결과는 양자화된 모델 파일의 이름을 딴 `.tar.gz` 형식의 아카이브 파일입니다. 여기에는 다음이 포함됩니다.

| 목차 | 목적 |
| --- | --- |
| `.elf` 파일 | MLA에서 실행됨 |
| `.so` 파일 | 코텍스-A65에서 실행(필요한 경우에만). |
| `.yaml` 파일 | 실행 통계 프로파일링 |
| `_mpk.json` | 프로세서 플러그인 구성 / 파이프라인 메타데이터 |

## 테셀레이션

**테셀레이션**은 입력 및 출력 텐서가 MLA를 위해 DRAM에 어떻게 배치되는지를 제어합니다. 입력 텐서를 `HWC` 레이아웃으로, 출력 텐서를 `HWC16` 레이아웃으로 하여 텐서를 MLA로 **직접 전송하고 MLA에서 직접 수신**하면 EV74 데이터 재정렬 장치를 거치지 않아 지연 시간을 줄일 수 있습니다. 이는 가속기를 직접 사용하는 모델에 대해 **권장되는 기본 설정**입니다. [첫 번째 모델 예제](./compile-your-first-model.md)는 기본적으로 이 설정을 활성화합니다.

컴파일할 때 텐서별로 테셀레이션 매개변수를 전달합니다.

```python
from afe.apis.defines import TensorTessellateParameters, TensorDRAMLayout

input_tess  = TensorTessellateParameters(tile_shape=(0, 0, 0, 0), enable_mla=True,
                                          dram_layout=TensorDRAMLayout.HWC)
output_tess = TensorTessellateParameters(tile_shape=(0, 0, 0, 0), enable_mla=True,
                                          dram_layout=TensorDRAMLayout.HWC16)

tess_params = {}
mla_node = quant_model._net.nodes["MLA_0"]
for name in mla_node.input_names:
    tess_params[name] = input_tess
# (resolve MLA output names and map them to output_tess — see the example script)

quant_model.compile(output_path="<output_folder_path>", tessellate_parameters=tess_params)
```

`sima-cli neat install model-compiler/examples`를 사용하여 설치된 첫 번째 모델 예제는 이 설정을 자동으로 구성합니다.
EV74 재정렬 경로가 파이프라인에 필요한 경우에만 테셀레이션 설정을 변경하지 않은 상태(`tessellate_parameters=None`)로 두십시오.

## 배치 크기가 1보다 큰 경우 컴파일합니다.

**원하는** 배치 크기를 설정하세요.

```python
quant_model.compile(output_path="<output_folder_path>", batch_size=16)
```

:::note
컴파일러는 요청된 값까지 가능한 한 가장 큰 배치 크기를 사용합니다. 정확히 요청된 크기를 보장하지는 않습니다. 실제로 사용된 값을 확인하려면 `_mpk.json`에서 `desired_batch_size`와 `actual_batch_size`를 검색하십시오.

```json
"name": "MLA_0",
"processor": "MLA",
"config_params": {
    "desired_batch_size": 16,
    "actual_batch_size": 12,
    "number_of_quads_to_user": 4
}
```
:::

## 아카이브를 검사합니다.

컴파일러는 아카이브의 내용을 출력하지 않습니다. 다음 명령어를 사용하여 내용을 나열하십시오.

```python
import tarfile

with tarfile.open("<name_of_archive.tar.gz>") as f:
    for filename in f.getnames():
        print(filename)
```

## 계층별 실행 시간 통계

각 컴파일된 아카이브에는 컴파일러가 추정한 MLA 레이어당 사이클 수가 포함된 `*_mla_stats.yaml` 파일이 있습니다.

```yaml
4:
  name: MLA_0/conv2d_add_relu_3
  start_cycle: 63615
  end_cycle: 71558
5:
  name: MLA_0/conv2d_add_relu_4
  start_cycle: 71559
  end_cycle: 79502
```

이 값들은 고정된 스케줄에 따른 시작 및 종료 주기입니다. 명령어 또는 메모리 접근으로 인한 지연 시간은 포함되지 않습니다. 메모리 주기 등 전체 실행 시간 통계를 확인하려면, Palette/Neat 가속 모드에서 `.elf` 모델을 하드웨어에서 실행하십시오.
