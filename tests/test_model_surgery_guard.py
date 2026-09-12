import argparse
import importlib.util
import json
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD_PATH = REPO_ROOT / "skills" / "model_surgery" / "scripts" / "model_surgery_guard.py"
SUPPORT_DB_PATH = (
    REPO_ROOT / "skills" / "model_surgery" / "data" / "supported_operators.json"
)


def _load_guard_module():
    spec = importlib.util.spec_from_file_location("model_surgery_guard", GUARD_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load_guard_module()


def _support_db():
    return {
        "release": "test",
        "operators": {
            "BatchNormalization": {"int8": None, "bfloat16": None},
            "InstanceNormalization": {"int8": "Y", "bfloat16": "Y"},
            "LayerNormalization": {"int8": "Y", "bfloat16": "Y"},
        },
    }


def test_audit_recognizes_standard_onnx_normalization_names():
    report = guard._build_audit_report(
        _support_db(),
        Counter(
            {
                "BatchNormalization": 1,
                "InstanceNormalization": 2,
                "LayerNormalization": 3,
            }
        ),
        "int8",
    )

    assert report["unknown_count"] == 0
    assert [item["operator"] for item in report["unsupported"]] == ["BatchNormalization"]
    assert [item["operator"] for item in report["supported"]] == [
        "InstanceNormalization",
        "LayerNormalization",
    ]


def test_real_onnx_model_uses_canonical_normalization_names(tmp_path):
    import onnx
    from onnx import TensorProto, helper

    model_path = tmp_path / "normalization.onnx"
    graph = helper.make_graph(
        [
            helper.make_node(
                "BatchNormalization",
                ["x", "bn_scale", "bn_bias", "bn_mean", "bn_variance"],
                ["batch_normalized"],
            ),
            helper.make_node(
                "InstanceNormalization",
                ["x", "instance_scale", "instance_bias"],
                ["instance_normalized"],
            ),
            helper.make_node(
                "LayerNormalization",
                ["x", "layer_scale", "layer_bias"],
                ["layer_normalized"],
                axis=-1,
            ),
        ],
        "canonical_normalization_names",
        [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 2, 2, 2])],
        [
            helper.make_tensor_value_info(
                "batch_normalized", TensorProto.FLOAT, [1, 2, 2, 2]
            ),
            helper.make_tensor_value_info(
                "instance_normalized", TensorProto.FLOAT, [1, 2, 2, 2]
            ),
            helper.make_tensor_value_info(
                "layer_normalized", TensorProto.FLOAT, [1, 2, 2, 2]
            ),
        ],
        initializer=[
            helper.make_tensor("bn_scale", TensorProto.FLOAT, [2], [1.0, 1.0]),
            helper.make_tensor("bn_bias", TensorProto.FLOAT, [2], [0.0, 0.0]),
            helper.make_tensor("bn_mean", TensorProto.FLOAT, [2], [0.0, 0.0]),
            helper.make_tensor("bn_variance", TensorProto.FLOAT, [2], [1.0, 1.0]),
            helper.make_tensor("instance_scale", TensorProto.FLOAT, [2], [1.0, 1.0]),
            helper.make_tensor("instance_bias", TensorProto.FLOAT, [2], [0.0, 0.0]),
            helper.make_tensor("layer_scale", TensorProto.FLOAT, [2], [1.0, 1.0]),
            helper.make_tensor("layer_bias", TensorProto.FLOAT, [2], [0.0, 0.0]),
        ],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    onnx.checker.check_model(model)
    onnx.save(model, model_path)

    report = guard._build_audit_report(
        _support_db(), guard._load_model_ops(model_path), "int8"
    )

    assert report["unknown_count"] == 0
    assert report["supported_count"] == 2
    assert report["unsupported_count"] == 1


