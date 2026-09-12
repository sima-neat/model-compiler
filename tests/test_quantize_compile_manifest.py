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


def argument_choices(option_name):
    call = next(
        call
        for call in calls_to("add_argument")
        if call.args
        and isinstance(call.args[0], ast.Constant)
        and call.args[0].value == option_name
    )
    choices = next(
        keyword.value for keyword in call.keywords if keyword.arg == "choices"
    )
    return ast.literal_eval(choices)


def argument_names():
    return [
        call.args[0].value
        for call in calls_to("add_argument")
        if call.args and isinstance(call.args[0], ast.Constant)
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
    def test_reference_cli_exposes_supported_model_formats(self):
        self.assertEqual(argument_choices("--model_format"), ["onnx", "pytorch"])

    def test_load_model_inherits_gen2_target(self):
        load_calls = calls_to("load_model")

        self.assertEqual(len(load_calls), 1)
        keyword_names = {keyword.arg for keyword in load_calls[0].keywords}
        self.assertNotIn("target", keyword_names)

    def test_reference_cli_uses_source_helpers(self):
        self.assertEqual(len(calls_to("onnx_source")), 1)
        self.assertEqual(len(calls_to("pytorch_source")), 1)
        self.assertEqual(calls_to("ImporterParams"), [])

    def test_onnx_source_infers_types_and_outputs(self):
        onnx_calls = calls_to("onnx_source")

        self.assertEqual(len(onnx_calls), 1)
        keyword_names = {keyword.arg for keyword in onnx_calls[0].keywords}
        self.assertNotIn("dtype_dict", keyword_names)
        self.assertNotIn("output_names", keyword_names)

    def test_output_names_are_not_a_cli_option(self):
        self.assertNotIn("--output_names", argument_names())

    def test_verification_inherits_execution_backend(self):
        self.assertNotIn("--executor", argument_names())
        for execute_call in calls_to("execute"):
            keyword_names = {keyword.arg for keyword in execute_call.keywords}
            self.assertNotIn("use_jax", keyword_names)

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
