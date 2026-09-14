import os
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest


FIX_LIBS = Path(__file__).resolve().parents[2] / 'tools' / 'osx-fix-libs.py'
MAC_TOOLS = ('clang', 'otool', 'install_name_tool', 'codesign')


@unittest.skipUnless(sys.platform == 'darwin' and all(shutil.which(tool) for tool in MAC_TOOLS),
                     'requires macOS and Xcode command line tools')
class FixLibsTests(unittest.TestCase):
    def __init__(self, methodName: str = 'runTest') -> None:
        super().__init__(methodName)
        self.root = self.build = self.macos = self.binary = Path()
        self.env: dict[str, str] = {}

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix='aegisub 한글 경로 ')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.build = self.root / 'build libraries'
        self.macos = self.root / 'Fixture.app' / 'Contents' / 'MacOS'
        self.build.mkdir()
        self.macos.mkdir(parents=True)
        self.binary = self.macos / 'aegisub'
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith('DYLD_')}
        self.env['AEGISUB_BUNDLE_SIGNATURE'] = '-'

    def run_tool(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(args, check=True, capture_output=True, text=True,
                              env=self.env, timeout=30)

    def compile(self, output: Path, source: str, *flags: str | Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['clang', '-arch', platform.machine(), '-x', 'c', '-',
                        '-x', 'none', '-Wl,-headerpad_max_install_names',
                        '-o', str(output), *map(str, flags)], input=source,
                       check=True, capture_output=True, text=True, env=self.env, timeout=30)

    def library(self, name: str, symbol: str, value: int, install_name: str = '') -> Path:
        path = self.build / name
        self.compile(path, f'int {symbol}(void) {{ return {value}; }}',
                     '-dynamiclib', '-Wl,-install_name,' + (install_name or str(path)))
        return path

    def repair(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(FIX_LIBS), str(self.binary)],
                              capture_output=True, text=True, env=self.env, timeout=15)

    def assert_repaired(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_runs_after_relocation_without_build_libraries(self):
        # Given: absolute symlinks, loader/executable paths and inherited RPATHs.
        alias = self.build / 'lib alias.dylib'
        base = self.library('versions/lib base.1.dylib', 'base', 10, str(alias))
        alias.symlink_to(base)
        base.chmod(0o444)
        original_base = base.read_bytes()
        relative = self.library('lib relative.dylib', 'relative', 10,
                                '@loader_path/lib relative.dylib')
        inherited = self.library('rpath leaves/lib inherited.dylib', 'inherited', 12,
                                 '@rpath/lib inherited.dylib')
        embedded = self.macos / 'lib executable.dylib'
        self.compile(embedded, 'int embedded(void) { return 10; }', '-dynamiclib',
                     '-Wl,-install_name,@executable_path/lib executable.dylib')
        top = self.build / 'lib top.dylib'
        self.compile(top, 'int base(void), relative(void), inherited(void), embedded(void);'
                     'int top(void) { return base()+relative()+inherited()+embedded(); }',
                     '-dynamiclib', '-Wl,-install_name,@rpath/lib top.dylib',
                     '-Wl,-rpath,@loader_path/missing local',
                     alias, relative, inherited, embedded)
        native_lib = self.library('native deps/lib native.dylib', 'native_value', 7,
                                  '@rpath/lib native.dylib')
        module = self.macos.parent / 'SharedSupport' / 'automation' / 'native module.so'
        self.compile(module, 'int native_value(void);'
                     'int module_value(void) { return native_value(); }',
                     '-bundle', '-Wl,-rpath,' + str(native_lib.parent), native_lib)
        self.compile(self.binary, '#include <dlfcn.h>\n#include <stdio.h>\n'
                     'int top(void); int main(int argc, char **argv) {'
                     'void *m = dlopen(argv[1], RTLD_NOW);'
                     'if (!m) { puts(dlerror()); return 1; }'
                     'int (*f)(void) = (int (*)(void))dlsym(m, "module_value");'
                     'if (!f) return 2; printf("%d %d\\n", top(), f()); return 0; }',
                     top, '-Wl,-rpath,@executable_path/missing first',
                     '-Wl,-rpath,' + str(self.build),
                     '-Wl,-rpath,' + str(inherited.parent))
        self.run_tool('codesign', '--remove-signature', str(self.binary))

        # When: the CLI repairs the graph before its original sources disappear.
        result = self.repair()

        # Then: copied code has valid signatures and runs in a different location.
        self.assert_repaired(result)
        self.assertEqual(base.read_bytes(), original_base)
        self.assertEqual(base.stat().st_mode & 0o777, 0o444)
        images = [self.binary, module, *self.macos.glob('*.dylib')]
        self.assertEqual(len(images), 8)
        for path in images:
            self.assertFalse(path.is_symlink(), str(path))
            self.run_tool('codesign', '--verify', '--strict', str(path))
            loads = self.run_tool('otool', '-l', str(path)).stdout
            self.assertNotIn(str(self.build), loads)
        for path in self.macos.glob('*.dylib'):
            identity = self.run_tool('otool', '-D', str(path)).stdout.splitlines()[1]
            self.assertEqual(identity, '@executable_path/' + path.name)
        shutil.rmtree(self.build)
        relocated = self.root / '이동한 앱 공간' / 'Relocated.app'
        relocated.parent.mkdir()
        self.macos.parent.parent.rename(relocated)
        output = self.run_tool(str(relocated / 'Contents' / 'MacOS' / 'aegisub'),
                               str(relocated / module.relative_to(self.root / 'Fixture.app')))
        self.assertEqual(output.stdout, '42 7\n')

    def test_rejects_unresolved_dependency_without_modifying_executable(self):
        # Given: a linked build dependency has disappeared.
        missing = self.library('lib missing.dylib', 'value', 3)
        self.compile(self.binary, 'int value(void); int main(void) { return value(); }', missing)
        original = self.binary.read_bytes()
        missing.unlink()

        # When: dependency discovery cannot resolve it.
        result = self.repair()

        # Then: the CLI fails with the missing path and preserves its input.
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(str(missing), result.stdout + result.stderr)
        self.assertEqual(self.binary.read_bytes(), original)

    def test_rejects_conflicting_flattened_names(self):
        # Given: two distinct build libraries would occupy the same bundle path.
        first = self.library('one/lib duplicate.dylib', 'first', 1)
        second = self.library('two/lib duplicate.dylib', 'second', 2)
        self.compile(self.binary, 'int first(void), second(void);'
                     'int main(void) { return first()+second(); }', first, second)
        original = self.binary.read_bytes()

        # When: flattening the dependency graph would overwrite one library.
        result = self.repair()

        # Then: both conflicting sources are reported before changing the executable.
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(str(first), result.stdout + result.stderr)
        self.assertIn(str(second), result.stdout + result.stderr)
        self.assertEqual(self.binary.read_bytes(), original)

    def test_materializes_external_native_module_symlink(self):
        # Given: an installed native module symlinks to code in the build tree.
        dependency = self.library('modules/lib value.dylib', 'value', 5,
                                  '@loader_path/lib value.dylib')
        source = self.build / 'modules' / 'native.so'
        self.compile(source, 'int value(void); int module_value(void) { return value(); }',
                     '-bundle', dependency)
        module = self.macos.parent / 'SharedSupport' / 'native.so'
        module.parent.mkdir()
        module.symlink_to(source)
        original = source.read_bytes()
        self.compile(self.binary, 'int main(void) { return 0; }')

        # When: native code is included in the dependency repair.
        result = self.repair()

        # Then: its bundle copy is independent of the unmodified external source.
        self.assert_repaired(result)
        self.assertFalse(module.is_symlink())
        self.assertEqual(source.read_bytes(), original)
        shutil.rmtree(self.build)
        self.run_tool('codesign', '--verify', '--strict', str(module))
        self.assertIn('@loader_path/../MacOS/lib value.dylib',
                      self.run_tool('otool', '-L', str(module)).stdout)

    def test_reports_copy_permission_failure(self) -> None:
        dependency = self.library('lib copy.dylib', 'value', 0)
        self.compile(self.binary, 'int value(void); int main(void) { return value(); }', dependency)
        original = self.binary.read_bytes()
        self.macos.chmod(0o555)
        self.addCleanup(self.macos.chmod, 0o755)

        result = self.repair()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(str(self.macos / dependency.name), result.stdout + result.stderr)
        self.assertEqual(self.binary.read_bytes(), original)

    def test_respects_signing_identity_and_reports_failure(self) -> None:
        self.compile(self.binary, 'int main(void) { return 0; }')
        self.env['AEGISUB_BUNDLE_SIGNATURE'] = 'Missing Aegisub fixture identity'

        result = self.repair()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(self.env['AEGISUB_BUNDLE_SIGNATURE'], result.stdout + result.stderr)

    def test_repairs_twice_through_symlinked_bundle_directory(self) -> None:
        dependency = self.library('lib repeat.dylib', 'value', 0)
        self.compile(self.binary, 'int value(void); int main(void) { return value(); }', dependency)
        alias = self.root / '다른 경로'
        alias.symlink_to(self.macos, target_is_directory=True)
        self.binary = alias / 'aegisub'
        self.assert_repaired(self.repair())
        shutil.rmtree(self.build)

        result = self.repair()

        self.assert_repaired(result)
        self.run_tool(str(self.binary))
        origins = json.loads((self.macos.parent / 'SharedSupport' /
                              'dependency-origins.json').read_text())['images']
        recorded = next(item for item in origins if item['path'] == 'MacOS/' + dependency.name)
        self.assertEqual(recorded['source'], '@external/' + dependency.name)
        self.assertTrue(all(item['source'].startswith('@') for item in origins))
        self.assertNotIn(str(self.root), json.dumps(origins))

    def test_rewrites_system_rpath_before_removing_it(self) -> None:
        self.compile(self.binary, 'int main(void) { return 0; }')
        self.run_tool('install_name_tool', '-change', '/usr/lib/libSystem.B.dylib',
                      '@rpath/libSystem.B.dylib', '-add_rpath', '/usr/lib', str(self.binary))

        result = self.repair()

        self.assert_repaired(result)
        self.run_tool(str(self.binary))
        self.assertIn('/usr/lib/libSystem.B.dylib',
                      self.run_tool('otool', '-L', str(self.binary)).stdout)


if __name__ == '__main__':
    unittest.main()
