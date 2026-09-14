import json
import os
from pathlib import Path
import plistlib
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import unittest


AUDIT = Path(__file__).resolve().parents[2] / 'tools' / 'macos-arm64-audit.py'
MAC_TOOLS = ('clang', 'lipo', 'otool', 'install_name_tool', 'codesign')


@unittest.skipUnless(sys.platform == 'darwin' and all(shutil.which(tool) for tool in MAC_TOOLS),
                     'requires macOS and Xcode command line tools')
class AuditTests(unittest.TestCase):
    def __init__(self, methodName: str = 'runTest') -> None:
        super().__init__(methodName)
        self.root = self.app = self.macos = self.binary = Path()

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix='audit 한글 app ')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.app = self.root / 'Fixture.app'
        self.macos = self.app / 'Contents' / 'MacOS'
        self.macos.mkdir(parents=True)
        self.binary = self.macos / 'aegisub'
        with (self.app / 'Contents' / 'Info.plist').open('wb') as stream:
            plistlib.dump({'CFBundleExecutable': 'aegisub', 'CFBundlePackageType': 'APPL',
                          'CFBundleIdentifier': 'org.aegisub.audit-fixture',
                          'LSMinimumSystemVersion': '11.0'}, stream)
        self.compile(self.binary)

    def run_tool(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(args, check=True, capture_output=True, text=True, timeout=30)

    def compile(self, path: Path, *flags: str | Path, arch: str = 'arm64',
                source: str = 'int main(void) { return 0; }', minimum: str = '11.0') -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['clang', '-arch', arch, '-x', 'c', '-', '-x', 'none',
                        '-mmacosx-version-min=' + minimum,
                        '-Wl,-headerpad_max_install_names', '-o', str(path), *map(str, flags)],
                       input=source, check=True, capture_output=True, text=True, timeout=30)
        self.run_tool('codesign', '--force', '--sign', '-', str(path))

    def library(self, relative: str, install_name: str) -> Path:
        path = self.app / relative
        self.compile(path, '-dynamiclib', '-Wl,-install_name,' + install_name,
                     source='int value(void) { return 7; }')
        return path

    def sign(self) -> None:
        self.run_tool('codesign', '--force', '--sign', '-', str(self.app))

    def set_minimum(self, value: object) -> None:
        path = self.app / 'Contents' / 'Info.plist'
        with path.open('rb') as stream:
            metadata = plistlib.load(stream)
        if value is None:
            metadata.pop('LSMinimumSystemVersion', None)
        else:
            metadata['LSMinimumSystemVersion'] = value
        with path.open('wb') as stream:
            plistlib.dump(metadata, stream)

    def audit(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(AUDIT), str(self.app)],
                              capture_output=True, text=True, timeout=30)

    def assert_rejected(self, result: subprocess.CompletedProcess[str], code: str) -> None:
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['status'], 'failed')
        self.assertTrue(any(code in error for error in report['errors']), report['errors'])

    def test_accepts_relocated_app_with_recursive_rpaths_helpers_and_modules(self) -> None:
        # Given: a signed graph with an inherited rpath and an unlinked native module.
        leaf = self.library('Contents/Frameworks/lib leaf.dylib', '@rpath/lib leaf.dylib')
        top = self.macos / 'lib top.dylib'
        self.compile(top, '-dynamiclib', '-Wl,-install_name,@loader_path/lib top.dylib', leaf,
                     source='int value(void); int top(void) { return value(); }')
        self.compile(self.binary, top, '-Wl,-rpath,@executable_path/../Frameworks',
                     source='int top(void); int main(void) { return top() != 7; }')
        helper_dir = self.app / 'Contents' / 'Helpers'
        helper_lib = self.library('Contents/Helpers/lib helper.dylib',
                                  '@executable_path/lib helper.dylib')
        self.compile(helper_dir / 'restart-helper', helper_lib,
                     source='int value(void); int main(void) { return value() != 7; }')
        module = self.app / 'Contents' / 'SharedSupport' / 'automation' / 'native.so'
        self.compile(module, '-bundle', leaf,
                     source='int value(void); int module(void) { return value(); }')
        (leaf.parent / 'lib alias.dylib').symlink_to(leaf.name)
        self.sign()
        relocated = self.root / '이동한 app.app'
        self.app.rename(relocated)
        self.app = relocated
        # When: the CLI audits the relocated bundle twice.
        result = self.audit()
        repeated = self.audit()
        # Then: all six images pass and the report is deterministic.
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(len(report['mach_o']), 6)
        self.assertTrue(report['codesign_verified'])
        self.assertEqual(result.stdout, repeated.stdout)
        self.run_tool(str(self.app / 'Contents' / 'MacOS' / 'aegisub'))
        self.run_tool(str(self.app / 'Contents' / 'Helpers' / 'restart-helper'))

    def test_rejects_x86_helper(self) -> None:
        # Given: an otherwise signed ARM64 app contains an Intel helper.
        self.compile(self.app / 'Contents' / 'Helpers' / 'restart-helper', arch='x86_64')
        self.sign()
        # When: every nested image is audited.
        result = self.audit()
        # Then: the helper fails the architecture requirement.
        self.assert_rejected(result, 'not_thin_arm64')

    def test_rejects_universal_module(self) -> None:
        # Given: a native module contains both ARM64 and Intel slices.
        arm = self.root / 'arm.so'
        intel = self.root / 'intel.so'
        self.compile(arm, '-bundle')
        self.compile(intel, '-bundle', arch='x86_64')
        module = self.app / 'Contents' / 'Resources' / 'native.so'
        module.parent.mkdir()
        self.run_tool('lipo', '-create', str(arm), str(intel), '-output', str(module))
        self.sign()
        # When: the module is audited independently of its filename or executable bit.
        module.chmod(0o644)
        result = self.audit()
        # Then: a universal binary is rejected even though it has an ARM64 slice.
        self.assert_rejected(result, 'not_thin_arm64')

    def test_rejects_external_and_missing_dependencies(self) -> None:
        # Given: a valid internal dylib reference is replaced with a forbidden load path.
        lib = self.library('Contents/MacOS/lib value.dylib', '@loader_path/lib value.dylib')
        for name in ('/opt/homebrew/opt/lib/lib value.dylib',
                     '/usr/local/lib/lib value.dylib', str(self.root / 'build/lib value.dylib'),
                     '/usr/lib/../../opt/homebrew/lib value.dylib',
                     '@loader_path/missing.dylib', '@rpath/missing.dylib',
                     '@loader_path/../../../outside.dylib'):
            with self.subTest(name=name):
                self.compile(self.binary, lib,
                             source='int value(void); int main(void) { return value(); }')
                self.run_tool('install_name_tool', '-change', '@loader_path/lib value.dylib',
                              name, str(self.binary))
                self.sign()
                # When: the dependency graph is resolved.
                result = self.audit()
                # Then: it cannot pass with an external or missing dependency.
                self.assert_rejected(result, 'dependency')

    def test_rejects_external_and_escaping_rpaths_even_when_unused(self) -> None:
        # Given: no dependency needs the unsafe search path.
        for rpath in ('/opt/homebrew/lib', str(self.root / 'build'),
                      '@loader_path/../../../outside'):
            with self.subTest(rpath=rpath):
                self.compile(self.binary, '-Wl,-rpath,' + rpath)
                self.sign()
                # When: the load commands are audited.
                result = self.audit()
                # Then: unused rpaths cannot leak build-machine paths.
                self.assert_rejected(result, 'rpath')

    def test_rejects_external_install_name(self) -> None:
        # Given: an unlinked bundled library retains its build install name.
        self.library('Contents/MacOS/lib value.dylib', '/opt/homebrew/lib/lib value.dylib')
        self.sign()
        # When: all Mach-O files, including unlinked dylibs, are audited.
        result = self.audit()
        # Then: the absolute install ID is rejected.
        self.assert_rejected(result, 'install_name')

    def test_rejects_escaping_directory_and_file_symlinks(self) -> None:
        # Given: either a resource directory or file links outside the bundle.
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'data').write_text('fixture', encoding='utf-8')
        for target in (outside, outside / 'data'):
            with self.subTest(target=target):
                link = self.app / 'Contents' / 'escape'
                link.symlink_to(os.path.relpath(target, link.parent))
                # When: the tree is scanned without following external directories.
                result = self.audit()
                # Then: the symlink is rejected.
                self.assert_rejected(result, 'symlink')
                link.unlink()

    def test_rejects_broken_symlink(self) -> None:
        # Given: a resource symlink has no target.
        (self.app / 'Contents' / 'broken').symlink_to('missing')
        # When: the bundle is audited.
        result = self.audit()
        # Then: the broken link is reported.
        self.assert_rejected(result, 'symlink')

    def test_rejects_modified_signature(self) -> None:
        # Given: a sealed resource changes after signing.
        resource = self.app / 'Contents' / 'Resources' / 'data'
        resource.parent.mkdir()
        resource.write_text('before', encoding='utf-8')
        self.sign()
        resource.write_text('after', encoding='utf-8')
        # When: the CLI verifies the complete bundle signature.
        result = self.audit()
        # Then: strict codesign verification fails.
        self.assert_rejected(result, 'codesign')

    def test_rejects_single_slice_fat_module(self) -> None:
        payload = self.binary.read_bytes()
        module = self.app / 'Contents' / 'Resources' / 'single-fat.so'
        module.parent.mkdir()
        header = struct.pack('>IIiiIII', 0xcafebabe, 1, 0x0100000c, 0, 4096, len(payload), 12)
        module.write_bytes(header.ljust(4096, b'\0') + payload)
        self.assertEqual(self.run_tool('lipo', '-archs', str(module)).stdout.strip(), 'arm64')
        self.sign()

        result = self.audit()

        self.assert_rejected(result, 'not_thin_arm64')

    def test_helper_cannot_inherit_main_executable_directory(self) -> None:
        lib = self.library('Contents/MacOS/lib value.dylib', '@executable_path/lib value.dylib')
        self.compile(self.app / 'Contents' / 'Helpers' / 'helper', lib,
                     source='int value(void); int main(void) { return value(); }')
        self.sign()

        result = self.audit()

        self.assert_rejected(result, 'dependency_unresolved')

    def test_rejects_non_dictionary_info_plist_with_json_error(self) -> None:
        with (self.app / 'Contents' / 'Info.plist').open('wb') as stream:
            plistlib.dump(['invalid metadata'], stream)

        result = self.audit()

        self.assert_rejected(result, 'executable')

    def test_zip_preserves_modes_symlinks_and_signature(self) -> None:
        (self.macos / 'alias').symlink_to('aegisub')
        self.sign()
        original_mode = stat.S_IMODE(self.binary.stat().st_mode)
        archive = self.root / 'app.zip'
        extracted = self.root / 'extracted'

        self.run_tool('ditto', '-c', '-k', '--sequesterRsrc', '--keepParent',
                      str(self.app), str(archive))
        self.run_tool('ditto', '-x', '-k', str(archive), str(extracted))
        self.app = extracted / 'Fixture.app'
        result = self.audit()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        macos = self.app / 'Contents' / 'MacOS'
        self.assertEqual(stat.S_IMODE((macos / 'aegisub').stat().st_mode), original_mode)
        self.assertEqual(os.readlink(macos / 'alias'), 'aegisub')

    def test_accepts_system_rpath_root(self) -> None:
        self.compile(self.binary, '-Wl,-rpath,/usr/lib')
        self.sign()

        result = self.audit()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_minimum_os_report_compares_numeric_versions(self) -> None:
        self.set_minimum('12.10')
        self.compile(self.binary, minimum='12.9')
        self.compile(self.macos / 'native.so', '-bundle', minimum='12.10.0')
        self.sign()

        result = self.audit()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['minimum_os'], '12.10')
        self.assertEqual({image['path']: image['minimum_os'] for image in report['mach_o']},
                         {'Contents/MacOS/aegisub': '12.9', 'Contents/MacOS/native.so': '12.10'})

    def test_rejects_newer_minimum_for_every_image_kind(self) -> None:
        cases = (('Contents/MacOS/aegisub', ()),
                 ('Contents/Helpers/helper', ()),
                 ('Contents/Frameworks/lib.dylib',
                  ('-dynamiclib', '-Wl,-install_name,@rpath/lib.dylib')),
                 ('Contents/Resources/native.so', ('-bundle',)))
        for relative, flags in cases:
            with self.subTest(path=relative):
                path = self.app / relative
                self.compile(path, *flags, minimum='11.0.1')
                self.sign()

                result = self.audit()

                self.assert_rejected(result, 'minimum_os_exceeds_plist')
                report = json.loads(result.stdout)
                self.assertEqual(report['errors'],
                                 [f'minimum_os_exceeds_plist: {relative}: 11.0.1 > 11.0'])
                self.assertTrue(report['codesign_verified'])
                path.unlink()
                self.compile(self.binary)

    def test_rejects_missing_or_invalid_plist_minimum(self) -> None:
        for minimum in (None, '', '11.beta', '11.0.0.1', '0.0', 11):
            with self.subTest(minimum=minimum):
                self.set_minimum(minimum)
                self.sign()

                result = self.audit()

                self.assert_rejected(result, 'plist_minimum_os')
                self.assertTrue(json.loads(result.stdout)['codesign_verified'])

    def test_rejects_missing_macho_minimum(self) -> None:
        helper = self.app / 'Contents' / 'Helpers' / 'helper'
        self.compile(helper)
        self.run_tool('xcrun', 'vtool', '-remove-build-version', 'macos',
                      '-output', str(helper), str(helper))
        self.run_tool('codesign', '--force', '--sign', '-', str(helper))
        self.sign()

        result = self.audit()

        self.assert_rejected(result, 'minimum_os_missing_or_invalid')
        report = json.loads(result.stdout)
        self.assertTrue(report['codesign_verified'])
        self.assertEqual(report['errors'], ['minimum_os_missing_or_invalid: Contents/Helpers/helper'])
        image = next(image for image in report['mach_o'] if image['path'] == 'Contents/Helpers/helper')
        self.assertIsNone(image['minimum_os'])

    def test_checks_legacy_macos_minimum_command(self) -> None:
        module = self.macos / 'native.so'
        self.compile(module, '-bundle')
        self.set_minimum('11')
        for minimum, returncode in (('11.0', 0), ('11.0.1', 1)):
            with self.subTest(minimum=minimum):
                self.run_tool('xcrun', 'vtool', '-set-version-min', 'macos', minimum, '11.0',
                              '-replace', '-output', str(module), str(module))
                self.run_tool('codesign', '--force', '--sign', '-', str(module))
                self.sign()

                result = self.audit()

                self.assertEqual(result.returncode, returncode, result.stdout + result.stderr)
                report = json.loads(result.stdout)
                self.assertTrue(report['codesign_verified'])
                image = next(image for image in report['mach_o'] if image['path'].endswith('native.so'))
                self.assertEqual(image['minimum_os'], minimum)
                if returncode:
                    self.assert_rejected(result, 'minimum_os_exceeds_plist')


if __name__ == '__main__':
    unittest.main()