def test_query_accepts_onnx_name(tmp_path, capsys):
    support_path = tmp_path / "support.json"
    support_path.write_text(json.dumps(_support_db()), encoding="utf-8")
    args = argparse.Namespace(
        supported_ops_json=str(support_path),
        op="LayerNormalization",
    )

    assert guard.cmd_query_op(args) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["operator"] == "LayerNormalization"


def test_list_supported_uses_standard_onnx_names(tmp_path, capsys):
    support_path = tmp_path / "support.json"
    support_path.write_text(json.dumps(_support_db()), encoding="utf-8")
    args = argparse.Namespace(supported_ops_json=str(support_path), dtype="int8")

    assert guard.cmd_list_supported(args) == 0
    assert capsys.readouterr().out.splitlines() == [
        "InstanceNormalization",
        "LayerNormalization",
    ]


def test_real_support_db_describes_new_onnx_operator_precision_constraints():
    support_db = guard._load_support_db(SUPPORT_DB_PATH)
    operators = support_db["operators"]

    assert operators["Sin"]["int8"] == "Y"
    assert operators["Sin"]["bfloat16"] == "N"
    assert "INT8 lookup-table UDF" in operators["Sin"]["sima_hw_sw_constraints"]

    assert operators["Cos"]["int8"] == "Y"
    assert operators["Cos"]["bfloat16"] == "N"
    assert "INT8 lookup-table UDF" in operators["Cos"]["sima_hw_sw_constraints"]

    assert operators["Gemm"]["int8"] == "Y"
    assert operators["Gemm"]["bfloat16"] == "Y"
    assert "compile-time constant initializer" in operators["Gemm"]["sima_hw_sw_constraints"]

    assert operators["MeanVarianceNormalization"]["int8"] == "Y"
    assert operators["MeanVarianceNormalization"]["bfloat16"] == "N"
    assert "Rank-5" in operators["MeanVarianceNormalization"]["sima_hw_sw_constraints"]


def test_real_onnx_model_audits_new_operator_names_by_activation_precision(tmp_path):
    import onnx
    from onnx import TensorProto, helper

    model_path = tmp_path / "new_supported_operators.onnx"
    graph = helper.make_graph(
        [
            helper.make_node("Sin", ["x"], ["sin_out"]),
            helper.make_node("Cos", ["x"], ["cos_out"]),
            helper.make_node(
                "MeanVarianceNormalization",
                ["x"],
                ["mvn_out"],
                axes=[0, 2, 3],
            ),
            helper.make_node("Gemm", ["a", "b"], ["gemm_out"]),
        ],
        "new_supported_operators",
        [
            helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 2, 2, 2]),
            helper.make_tensor_value_info("a", TensorProto.FLOAT, [1, 4]),
        ],
        [
            helper.make_tensor_value_info("sin_out", TensorProto.FLOAT, [1, 2, 2, 2]),
            helper.make_tensor_value_info("cos_out", TensorProto.FLOAT, [1, 2, 2, 2]),
            helper.make_tensor_value_info("mvn_out", TensorProto.FLOAT, [1, 2, 2, 2]),
            helper.make_tensor_value_info("gemm_out", TensorProto.FLOAT, [1, 3]),
        ],
        initializer=[
            helper.make_tensor(
                "b",
                TensorProto.FLOAT,
                [4, 3],
                [0.1] * 12,
            )
        ],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    onnx.checker.check_model(model)
    onnx.save(model, model_path)

    support_db = guard._load_support_db(SUPPORT_DB_PATH)
    op_counts = guard._load_model_ops(model_path)
    int8_report = guard._build_audit_report(support_db, op_counts, "int8")
    bfloat16_report = guard._build_audit_report(support_db, op_counts, "bfloat16")

    assert int8_report["unknown_count"] == 0
    assert int8_report["unsupported_count"] == 0
    assert [item["operator"] for item in bfloat16_report["supported"]] == ["Gemm"]
    assert [item["operator"] for item in bfloat16_report["unsupported"]] == [
        "Cos",
        "MeanVarianceNormalization",
        "Sin",
    ]
