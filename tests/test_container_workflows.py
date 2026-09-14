import json
import subprocess
import textwrap
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
        completion_trigger = text.split("  workflow_run:", 1)[1].split("  workflow_call:", 1)[0]
        self.assertIn("branches-ignore: [daily]", completion_trigger)
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

        self.assertNotIn("createHash", text)
        self.assertIn("packageForBranch(branch)", text)
        self.assertIn('--tag "${IMAGE}:${SHA}"', text)
        self.assertIn('--tag "${IMAGE}:latest"', text)
        self.assertIn("packages: write", text)

    def test_package_names_match_sdk_convention_in_publish_and_cleanup(self):
        branches = ["main", "daily", "develop", "fix/Container-Build", "fix--foo", "///"]
        expected = ["model-compiler", "model-compiler-daily", "model-compiler-develop",
                    "model-compiler-fix-container-build", "model-compiler-fix-foo",
                    "model-compiler-branch"]
        for path in (PUBLISH_WORKFLOW, CLEANUP_WORKFLOW):
            with self.subTest(workflow=path.name):
                script = path.read_text().split("            function packageForBranch", 1)[1]
                helper = "function packageForBranch" + script.split("\n            }", 1)[0] + "\n}"
                result = subprocess.run(
                    ["node", "-e", helper + "\nconsole.log(JSON.stringify(" +
                     json.dumps(branches) + ".map(packageForBranch)));"],
                    check=True, capture_output=True, text=True,
                )
                self.assertEqual(json.loads(result.stdout), expected)

    def test_cleanup_preserves_live_legacy_and_shared_packages(self):
        script = textwrap.dedent(CLEANUP_WORKFLOW.read_text().split("          script: |\n", 1)[1])
        harness = r"""
const crypto = require('crypto');
const legacy = 'model-compiler-daily-' + crypto.createHash('sha256').update('daily').digest('hex').slice(0, 12);
const deleted = [];
const names = ['model-compiler', 'model-compiler-daily', legacy,
               'model-compiler-fix-foo', 'model-compiler-removed'];
const context = {repo: {owner: 'sima-neat', repo: 'model-compiler'}};
const core = {info() {}, warning() {}};
process.env.DELETED_REF = 'fix/foo';
process.env.DELETED_REF_TYPE = 'branch';
process.env.REQUESTED_BRANCH = 'main';
process.env.DRY_RUN = 'false';
const github = {
  async paginate(route) {
    if (route.endsWith('/branches')) return [{name: 'daily'}, {name: 'fix-foo'}];
    if (route.endsWith('/packages')) return names.map(name => ({name}));
    throw new Error(route);
  },
  async request(route, params) {
    if (route.endsWith('/runs')) return {data: {workflow_runs: []}};
    if (route.startsWith('GET ')) return {data: {repository: {full_name: 'sima-neat/model-compiler'}}};
    if (route.startsWith('DELETE ')) {deleted.push(params.package_name); return {};}
    throw new Error(route);
  },
};
"""
        result = subprocess.run(
            ["node", "-e", harness + "\n(async () => {\n" + script +
             "\nconsole.log(JSON.stringify(deleted));\n})().catch(e => {console.error(e); process.exit(1)});"],
            check=True, capture_output=True, text=True,
        )
        self.assertIn("model-compiler-removed", json.loads(result.stdout))
        self.assertNotIn("model-compiler", json.loads(result.stdout))
        self.assertNotIn("model-compiler-daily", json.loads(result.stdout))
        self.assertNotIn("model-compiler-fix-foo", json.loads(result.stdout))
        self.assertFalse(any(name.startswith("model-compiler-daily-") for name in json.loads(result.stdout)))

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

    def test_daily_branch_calls_publisher_after_package_tests(self):
        build_text = BUILD_WORKFLOW.read_text(encoding="utf-8")
        publish_text = PUBLISH_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("workflow_call:", publish_text)
        self.assertIn("source_run_id:", publish_text)
        self.assertIn("daily-containers:", build_text)
        self.assertIn("github.ref_name == 'daily'", build_text)
        self.assertIn("- test-package-install", build_text)
        self.assertIn("uses: ./.github/workflows/container-build.yml", build_text)
        self.assertIn("source_run_id: ${{ github.run_id }}", build_text)

    def test_cleanup_handles_branch_deletion_and_reconciliation(self):
        text = CLEANUP_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("delete:", text)
        self.assertIn("schedule:", text)
        self.assertIn("github.event.ref_type", text)
        self.assertIn("legacyPackageForBranch(branchName)", text)
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
