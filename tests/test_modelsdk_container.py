import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "scripts" / "build_modelsdk_container.sh"
DOCKERFILE = ROOT / "container" / "Dockerfile"
SHELL_INIT = ROOT / "container" / "model-compiler-shell.sh"


class ModelCompilerContainerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temp_dir.name)
        self.bundle_dir = self.work_dir / "bundle"
        self.bundle_dir.mkdir()
        for name in ("install_modelsdk_wheels.sh", "source.json", "manifest.txt"):
            (self.bundle_dir / name).write_text("test\n", encoding="utf-8")
        (self.bundle_dir / "package.whl").write_text("wheel\n", encoding="utf-8")

        self.fake_bin = self.work_dir / "bin"
        self.fake_bin.mkdir()
        self.docker_log = self.work_dir / "docker.log"
        fake_docker = self.fake_bin / "docker"
        fake_docker.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'printf "%s\\n" "$@" >> "${FAKE_DOCKER_LOG:?}"\n',
            encoding="utf-8",
        )
        fake_docker.chmod(0o755)

        fake_git = self.fake_bin / "git"
        fake_git.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'case "$*" in\n'
            '  *"branch --show-current"*) printf "%s\\n" "${FAKE_GIT_BRANCH:-feature/container}" ;;\n'
            '  *"rev-parse --short HEAD"*) printf "%s\\n" "${FAKE_GIT_HASH:-deadbee}" ;;\n'
            '  *"describe --tags --exact-match HEAD"*)\n'
            '    [[ -n "${FAKE_GIT_TAG:-}" ]] || exit 1\n'
            '    printf "%s\\n" "${FAKE_GIT_TAG}"\n'
            "    ;;\n"
            "  *) exit 1 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        fake_git.chmod(0o755)

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_build(
        self, *extra_args: str, env_overrides: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["PATH"] = f"{self.fake_bin}:{env['PATH']}"
        env["FAKE_DOCKER_LOG"] = str(self.docker_log)
        env["MODELSDK_CONTAINER_BUILD_TIME"] = "2026-08-26T12:34:56Z"
        env.pop("GITHUB_REF_TYPE", None)
        env.pop("GITHUB_REF_NAME", None)
        env.pop("GITHUB_HEAD_REF", None)
        if env_overrides:
            env.update(env_overrides)
        return subprocess.run(
            [
                str(BUILD_SCRIPT),
                "--bundle-dir",
                str(self.bundle_dir),
                "--image",
                "model-compiler:test",
                *extra_args,
            ],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
        )

    def test_dockerfile_uses_local_bundle_context_and_ubuntu_2404(self):
        text = DOCKERFILE.read_text(encoding="utf-8")
        dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        self.assertIn("ubuntu:24.04", text)
        self.assertIn("from=modelsdk_bundle", text)
        self.assertIn("MODEL_COMPILER_TARGET_ARCH", text)
        self.assertIn("MODEL_COMPILER_SMOKE_ARCH", text)
        self.assertNotIn(".netrc", text)
        self.assertNotIn("build_modelsdk_bundle.sh", text)
        self.assertIn("python3-venv", text)
        self.assertIn("libglib2.0-0", text)
        self.assertIn("MODEL_COMPILER_VERSION", text)
        self.assertIn("MODEL_COMPILER_BUILD_TIME", text)
        self.assertIn("org.opencontainers.image.source", text)
        self.assertIn("/usr/local/share/model-compiler/source.json", text)
        self.assertIn("generate-container-release", text)
        self.assertIn("--output /etc/sdk-release", text)
        self.assertIn('CMD ["bash", "-l"]', text)
        self.assertIn(".git", dockerignore.splitlines())
        self.assertIn("dist", dockerignore.splitlines())

    def test_shell_initializes_pyenv_and_model_compiler_venv(self):
        text = SHELL_INIT.read_text(encoding="utf-8")
        self.assertIn("pyenv init - bash", text)
        self.assertIn('model_compiler_home}/bin/activate', text)
        self.assertIn("[model-compiler ${MODEL_COMPILER_VERSION:-unknown:nogit}]", text)

    def test_prompt_is_restored_after_bashrc_reset(self):
        command = (
            f". {SHELL_INIT}; "
            "PS1='reset$ '; "
            f". {SHELL_INIT}; "
            'printf "%s" "$PS1"'
        )
        result = subprocess.run(
            ["bash", "--noprofile", "--norc", "-i", "-c", command],
            env={**os.environ, "MODEL_COMPILER_VERSION": "feature/test:deadbee"},
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout, "[model-compiler feature/test:deadbee] reset$ "
        )

    def test_build_uses_amd64_and_local_bundle_context(self):
        result = self.run_build()

        self.assertEqual(result.returncode, 0, result.stderr)
        args = self.docker_log.read_text(encoding="utf-8").splitlines()
        self.assertIn("buildx", args)
        self.assertIn("linux/amd64", args)
        self.assertIn("MODEL_COMPILER_TARGET_ARCH=x86_64", args)
        self.assertIn("MODEL_COMPILER_SMOKE_ARCH=amd64", args)
        self.assertIn(f"modelsdk_bundle={self.bundle_dir}", args)
        self.assertIn("model-compiler:test", args)
        self.assertIn("MODEL_COMPILER_GIT_BRANCH=feature/container", args)
        self.assertIn("MODEL_COMPILER_GIT_HASH=deadbee", args)
        self.assertIn("MODEL_COMPILER_VERSION=feature/container:deadbee", args)
        self.assertIn("MODEL_COMPILER_BUILD_TIME=2026-08-26T12:34:56Z", args)
        self.assertIn("MODEL_COMPILER_SOURCE_URL=", args)
        self.assertNotIn("run", args)

    def test_build_accepts_workflow_source_metadata_overrides(self):
        result = self.run_build(
            env_overrides={
                "MODELSDK_CONTAINER_GIT_BRANCH": "feature/workflow-run",
                "MODELSDK_CONTAINER_GIT_HASH": "1234567890abcdef",
                "MODELSDK_CONTAINER_SOURCE_URL": "https://github.com/sima-neat/model-compiler",
            }
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        args = self.docker_log.read_text(encoding="utf-8").splitlines()
        self.assertIn("MODEL_COMPILER_GIT_BRANCH=feature/workflow-run", args)
        self.assertIn("MODEL_COMPILER_GIT_HASH=1234567", args)
        self.assertIn("MODEL_COMPILER_VERSION=feature/workflow-run:1234567", args)
        self.assertIn(
            "MODEL_COMPILER_SOURCE_URL=https://github.com/sima-neat/model-compiler",
            args,
        )

    def test_build_supports_registry_cache_import_and_export(self):
        result = self.run_build(
            env_overrides={
                "BUILDX_CACHE_FROM": (
                    "ghcr.io/sima-neat/model-compiler-feature:buildcache-amd64 "
                    "ghcr.io/sima-neat/model-compiler-develop:buildcache-amd64"
                ),
                "BUILDX_CACHE_TO": (
                    "ghcr.io/sima-neat/model-compiler-feature:buildcache-amd64"
                ),
            }
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        args = self.docker_log.read_text(encoding="utf-8").splitlines()
        self.assertIn(
            "type=registry,ref=ghcr.io/sima-neat/model-compiler-feature:buildcache-amd64",
            args,
        )
        self.assertIn(
            "type=registry,ref=ghcr.io/sima-neat/model-compiler-develop:buildcache-amd64",
            args,
        )
        self.assertIn(
            "type=registry,ref=ghcr.io/sima-neat/model-compiler-feature:buildcache-amd64,"
            "mode=max,oci-mediatypes=true,image-manifest=true",
            args,
        )

    def test_build_supports_native_arm64_target(self):
        result = self.run_build("--target-arch", "arm64")

        self.assertEqual(result.returncode, 0, result.stderr)
        args = self.docker_log.read_text(encoding="utf-8").splitlines()
        self.assertIn("linux/arm64", args)
        self.assertIn("MODEL_COMPILER_TARGET_ARCH=aarch64", args)
        self.assertIn("MODEL_COMPILER_SMOKE_ARCH=arm64", args)

    def test_build_accepts_aarch64_alias(self):
        result = self.run_build("--target-arch", "aarch64")

        self.assertEqual(result.returncode, 0, result.stderr)
        args = self.docker_log.read_text(encoding="utf-8").splitlines()
        self.assertIn("linux/arm64", args)

    def test_build_rejects_unknown_target_architecture(self):
        result = self.run_build("--target-arch", "riscv64")

        self.assertEqual(result.returncode, 2)
        self.assertIn("Unsupported target architecture: riscv64", result.stderr)
        self.assertFalse(self.docker_log.exists())

    def test_exact_official_release_tag_is_used_as_version(self):
        result = self.run_build(env_overrides={"FAKE_GIT_TAG": "v2.1.3"})

        self.assertEqual(result.returncode, 0, result.stderr)
        args = self.docker_log.read_text(encoding="utf-8").splitlines()
        self.assertIn("MODEL_COMPILER_VERSION=v2.1.3", args)

    def test_non_release_tag_uses_branch_and_hash_version(self):
        result = self.run_build(env_overrides={"FAKE_GIT_TAG": "nightly"})

        self.assertEqual(result.returncode, 0, result.stderr)
        args = self.docker_log.read_text(encoding="utf-8").splitlines()
        self.assertIn("MODEL_COMPILER_VERSION=feature/container:deadbee", args)

    def test_smoke_test_is_opt_in(self):
        result = self.run_build("--smoke-test")

        self.assertEqual(result.returncode, 0, result.stderr)
        args = self.docker_log.read_text(encoding="utf-8").splitlines()
        self.assertIn("run", args)
        self.assertTrue(any(arg.endswith("/smoke_test_modelsdk.py") for arg in args))
        self.assertIn("basic", args)

    def test_missing_manifest_fails_before_docker_build(self):
        (self.bundle_dir / "manifest.txt").unlink()

        result = self.run_build()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing manifest.txt", result.stderr)
        self.assertFalse(self.docker_log.exists())

    def test_credential_file_in_bundle_is_rejected(self):
        (self.bundle_dir / ".netrc").write_text("machine example.invalid\n", encoding="utf-8")

        result = self.run_build()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("credential file .netrc", result.stderr)
        self.assertFalse(self.docker_log.exists())


if __name__ == "__main__":
    unittest.main()
