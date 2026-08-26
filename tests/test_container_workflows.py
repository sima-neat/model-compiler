import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
PUBLISH_WORKFLOW = ROOT / ".github" / "workflows" / "container-build.yml"
CLEANUP_WORKFLOW = ROOT / ".github" / "workflows" / "cleanup-container-packages.yml"


class ContainerWorkflowTests(unittest.TestCase):
    def test_publish_runs_only_after_successful_branch_build(self):
        text = PUBLISH_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("workflows: [Build]", text)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", text)
        self.assertIn("github.event.workflow_run.event == 'push'", text)
        self.assertIn("head_repository.full_name == github.repository", text)
        self.assertIn("Verify branch still points to the successful commit", text)
        self.assertIn("ref: ${{ needs.prepare.outputs.sha }}", text)

    def test_publish_uses_build_artifacts_for_both_architectures(self):
        text = PUBLISH_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("run-id: ${{ needs.prepare.outputs.run_id }}", text)
        self.assertIn("name: model-compiler-${{ matrix.arch }}", text)
        self.assertIn('archive="_package/model-compiler-${ARCH}.zip"', text)
        self.assertIn('unzip -oq "${archive}" -d _bundle', text)
        self.assertIn("--bundle-dir _bundle", text)
        self.assertIn("runner: ubuntu-24.04", text)
        self.assertIn("runner: ubuntu-24.04-arm", text)
        self.assertIn("--smoke-test", text)
        self.assertIn('"${IMAGE}:${SHA}-amd64"', text)
        self.assertIn('"${IMAGE}:${SHA}-arm64"', text)

    def test_publish_uses_branch_scoped_package_and_multiarch_latest(self):
        text = PUBLISH_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("createHash('sha256')", text)
        self.assertIn(".slice(0, 12)", text)
        self.assertIn("packageForBranch(branch)", text)
        self.assertIn('--tag "${IMAGE}:${SHA}"', text)
        self.assertIn('--tag "${IMAGE}:latest"', text)
        self.assertIn("packages: write", text)

    def test_publish_uses_architecture_scoped_registry_caches(self):
        text = PUBLISH_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("Set up Docker Buildx", text)
        self.assertIn("base_cache_image", text)
        self.assertIn(":buildcache-${{ matrix.arch }}", text)
        self.assertIn("BUILDX_CACHE_FROM:", text)
        self.assertIn("BUILDX_CACHE_TO:", text)
        self.assertLess(
            text.index("Log in to GitHub Container Registry"),
            text.index("Build and smoke-test container"),
        )

    def test_feature_branch_can_call_publisher_after_package_tests(self):
        build_text = BUILD_WORKFLOW.read_text(encoding="utf-8")
        publish_text = PUBLISH_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("workflow_call:", publish_text)
        self.assertIn("source_run_id:", publish_text)
        self.assertIn("test-branch-containers:", build_text)
        self.assertIn("github.ref_name == 'container-image'", build_text)
        self.assertIn("- test-package-install", build_text)
        self.assertIn("uses: ./.github/workflows/container-build.yml", build_text)
        self.assertIn("source_run_id: ${{ github.run_id }}", build_text)

    def test_cleanup_handles_branch_deletion_and_reconciliation(self):
        text = CLEANUP_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("delete:", text)
        self.assertIn("schedule:", text)
        self.assertIn("github.event.ref_type", text)
        self.assertIn("model-compiler-${branchSlug(branchName)}", text)
        self.assertIn("GET /orgs/{org}/packages", text)
        self.assertIn("package_type: 'container'", text)
        self.assertIn("addPackageCandidate(packageName)", text)
        self.assertIn("createHash('sha256')", text)
        self.assertIn("livePackages.has(packageName)", text)
        self.assertIn("DELETE /orgs/{org}/packages/{package_type}/{package_name}", text)
        self.assertIn("model-compiler-container-{0}", text)
        self.assertIn("packages: write", text)


if __name__ == "__main__":
    unittest.main()
