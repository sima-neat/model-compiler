---
title: "Компіляція"
sidebar_position: 5
---

# Компіляція

Використовуйте `Model.compile`, щоб перетворити **квантовану** модель у двійковий формат, який працюватиме на SiMa MLSoC.

```python
from afe.apis.model import Model

# Load a previously quantized model
quant_model = Model.load("<quant_model_name>", "<path to quantized model file>")
```

## Зберіть, використовуючи параметри за замовчуванням.

Вкажіть папку для збереження результату:

```python
quant_model.compile(output_path="<output_folder_path>")
```

Результатом є архів `.tar.gz`, названий на честь файлу квантованої моделі. Він містить:

| Зміст | Мета. |
| --- | --- |
| файли `.elf` | Виконано відповідно до вимог MLA. |
| файли `.so` | Виконується на процесорі Cortex-A65 (лише за потреби). |
| файл `.yaml` | Аналіз статистики виконання. |
| `_mpk.json` | Конфігурація процесорного плагіна / метадані конвеєра. |

## Теселяція {#tessellation}

**Теселяція** визначає, як вхідні та вихідні тензори розміщуються в DRAM для
блоку множення та акумулювання (MLA). Передача тензорів **безпосередньо до та з MLA**, зі вхідними даними у форматі `HWC`
та вихідними даними у форматі `HWC16`, дозволяє обійти блок переупорядкування даних EV74 і зменшити
затримку. Це **рекомендоване значення за замовчуванням** для моделей, які безпосередньо передають дані
в прискорювач. [first-model example](./compile-your-first-model.md)
вмикає цю функцію за замовчуванням.

Під час компіляції передавайте параметри теселяції для кожного тензора:

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

Перший приклад моделі, встановлений за допомогою
`sima-cli neat install model-compiler/examples`, автоматично налаштовує всі необхідні параметри.
Залиште параметр теселяції без змін (`tessellate_parameters=None`) лише тоді, коли для вашого конвеєра потрібне переупорядкування шляху EV74.

## Здійснення компіляції для пакетів даних розміром більше 1.

Встановіть **бажаний** розмір пакету:

```python
quant_model.compile(output_path="<output_folder_path>", batch_size=16)
```

:::note
Компілятор реалізує найбільший можливий розмір пакета, але не більше зазначеного значення. Він не гарантує точне відповідність заданому розміру. Щоб дізнатися, який розмір було фактично реалізовано, перегляньте файл `_mpk.json` і знайдіть значення `desired_batch_size` та `actual_batch_size`.

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

## Перевірка архіву.

Компілятор не виводить вміст архіву. Щоб переглянути його, скористайтеся:

```python
import tarfile

with tarfile.open("<name_of_archive.tar.gz>") as f:
    for filename in f.getnames():
        print(filename)
```

## Статистичні дані про час виконання для кожного шару.

Кожен створений архів містить файл `*_mla_stats.yaml` з оціночною кількістю циклів, необхідних компілятору для кожного шару MLA:

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

Ці значення представляють собою фіксовані цикли початку та завершення. Вони **не** включають
цикли очікування, пов’язані з отриманням інструкцій або даних з пам’яті. Для отримання повної статистики під час виконання, включно з циклами пам’яті, запустіть модель `.elf` на апаратному забезпеченні в режимі прискорення Palette/Neat.
