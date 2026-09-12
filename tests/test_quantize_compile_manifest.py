import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "quantize_compile" / "scripts" / "quantize_compile.py"


def load_function(name):
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"), filename=str(SCRIPT))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == name
    )
    namespace = {}
    exec(
        compile(ast.Module(body=[function], type_ignores=[]), str(SCRIPT), "exec"),
        namespace,
    )
    return namespace[name]


def load_manifest_builder():
    return load_function("build_quantization_manifest")


def calls_to(method_name):
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"), filename=str(SCRIPT))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            isinstance(node.func, ast.Attribute) and node.func.attr == method_name
            or isinstance(node.func, ast.Name) and node.func.id == method_name
        )
    ]


class QuantizationManifestTests(unittest.TestCase):
    def test_bf16_weights_imply_bf16_activations(self):
        manifest = load_manifest_builder()(
            bf16_activations=False,
            bf16_weights=True,
        )

        self.assertEqual(manifest["activation_precision"], "bfloat16")
        self.assertEqual(manifest["weight_precision"], "bfloat16")
        self.assertEqual(manifest["device"], "modalix")

    def test_int8_configuration_remains_int8(self):
        manifest = load_manifest_builder()(
            bf16_activations=False,
            bf16_weights=False,
        )

        self.assertEqual(manifest["activation_precision"], "int8")
        self.assertEqual(manifest["weight_precision"], "int8")


class SDKDefaultTests(unittest.TestCase):
    def test_load_model_inherits_gen2_target(self):
        load_calls = calls_to("load_model")

        self.assertEqual(len(load_calls), 1)
        keyword_names = {keyword.arg for keyword in load_calls[0].keywords}
        self.assertNotIn("target", keyword_names)

    def test_quantize_inherits_mla_and_layout_defaults(self):
        quantize_calls = calls_to("quantize")

        self.assertEqual(len(quantize_calls), 1)
        keyword_names = {keyword.arg for keyword in quantize_calls[0].keywords}
        self.assertNotIn("any_shape_on_mla", keyword_names)
        self.assertNotIn("automatic_layout_conversion", keyword_names)

    def test_compile_inherits_tessellation_defaults(self):
        compile_calls = calls_to("compile")

        self.assertEqual(len(compile_calls), 1)
        keyword_names = {keyword.arg for keyword in compile_calls[0].keywords}
        self.assertNotIn("tessellate_parameters", keyword_names)

    def test_quantization_config_inherits_requantization_default(self):
        self.assertEqual(calls_to("with_requantization_mode"), [])


if __name__ == "__main__":
    unittest.main()
