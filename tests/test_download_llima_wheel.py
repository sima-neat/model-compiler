import json
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "download_llima_wheel.sh"


class DownloadLlimaWheelTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temp_dir.name)
        self.call_count = 0
        self.cli_log = self.work_dir / "sima-cli.log"
        self.fake_cli = self.work_dir / "sima-cli"
        self.fake_cli.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'printf "%s\\n" "$@" >> "${FAKE_SIMA_CLI_LOG:?}"\n'
            'target="${@: -1}"\n'
            'if [[ "$target" == "${FAKE_SIMA_CLI_FAIL_TARGET:-}" ]]; then exit 1; fi\n'
            'shopt -s nullglob\n'
            'wheels=("${FAKE_SIMA_CLI_WHEELS:?}"/*.whl)\n'
            'if (( ${#wheels[@]} )); then cp "${wheels[@]}" "${@: -2:1}/"; fi\n',
            encoding="utf-8",
        )
        self.fake_cli.chmod(0o755)

    def tearDown(self):
        self.temp_dir.cleanup()

    def make_wheel(self, output_dir, version):
        wheel = output_dir / f"sima_lmm-{version}-py3-none-any.whl"
        dist_info = f"sima_lmm-{version}.dist-info"
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr(
                f"{dist_info}/METADATA",
                "Metadata-Version: 2.1\n"
                "Name: sima-lmm\n"
                f"Version: {version}\n",
            )
        return wheel

    def run_helper(
        self,
        manifest,
        *,
        arch="x86_64",
        wheel_versions=(),
        github_ref_name=None,
        github_ref_type=None,
        fail_target=None,
    ):
        self.call_count += 1
        manifest_path = self.work_dir / f"source-{self.call_count}.json"
        output_dir = self.work_dir / f"output-{self.call_count}"
        wheels_dir = self.work_dir / f"wheels-{self.call_count}"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        output_dir.mkdir()
        wheels_dir.mkdir()
        for version in wheel_versions:
            self.make_wheel(wheels_dir, version)

        self.cli_log.unlink(missing_ok=True)
        env = os.environ.copy()
        env.update(
            {
                "SIMA_CLI_BIN": str(self.fake_cli),
                "FAKE_SIMA_CLI_LOG": str(self.cli_log),
                "FAKE_SIMA_CLI_WHEELS": str(wheels_dir),
            }
        )
        for name, value in (
            ("GITHUB_REF_NAME", github_ref_name),
            ("GITHUB_REF_TYPE", github_ref_type),
            ("FAKE_SIMA_CLI_FAIL_TARGET", fail_target),
        ):
            if value is None:
                env.pop(name, None)
            else:
                env[name] = value
        result = subprocess.run(
            [
                str(HELPER),
                "--output-dir",
                str(output_dir),
                "--source-json",
                str(manifest_path),
                "--target-arch",
                arch,
            ],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
        )
        return result, output_dir

    def assert_cli_target(self, expected):
        args = self.cli_log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(args[-1], expected)

    def cli_targets(self):
        return [
            arg
            for arg in self.cli_log.read_text(encoding="utf-8").splitlines()
            if arg.startswith("llima/compiler@")
        ]

    def test_architecture_override_is_authoritative(self):
        manifest = {
            "python-packages": [
                {"name": "sima_lmm[sdk]", "vulcan": {"ref": "develop"}}
            ],
            "aarch64": {
                "python-packages": [
                    {
                        "name": "sima_lmm[sdk]",
                        "vulcan": {"ref": "arm-develop"},
                    }
                ]
            },
        }

        result, _ = self.run_helper(
            manifest,
            arch="arm64",
            wheel_versions=["0.4.0+arm.abcdef123456"],
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_cli_target("llima/compiler@arm-develop")

    def test_architecture_override_can_omit_llima(self):
        manifest = {
            "python-packages": [
                {"name": "sima_lmm[sdk]", "vulcan": {"ref": "develop"}}
            ],
            "aarch64": {
                "python-packages": [{"name": "pyyaml", "version": "6.0.3"}]
            },
        }

        result, _ = self.run_helper(manifest, arch="aarch64")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertFalse(self.cli_log.exists())

    def test_top_level_ref_is_used_without_override(self):
        manifest = {
            "python-packages": [
                {"name": "sima_lmm[sdk]", "vulcan": {"ref": "develop"}}
            ]
        }

        result, output_dir = self.run_helper(
            manifest,
            wheel_versions=["0.4.0+develop.abcdef123456"],
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_cli_target("llima/compiler@develop")
        provenance = json.loads(
            (output_dir / "resolved-llima-package.json").read_text(encoding="utf-8")
        )["sima_lmm"]
        self.assertEqual(provenance["requested-ref"], "develop")
        self.assertEqual(provenance["resolved-commit"], "abcdef123456")
        self.assertEqual(provenance["version"], "0.4.0+develop.abcdef123456")

    def test_missing_or_invalid_ref_fails(self):
        for ref in (None, "", 123):
            with self.subTest(ref=ref):
                vulcan = {} if ref is None else {"ref": ref}
                manifest = {
                    "python-packages": [
                        {"name": "sima_lmm[sdk]", "vulcan": vulcan}
                    ]
                }

                result, _ = self.run_helper(manifest)

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("requires either vulcan.policy", result.stderr)
                self.assertFalse(self.cli_log.exists())

    def test_snap_uses_matching_branch(self):
        manifest = {
            "python-packages": [
                {"name": "sima_lmm[sdk]", "vulcan": {"policy": "snap"}}
            ]
        }

        result, output_dir = self.run_helper(
            manifest,
            wheel_versions=["0.4.0+topic.abcdef123456"],
            github_ref_name="feature/topic",
            github_ref_type="branch",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_cli_target("llima/compiler@feature/topic")
        provenance = json.loads(
            (output_dir / "resolved-llima-package.json").read_text(encoding="utf-8")
        )["sima_lmm"]
        self.assertEqual(provenance["requested-ref"], "feature/topic")

    def test_snap_feature_branch_falls_back_to_develop(self):
        manifest = {
            "python-packages": [
                {"name": "sima_lmm[sdk]", "vulcan": {"policy": "snap"}}
            ]
        }

        result, output_dir = self.run_helper(
            manifest,
            wheel_versions=["0.4.0+develop.abcdef123456"],
            github_ref_name="feature/missing",
            github_ref_type="branch",
            fail_target="llima/compiler@feature/missing",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.cli_targets(),
            ["llima/compiler@feature/missing", "llima/compiler@develop"],
        )
        provenance = json.loads(
            (output_dir / "resolved-llima-package.json").read_text(encoding="utf-8")
        )["sima_lmm"]
        self.assertEqual(provenance["requested-ref"], "develop")

    def test_snap_protected_branch_does_not_fallback(self):
        manifest = {
            "python-packages": [
                {"name": "sima_lmm[sdk]", "vulcan": {"policy": "snap"}}
            ]
        }

        for branch in ("develop", "main", "release-2.1"):
            with self.subTest(branch=branch):
                result, _ = self.run_helper(
                    manifest,
                    wheel_versions=["0.4.0+develop.abcdef123456"],
                    github_ref_name=branch,
                    github_ref_type="branch",
                    fail_target=f"llima/compiler@{branch}",
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.cli_targets(), [f"llima/compiler@{branch}"])

    def test_tag_build_rejects_snap_and_unqualified_ref(self):
        snap_manifest = {
            "python-packages": [
                {"name": "sima_lmm[sdk]", "vulcan": {"policy": "snap"}}
            ]
        }
        result, _ = self.run_helper(
            snap_manifest,
            github_ref_name="v2.1.3",
            github_ref_type="tag",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("snap policy is not allowed", result.stderr)

        floating_manifest = {
            "python-packages": [
                {"name": "sima_lmm[sdk]", "vulcan": {"ref": "v0.4.0"}}
            ]
        }
        result, _ = self.run_helper(
            floating_manifest,
            github_ref_name="v2.1.3",
            github_ref_type="tag",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("commit-qualified", result.stderr)

        pinned_manifest = {
            "python-packages": [
                {
                    "name": "sima_lmm[sdk]",
                    "vulcan": {"ref": "v0.4.0:deadbeef1234"},
                }
            ]
        }
        result, _ = self.run_helper(
            pinned_manifest,
            wheel_versions=["0.4.0"],
            github_ref_name="v2.1.3",
            github_ref_type="tag",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_cli_target("llima/compiler@v0.4.0:deadbeef1234")

    def test_unsupported_vulcan_package_fails(self):
        manifest = {
            "python-packages": [
                {"name": "future-package", "vulcan": {"ref": "develop"}}
            ]
        }

        result, _ = self.run_helper(manifest)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("uses unsupported Vulcan package", result.stderr)
        self.assertFalse(self.cli_log.exists())

    def test_zero_downloaded_wheels_fails(self):
        manifest = {
            "python-packages": [
                {"name": "sima_lmm[sdk]", "vulcan": {"ref": "develop"}}
            ]
        }

        result, _ = self.run_helper(manifest)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("found 0", result.stderr)

    def test_multiple_downloaded_wheels_fails(self):
        manifest = {
            "python-packages": [
                {"name": "sima_lmm[sdk]", "vulcan": {"ref": "develop"}}
            ]
        }

        result, _ = self.run_helper(
            manifest,
            wheel_versions=[
                "0.4.0+develop.abcdef123456",
                "0.4.0+develop.123456abcdef",
            ],
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("found 2", result.stderr)

    def test_immutable_branch_commit_ref_is_forwarded(self):
        manifest = {
            "python-packages": [
                {
                    "name": "sima_lmm[sdk]",
                    "vulcan": {"ref": "release-0.4:deadbeef1234"},
                }
            ]
        }

        result, output_dir = self.run_helper(
            manifest,
            wheel_versions=["0.4.0"],
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_cli_target("llima/compiler@release-0.4:deadbeef1234")
        provenance = json.loads(
            (output_dir / "resolved-llima-package.json").read_text(encoding="utf-8")
        )["sima_lmm"]
        self.assertEqual(provenance["resolved-commit"], "deadbeef1234")

    def test_immutable_tag_ref_is_forwarded(self):
        manifest = {
            "python-packages": [
                {"name": "sima_lmm[sdk]", "vulcan": {"ref": "v0.4.0"}}
            ]
        }

        result, output_dir = self.run_helper(
            manifest,
            wheel_versions=["0.4.0+release.deadbeef1234"],
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_cli_target("llima/compiler@v0.4.0")
        provenance = json.loads(
            (output_dir / "resolved-llima-package.json").read_text(encoding="utf-8")
        )["sima_lmm"]
        self.assertEqual(provenance["resolved-commit"], "deadbeef1234")


if __name__ == "__main__":
    unittest.main()
