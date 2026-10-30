import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install_modelsdk_wheels.sh"


def host_build_functions():
    script = INSTALLER.read_text(encoding="utf-8")
    # Load the actual helper definitions without running installation.
    start = script.index("host_multiarch_triplet() {")
    end = script.index("ensure_python_cmd() {", start)
    return script[start:end]


class InstallerHostBuildEnvTests(unittest.TestCase):
    def run_host(self, command, overrides=None):
        env = os.environ.copy()
        env.update(overrides or {})
        return subprocess.run(
            ["bash", "-c", "set -euo pipefail\n" + host_build_functions()
             + "\nrun_host_build_env " + shlex.join(command)],
            env=env, text=True, capture_output=True,
        )

    def test_sdk_compiler_overrides_do_not_reach_native_build(self):
        cleared = (
            "CFLAGS", "CPPFLAGS", "CXXFLAGS", "LDFLAGS", "CPATH",
            "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "OBJC_INCLUDE_PATH",
            "LIBRARY_PATH", "GCC_EXEC_PREFIX", "COMPILER_PATH",
            "CMAKE_TOOLCHAIN_FILE", "SDKTARGETSYSROOT",
        )
        overrides = {key: "/sdk/foreign-toolchain" for key in cleared}
        overrides.update(CC="sdk-gcc", CXX="sdk-g++", MODELSDK_BUILD_PARALLEL_LEVEL="2")
        result = self.run_host(
            [sys.executable, "-c", "import json, os; print(json.dumps(dict(os.environ)))"],
            overrides,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        env = json.loads(result.stdout)
        for key in cleared:
            with self.subTest(key=key):
                self.assertNotIn(key, env)
        self.assertEqual(env["CC"], "gcc")
        self.assertEqual(env["CXX"], "g++")
        self.assertTrue(env["PATH"].startswith("/usr/bin:/bin:"))
        self.assertEqual(env["CMAKE_ARGS"], "-DGGML_NATIVE=OFF -DLLAVA_BUILD=OFF")
        self.assertEqual(env["CMAKE_BUILD_PARALLEL_LEVEL"], "2")

    @unittest.skipUnless(
        sys.platform.startswith("linux") and Path("/usr/bin/g++").exists()
        and shutil.which("cmake"), "requires native Linux g++ and CMake",
    )
    def test_cmake_build_uses_native_standard_library_despite_sdk_headers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            foreign = root / "sdk-headers"
            foreign.mkdir()
            (foreign / "vector").write_text('#error "SDK headers leaked into native build"\n')
            (root / "main.cpp").write_text(
                "#include <vector>\n#include <string>\n#include <type_traits>\n"
                "template<class T> constexpr bool supported = false;\n"
                "template<> constexpr bool supported<int> = true;\n"
                "int main() { static_assert(supported<int>); "
                'std::vector<std::string> v{"native"}; return v.size() != 1; }\n'
            )
            (root / "CMakeLists.txt").write_text(
                "cmake_minimum_required(VERSION 3.16)\nproject(host_probe LANGUAGES CXX)\n"
                "set(CMAKE_CXX_STANDARD 17)\nadd_executable(host_probe main.cpp)\n"
            )
            overrides = {
                "CPATH": str(foreign), "CPLUS_INCLUDE_PATH": str(foreign),
                "CXXFLAGS": f"-isystem {foreign}", "CXX": "sdk-g++",
            }
            build = root / "build"
            for command in (
                ["cmake", "-S", str(root), "-B", str(build)],
                ["cmake", "--build", str(build)],
                [str(build / "host_probe")],
            ):
                result = self.run_host(command, overrides)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
