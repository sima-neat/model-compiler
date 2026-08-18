import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pin_llima_release.py"
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
SPEC = importlib.util.spec_from_file_location("pin_llima_release", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class PinLlimaReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temp_dir.name)
        self.source = self.work_dir / "source.json"
        self.provenance = self.work_dir / "resolved.json"
        self.setUp_source_with_snap()

    def setUp_source_with_snap(self):
        self.source.write_text(
            json.dumps(
                {
                    "python-packages": [
                        {
                            "name": "sima_lmm[sdk]",
                            "vulcan": {"policy": "snap"},
                        }
                    ]
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_provenance(
        self,
        *,
        version="0.4.0",
        commit="deadbeef1234",
        requested_ref=None,
    ):
        if requested_ref is None:
            requested_ref = f"v{version}:{commit}"
        self.provenance.write_text(
            json.dumps(
                {
                    "sima_lmm": {
                        "requested-ref": requested_ref,
                        "resolved-commit": commit,
                        "version": version,
                        "wheel": f"sima_lmm-{version}-py3-none-any.whl",
                    }
                }
            ),
            encoding="utf-8",
        )

    def test_pins_commit_qualified_release_ref(self):
        self.write_provenance()
        original = self.source.read_text(encoding="utf-8")

        pinned = MODULE.pin_release(self.source, self.provenance, "0.4.0")

        self.assertEqual(pinned, "v0.4.0:deadbeef1234")
        source = json.loads(self.source.read_text(encoding="utf-8"))
        self.assertEqual(
            source["python-packages"][0]["vulcan"],
            {"ref": "v0.4.0:deadbeef1234"},
        )
        expected = original.replace(
            '{\n        "policy": "snap"\n      }',
            '{\n        "ref": "v0.4.0:deadbeef1234"\n      }',
        )
        self.assertEqual(self.source.read_text(encoding="utf-8"), expected)

    def test_rejects_mismatched_wheel_version(self):
        self.write_provenance(version="0.4.1")

        with self.assertRaisesRegex(ValueError, "does not match"):
            MODULE.pin_release(self.source, self.provenance, "0.4.0")

    def test_pins_top_level_and_architecture_overrides(self):
        source = {
            "aarch64": {
                "python-packages": [
                    {
                        "name": "sima_lmm[sdk]",
                        "vulcan": {"policy": "snap"},
                    }
                ]
            },
            "python-packages": [
                {
                    "name": "sima_lmm[sdk]",
                    "vulcan": {"policy": "snap"},
                }
            ],
        }
        self.source.write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")
        self.write_provenance()

        MODULE.pin_release(self.source, self.provenance, "0.4.0")

        updated = json.loads(self.source.read_text(encoding="utf-8"))
        expected = {"ref": "v0.4.0:deadbeef1234"}
        self.assertEqual(updated["python-packages"][0]["vulcan"], expected)
        self.assertEqual(
            updated["aarch64"]["python-packages"][0]["vulcan"],
            expected,
        )

    def test_rejects_missing_vulcan_or_mismatched_requested_ref(self):
        self.source.write_text(
            json.dumps(
                {"python-packages": [{"name": "sima_lmm[sdk]"}]},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        self.write_provenance()
        with self.assertRaisesRegex(ValueError, "requires a Vulcan object"):
            MODULE.pin_release(self.source, self.provenance, "0.4.0")

        self.setUp_source_with_snap()
        self.write_provenance(requested_ref="develop:deadbeef1234")
        with self.assertRaisesRegex(ValueError, "does not match expected"):
            MODULE.pin_release(self.source, self.provenance, "0.4.0")

    def test_rejects_duplicate_llima_entries_in_one_package_list(self):
        package = {
            "name": "sima_lmm[sdk]",
            "vulcan": {"policy": "snap"},
        }
        self.source.write_text(
            json.dumps({"python-packages": [package, package]}, indent=2) + "\n",
            encoding="utf-8",
        )
        self.write_provenance()

        with self.assertRaisesRegex(ValueError, "at most one"):
            MODULE.pin_release(self.source, self.provenance, "0.4.0")

    def test_rejects_invalid_version_or_commit(self):
        self.write_provenance(commit="not-a-commit")
        with self.assertRaisesRegex(ValueError, "commit is invalid"):
            MODULE.pin_release(self.source, self.provenance, "0.4.0")

        self.write_provenance()
        with self.assertRaisesRegex(ValueError, "must look like"):
            MODULE.pin_release(self.source, self.provenance, "release-0.4")

    def test_release_workflow_keeps_tools_outside_reused_branch(self):
        workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("ref: ${{ github.workflow_sha }}", workflow)
        self.assertIn("path: _release-tools", workflow)
        self.assertIn(
            "_release-tools/scripts/download_llima_wheel.sh", workflow
        )
        self.assertIn("_release-tools/scripts/pin_llima_release.py", workflow)


if __name__ == "__main__":
    unittest.main()
