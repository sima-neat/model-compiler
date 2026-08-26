import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
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

        self.assertIn("run-id: ${{ github.event.workflow_run.id }}", text)
        self.assertIn("name: model-compiler-${{ matrix.arch }}", text)
        self.assertIn("runner: ubuntu-24.04", text)
        self.assertIn("runner: ubuntu-24.04-arm", text)
        self.assertIn("--smoke-test", text)
        self.assertIn('"${IMAGE}:${SHA}-amd64"', text)
        self.assertIn('"${IMAGE}:${SHA}-arm64"', text)

    def test_publish_uses_branch_scoped_package_and_multiarch_latest(self):
        text = PUBLISH_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("model-compiler-${slug}", text)
        self.assertIn('--tag "${IMAGE}:${SHA}"', text)
        self.assertIn('--tag "${IMAGE}:latest"', text)
        self.assertIn("packages: write", text)

    def test_cleanup_handles_branch_deletion_and_reconciliation(self):
        text = CLEANUP_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("delete:", text)
        self.assertIn("schedule:", text)
        self.assertIn("github.event.ref_type", text)
        self.assertIn("model-compiler-${branchSlug(branchName)}", text)
        self.assertIn("livePackages.has(packageName)", text)
        self.assertIn("DELETE /orgs/{org}/packages/{package_type}/{package_name}", text)
        self.assertIn("model-compiler-container-{0}", text)
        self.assertIn("packages: write", text)


if __name__ == "__main__":
    unittest.main()
