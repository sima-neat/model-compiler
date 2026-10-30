import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_container_release.py"
SPEC = importlib.util.spec_from_file_location("generate_container_release", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class GenerateContainerReleaseTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "sdk_version": "2.1.3",
            "python_version": "3.12.3",
            "dependency_overrides": {
                "sima-frontend": "2.1.3.dev0+master.1",
                "ml-dtypes": "0.4.0",
            },
            "aarch64": {"dependency_overrides": {"ml-dtypes": "0.4.1"}},
            "python-packages": [
                {"name": "sima_lmm[sdk]", "vulcan": {"policy": "snap"}}
            ],
            "binary-packages": [
                {"name": "mla/toolchain/mla-toolchain", "version": "v2.1.3560"}
            ],
        }

    def test_release_includes_sdk_build_and_component_versions(self):
        text = MODULE.render_release(
            self.source,
            model_compiler_version="container-image:deadbee",
            git_branch="container-image",
            git_commit="deadbee",
            build_time="2026-08-26T12:34:56Z",
            target_arch="arm64",
            installed_versions={
                "sima-frontend": "2.1.3.dev0+master.1",
                "ml-dtypes": "0.4.1",
                "sima-lmm": "2.1.3.dev0+develop.42",
            },
        )

        self.assertIn("SDK Version = 2.1.3", text)
        self.assertIn("Python Version = 3.12.3", text)
        self.assertIn("Target Architecture = aarch64", text)
        self.assertIn("Build Time (UTC) = 2026-08-26T12:34:56Z", text)
        self.assertIn("  ml-dtypes = 0.4.1", text)
        self.assertIn("  sima-lmm = 2.1.3.dev0+develop.42", text)
        self.assertIn("  mla/toolchain/mla-toolchain = v2.1.3560", text)

    def test_x86_uses_top_level_component_override(self):
        versions = MODULE.component_versions(
            self.source,
            "amd64",
            installed_versions={},
        )

        self.assertEqual(versions["ml-dtypes"], "0.4.0")
        self.assertEqual(versions["sima-lmm"], "snap")


if __name__ == "__main__":
    unittest.main()
