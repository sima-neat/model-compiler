import importlib.util
import json
from pathlib import Path

import onnx


REPO_ROOT = Path(__file__).resolve().parents[1]
SUPPORT_DB_PATH = (
    REPO_ROOT / "skills" / "model_surgery" / "data" / "supported_operators.json"
)
GENERATOR_PATH = REPO_ROOT / "scripts" / "build_supported_operators_md.py"
LEGACY_DATA_PATHS = (
    REPO_ROOT / "scripts" / "data" / "onnx_operators.json",
    REPO_ROOT / "scripts" / "data" / "constraint_copy.json",
)


def _load_generator_module():
    spec = importlib.util.spec_from_file_location(
        "build_supported_operators_md", GENERATOR_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _support_db():
    return json.loads(SUPPORT_DB_PATH.read_text(encoding="utf-8"))


def test_support_database_is_the_only_operator_documentation_source():
    assert all(not path.exists() for path in LEGACY_DATA_PATHS)

    generator_source = GENERATOR_PATH.read_text(encoding="utf-8")
    assert "supported_operators.json" in generator_source
    assert "onnx_operators.json" not in generator_source
    assert "constraint_copy.json" not in generator_source


def test_support_database_schema_is_complete_and_uses_canonical_onnx_names():
    support_db = _support_db()
    assert support_db["schema_version"] == 4

    canonical_onnx_names = {
        schema.name
        for schema in onnx.defs.get_all_schemas_with_history()
        if schema.domain in {"", "ai.onnx"}
    }
    legacy_or_internal_names = {
        "BatchNorm",
        "BroadcastTo",
        "InstanceNorm",
        "LayerNorm",
        "Log10",
        "Log2",
        "QuickGelu",
        "RMSNorm",
        "Rsqrt",
        "Take",
        "Variance",
    }

    required_fields = {
        "onnx-opset-version",
        "attributes",
        "element_wise",
        "tvm_transforms_constraints",
        "spatial_dimensions",
        "fived",
        "sima_hw_sw_constraints",
        "customer_constraints",
        "business_study",
        "int8",
        "bfloat16",
        "notes",
    }

    operators = support_db["operators"]
    assert set(operators) <= canonical_onnx_names
    assert not set(operators) & legacy_or_internal_names

    for name, entry in operators.items():
        assert set(entry) == required_fields, name
        assert entry["int8"] in {"Y", "N", None}, name
        assert entry["bfloat16"] in {"Y", "N", None}, name
        assert entry["fived"] in {"Y", "N", None}, name
        assert bool(entry["sima_hw_sw_constraints"]) == bool(
            entry["customer_constraints"]
        ), name


def test_documentation_generator_publishes_every_database_entry(tmp_path, monkeypatch):
    generator = _load_generator_module()
    output_path = tmp_path / "model-compatibility.md"
    monkeypatch.setattr(generator, "OUT", output_path)

    assert generator.main() == 0

    generated = output_path.read_text(encoding="utf-8")
    payload = generated.split("<OperatorTable>\n", 1)[1].split(
        "\n</OperatorTable>", 1
    )[0]
    rows = json.loads(payload)
    database_names = sorted(_support_db()["operators"], key=str.lower)

    assert [row["name"] for row in rows] == database_names
    assert len(rows) == len(database_names)
