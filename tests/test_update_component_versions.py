import importlib.util
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "update_component_versions.py"
SPEC = importlib.util.spec_from_file_location("update_component_versions", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ComponentVersionUpdateTests(unittest.TestCase):
    def report(self, arch, components):
        return {"target_arch": arch, "components": components}

    def test_python_family_preserves_base_and_channel(self):
        family = MODULE.python_family("2.1.3.dev0+master.390")
        self.assertIsNotNone(family)
        self.assertEqual(family.parse_candidate("2.1.3.dev0+master.391"), 391)
        self.assertIsNone(family.parse_candidate("2.1.3.dev0+develop.999"))
        self.assertIsNone(family.parse_candidate("2.1.4.dev0+master.999"))

    def test_binary_family_preserves_base_and_channel(self):
        family = MODULE.binary_family("v2.1.3560-develop.409")
        self.assertIsNotNone(family)
        self.assertEqual(family.parse_candidate("v2.1.3560-develop.410"), 410)
        self.assertIsNone(family.parse_candidate("v2.1.3560-master.999"))
        self.assertIsNone(family.parse_candidate("v2.1.3561-develop.999"))

    def test_python_index_filters_to_current_family_and_orders_numerically(self):
        page = """
        <a href="sima_frontend-2.1.3.dev0%2Bmaster.9-py3-none-any.whl">old</a>
        <a href="sima_frontend-2.1.3.dev0%2Bmaster.391-py3-none-any.whl">new</a>
        <a href="sima_frontend-2.1.3.dev0%2Bmaster.400-py3-none-any.whl">newer</a>
        <a href="sima_frontend-2.1.3.dev0%2Bdevelop.999-py3-none-any.whl">wrong channel</a>
        <a href="sima_frontend-2.1.4.dev0%2Bmaster.999-py3-none-any.whl">wrong base</a>
        """
        with patch.object(MODULE, "curl_text", return_value=page):
            versions = MODULE.python_index_versions(
                "sima-frontend",
                "2.1.3.dev0+master.390",
                "https://example.invalid/simple",
            )
        self.assertEqual(
            versions,
            ["2.1.3.dev0+master.400", "2.1.3.dev0+master.391"],
        )

    def test_mla_index_requires_architecture_specific_archive(self):
        component = MODULE.Component(
            component_id=(
                "binary:mla/toolchain/mla-toolchain:"
                "v2.1.3560-develop.409"
            ),
            kind="binary",
            name="mla/toolchain/mla-toolchain",
            current="v2.1.3560-develop.409",
        )
        listing = json.dumps(
            {
                "files": [
                    {
                        "uri": (
                            "/mla-toolchain-v2.1.3560-develop.410-"
                            "x86-ubuntu.zip"
                        )
                    },
                    {
                        "uri": (
                            "/mla-toolchain-v2.1.3560-develop.411-"
                            "aarch64-ubuntu.zip"
                        )
                    },
                    {
                        "uri": (
                            "/mla-toolchain-v2.1.3560-master.999-"
                            "x86-ubuntu.zip"
                        )
                    },
                ]
            }
        )
        with patch.object(MODULE, "curl_text", return_value=listing):
            versions = MODULE.binary_index_versions(
                component,
                target_arch="x86_64",
                artifactory_url="https://example.invalid/artifactory",
            )
        self.assertEqual(versions, ["v2.1.3560-develop.410"])

    def test_selects_highest_version_available_on_both_architectures(self):
        source = {
            "dependency_overrides": {
                "sima-frontend": "2.1.3.dev0+master.390",
            }
        }
        component_id = "python:sima-frontend:2.1.3.dev0+master.390"
        reports = [
            self.report(
                "x86_64",
                {
                    component_id: {
                        "available": [
                            "2.1.3.dev0+master.395",
                            "2.1.3.dev0+master.393",
                        ]
                    }
                },
            ),
            self.report(
                "aarch64",
                {
                    component_id: {
                        "available": [
                            "2.1.3.dev0+master.394",
                            "2.1.3.dev0+master.393",
                        ]
                    }
                },
            ),
        ]
        self.assertEqual(
            MODULE.select_updates(source, reports),
            {component_id: "2.1.3.dev0+master.393"},
        )

    def test_no_common_architecture_version_produces_no_update(self):
        source = {
            "binary-packages": [
                {
                    "name": "mla/toolchain/mla-toolchain",
                    "version": "v2.1.3560-develop.409",
                }
            ]
        }
        component_id = (
            "binary:mla/toolchain/mla-toolchain:v2.1.3560-develop.409"
        )
        reports = [
            self.report(
                "x86_64",
                {component_id: {"available": ["v2.1.3560-develop.411"]}},
            ),
            self.report(
                "aarch64",
                {component_id: {"available": ["v2.1.3560-develop.410"]}},
            ),
        ]
        self.assertEqual(MODULE.select_updates(source, reports), {})

    def test_architecture_specific_component_requires_only_that_report(self):
        source = {
            "python-packages": [],
            "aarch64": {
                "python-packages": [
                    {
                        "name": "sima-arm-helper",
                        "version": "2.1.3.dev0+develop.7",
                    }
                ]
            },
        }
        component_id = "python:sima-arm-helper:2.1.3.dev0+develop.7"
        reports = [
            self.report("x86_64", {}),
            self.report(
                "aarch64",
                {
                    component_id: {
                        "available": ["2.1.3.dev0+develop.8"]
                    }
                },
            ),
        ]
        self.assertEqual(
            MODULE.select_updates(source, reports),
            {component_id: "2.1.3.dev0+develop.8"},
        )

    def test_merge_updates_duplicate_pins_without_reformatting(self):
        source_text = """{
  "dependency_overrides": {
    "sima-frontend": "2.1.3.dev0+master.390"
  },
  "python-packages": [
    { "name": "sima-frontend", "version": "2.1.3.dev0+master.390" }
  ]
}
"""
        component_id = "python:sima-frontend:2.1.3.dev0+master.390"
        component = {
            component_id: {
                "kind": "python",
                "name": "sima-frontend",
                "current": "2.1.3.dev0+master.390",
                "available": ["2.1.3.dev0+master.391"],
            }
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.json"
            output = root / "updated.json"
            summary = root / "summary.md"
            source.write_text(source_text, encoding="utf-8")
            reports = []
            source_sha256 = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
            for arch in MODULE.SUPPORTED_ARCHES:
                report = root / f"{arch}.json"
                report.write_text(
                    json.dumps(
                        {
                            **self.report(arch, component),
                            "source_sha256": source_sha256,
                        }
                    ),
                    encoding="utf-8",
                )
                reports.append(report)

            changed = MODULE.merge(
                source, reports, output=output, summary=summary
            )

            self.assertTrue(changed)
            updated = output.read_text(encoding="utf-8")
            self.assertIn(
                '{ "name": "sima-frontend", '
                '"version": "2.1.3.dev0+master.391" }',
                updated,
            )
            self.assertEqual(updated.count("2.1.3.dev0+master.391"), 2)
            self.assertNotIn("2.1.3.dev0+master.390", updated)

    def test_merge_rejects_report_from_different_manifest(self):
        source_text = """{"dependency_overrides":{"sima-utils":"2.1.3.dev0+master.37"}}\n"""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.json"
            report = root / "report.json"
            source.write_text(source_text, encoding="utf-8")
            report.write_text(
                json.dumps(
                    {
                        "target_arch": "x86_64",
                        "source_sha256": "wrong",
                        "components": {},
                    }
                ),
                encoding="utf-8",
            )
            second = root / "second.json"
            second.write_text(
                json.dumps(
                    {
                        "target_arch": "aarch64",
                        "source_sha256": "wrong",
                        "components": {},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                MODULE.UpdateError, "different source.json"
            ):
                MODULE.merge(
                    source,
                    [report, second],
                    output=root / "output.json",
                    summary=root / "summary.md",
                )

    def test_preserving_update_leaves_same_value_in_unmanaged_field(self):
        version = "2.1.3.dev0+master.390"
        source = {
            "note": version,
            "python-packages": [
                {"name": "sima-frontend", "version": version}
            ],
        }
        component = MODULE.collect_components(source, "x86_64")[0]
        updated = MODULE.apply_updates_preserving_format(
            json.dumps(source),
            source,
            {component.component_id: component},
            {component.component_id: "2.1.3.dev0+master.391"},
        )
        self.assertEqual(json.loads(updated)["note"], version)
        self.assertEqual(
            json.loads(updated)["python-packages"][0]["version"],
            "2.1.3.dev0+master.391",
        )

    def test_preserving_update_does_not_change_other_package_with_same_version(self):
        version = "2.1.3.dev0+master.44"
        source_text = """{
  "python-packages": [
    { "name": "pkg-a", "version": "2.1.3.dev0+master.44" },
    { "name": "pkg-b", "version": "2.1.3.dev0+master.44" }
  ]
}
"""
        source = json.loads(source_text)
        components = {
            component.component_id: component
            for component in MODULE.collect_components(source, "aarch64")
        }
        pkg_a_id = f"python:pkg-a:{version}"
        updated = MODULE.apply_updates_preserving_format(
            source_text,
            source,
            components,
            {pkg_a_id: "2.1.3.dev0+master.45"},
        )
        updated_doc = json.loads(updated)
        self.assertEqual(
            updated_doc["python-packages"][0]["version"],
            "2.1.3.dev0+master.45",
        )
        self.assertEqual(
            updated_doc["python-packages"][1]["version"],
            version,
        )

    def test_moving_vulcan_ref_is_not_managed(self):
        source = {
            "python-packages": [
                {"name": "sima_lmm[sdk]", "vulcan": {"ref": "develop"}}
            ]
        }
        self.assertEqual(MODULE.collect_components(source, "x86_64"), [])

    def test_single_architecture_report_is_authoritative(self):
        source = {
            "dependency_overrides": {
                "sima-utils": "2.1.3.dev0+master.37"
            }
        }
        component_id = "python:sima-utils:2.1.3.dev0+master.37"
        self.assertEqual(
            MODULE.select_updates(
                source,
                [
                    self.report(
                        "aarch64",
                        {
                            component_id: {
                                "available": ["2.1.3.dev0+master.38"]
                            }
                        },
                    )
                ],
            ),
            {component_id: "2.1.3.dev0+master.38"},
        )


if __name__ == "__main__":
    unittest.main()
