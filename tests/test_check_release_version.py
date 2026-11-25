import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_release_version.py"
SPEC = importlib.util.spec_from_file_location("check_release_version", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class CheckReleaseVersionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.source = Path(self.temp_dir.name) / "source.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_source(self, sdk_version):
        self.source.write_text(
            json.dumps({"sdk_version": sdk_version}), encoding="utf-8"
        )

    def test_accepts_tags_that_start_with_sdk_version(self):
        self.write_source("3.0.1")

        for tag in ("v3.0.1.0", "3.0.1.0", "v3.0.1", "3.0.1.12", "v3.0.1.0-rc1"):
            with self.subTest(tag=tag):
                self.assertEqual(
                    MODULE.check_release_version(self.source, tag), "3.0.1"
                )

    def test_rejects_tag_for_another_sdk_version(self):
        self.write_source("3.0.0")

        with self.assertRaisesRegex(ValueError, "bump sdk_version"):
            MODULE.check_release_version(self.source, "v3.0.1.0")

    def test_rejects_malformed_tag_or_sdk_version(self):
        self.write_source("3.0.1")
        for tag in ("v3.0", "v3.0.1.0.1", "release-3.0.1"):
            with self.subTest(tag=tag):
                with self.assertRaisesRegex(ValueError, "must look like"):
                    MODULE.check_release_version(self.source, tag)

        for sdk_version in ("", "3.0", "3.0.1.0"):
            with self.subTest(sdk_version=sdk_version):
                self.write_source(sdk_version)
                with self.assertRaisesRegex(ValueError, "sdk_version"):
                    MODULE.check_release_version(self.source, "v3.0.1.0")

    def test_release_and_tag_builds_check_sdk_version(self):
        workflows = ROOT / ".github" / "workflows"
        release = (workflows / "release.yml").read_text(encoding="utf-8")
        build = (workflows / "build.yml").read_text(encoding="utf-8")

        self.assertIn("_release-tools/scripts/check_release_version.py", release)
        self.assertIn("scripts/check_release_version.py", build)
        # release-* is PR-protected: tag only once the pin needs no new commit.
        self.assertIn("needs.prepare-release.outputs.ready == 'true'", release)

    def test_current_manifest_has_valid_sdk_version(self):
        source = json.loads(
            (ROOT / "scripts" / "source.json").read_text(encoding="utf-8")
        )
        self.assertRegex(source["sdk_version"], MODULE.SDK_VERSION_RE)


if __name__ == "__main__":
    unittest.main()
