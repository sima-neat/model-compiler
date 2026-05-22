<a id="afe-apis-statistic"></a>
# `afe.apis.statistic`

Source: `afe/apis/statistic.py`

[Back to index](index.md)

Analysis of statistics on tensors.

Imports:
- [`afe.apis.compilation_job_base.Tensor`](afe-apis-compilation_job_base.md#afe-apis-compilation-job-base-tensor)
- `afe.core.evaluate_networks.checked_zip`
- `afe.driver.statistic.Statistic`
- `dataclasses`
- `numpy as np`
- `typing.Any`
- `typing.Callable`
- `typing.Generic`
- `typing.List`
- `typing.Tuple`
- `typing.Type`
- `typing.TypeVar`

Constants:
- <a id="afe-apis-statistic-metric"></a>`Metric` (line 28) [default/value `Callable[[Tensor, Tensor], float]`]

Functions:
- <a id="afe-apis-statistic-equality"></a>`equality(x: Tensor, y: Tensor) -> float` (line 31): Equality as a distance metric.
    Parameters:
    - `x`: type `Tensor`
    - `y`: type `Tensor`
    Returns: float
- <a id="afe-apis-statistic-mean-float"></a>`mean_float(x: Tensor, y: Tensor) -> float` (line 40): Mean value of difference between input values and ground truth values.
    Parameters:
    - `x`: type `Tensor`
    - `y`: type `Tensor`
    Returns: float
- <a id="afe-apis-statistic-threshold-test-counter"></a>`threshold_test_counter(metric: Metric, threshold: float) -> Statistic[Tuple[Tensor, Tensor], str]` (line 58): Create a Statistic over a stream of (x, y) pairs that counts the number of times metric(x, y) < threshold is satisfied.
    Parameters:
    - `metric`: Distance metric
    - `threshold`: Threshold to compare against
    Returns: Statistic that captures the data
- <a id="afe-apis-statistic-tensor-set-statistics"></a>`tensor_set_statistics(statistics: List[Statistic[Tuple[Any, Any], str]]) -> Statistic[Tuple[List[Any], List[Any]], str]` (line 82): Apply an independent Statistic to each tensor in a stream of pairs of fixed-length lists.
    Parameters:
    - `statistics`: Statistic to apply to each pair of values
    Returns: Composed statistic that applies the statistics to list items
- <a id="afe-apis-statistic-mean"></a>`mean(metric: Metric) -> Statistic[Tuple[List[Tensor], Tensor], float]` (line 114): Create a statistic that takes input pairs (i, g) and computes the arithmetic mean of metric(i, g) over all given inputs.
    Parameters:
    - `metric`: Mean metric.
    Returns: Statistic that captures the data
- <a id="afe-apis-statistic-mean-text"></a>`mean_text(metric: Metric) -> Statistic[Tuple[List[Tensor], Tensor], str]` (line 136): Create a statistic that takes input pairs (i, g) and computes the arithmetic mean of metric(i, g) over all given inputs and formats the results as text message.
    Parameters:
    - `metric`: Mean metric.
    Returns: Statistic that captures the data
