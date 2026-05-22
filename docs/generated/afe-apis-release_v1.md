<a id="afe-apis-release-v1"></a>
# `afe.apis.release_v1`

Source: `afe/apis/release_v1.py`

[Back to index](index.md)

This is the development API for AFE.  It supports importing models, loading and storing AFE's internal format, quantizing, executing, and simulating.

Imports:
- [`afe.apis.defines.gen1_target`](afe-apis-defines.md#afe-apis-defines-gen1-target)
- [`afe.apis.transform.Transform`](afe-apis-transform.md#afe-apis-transform-transform)
- `afe.core.utils.convert_data_generator_to_iterable`
- `afe.core.utils.length_hinted`
- `afe.ir.defines.InputName`
- `afe.ir.defines.NodeName`
- `afe.ir.defines.Status`
- `afe.ir.defines.TupleValue`
- `afe.ir.defines.data_value_elements`
- `afe.ir.defines.get_expected_tensor_value`
- `afe.ir.net.AwesomeNet`
- `afe.ir.net.Renaming`
- `afe.ir.net.inline_awesomenet_subgraphs`
- `afe.ir.net.rename_awesomenet_nodes`
- `afe.ir.node.AwesomeNode`
- `afe.ir.node.node_is_tuple`
- `afe.ir.tensor_type.TensorType`
- `copy`
- `ev_transforms.transforms.resize`
- `sima_utils.common.Platform`
- `sima_utils.data.data_generator.DataGenerator`
- `sima_utils.data.data_generator.get_dummy_data_generator`
- `typing.Dict`
- `typing.List`
- `typing.Optional`
- `typing.Tuple`

Functions:
- <a id="afe-apis-release-v1-create-auxiliary-processing-network"></a>`create_auxiliary_processing_network(transforms: List[Transform], input_types: Dict[InputName, TensorType], *, input_node_names: Optional[List[NodeName]] = None, net_name: str = 'aux_net', status: Status = Status.RELAY, target: Platform = gen1_target) -> AwesomeNet` (line 94): Creates an AwesomeNet from the list of Transforms.
    Parameters:
    - `transforms`: The list of Transforms. Each transform in the list correspond to one input.
    - `input_types`: The list of input types. Each input correspond to one Transform.
    - `input_node_names`: If set, determines the input names of the resulting AwesomeNet.
    - `net_name`: The name of the resulting AwesomeNet. Default it "aux_net".
    - `status`: The status of the created AwesomeNet. Default is Status.RELAY.
    - `target`: A target platform that a model is compiled for.
    Returns: AwesomeNet containing nodes corresponding to the transforms list.
- <a id="afe-apis-release-v1-compose-awesomenets"></a>`compose_awesomenets(nets: List[AwesomeNet], status: Status = Status.RELAY, combined_model_name: str = 'main') -> AwesomeNet` (line 142): Creates an AwesomeNet form the list of AwesomeNets. Each AwesomeNet in the list of input AwesomeNets becomes the subnet of the resulting AwesomeNet.
    Parameters:
    - `nets`: List[AwesomeNet]. The list of input AwesomeNet which are to be composed into a single AwesomeNet.
    - `status`: Parameter setting the status of composed network. Default value is Status.RELAY
    - `combined_model_name`: Combined model name.
    Returns: The AwesomeNet consisting of the input AwesomeNets.
- <a id="afe-apis-release-v1-get-model-sdk-version"></a>`get_model_sdk_version() -> str` (line 211)
    Returns: str
