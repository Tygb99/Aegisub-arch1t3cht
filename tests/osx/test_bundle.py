from pathlib import Path
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[2] / 'tools'


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('meson'),
                     'requires macOS and Meson on PATH')
class BundleScriptTests(unittest.TestCase):
    def test_installs_only_main_project_and_signs_updated_metadata(self) -> None:
        # Given: a headless Meson fixture with obsolete plist values and an installable subproject.
        with tempfile.TemporaryDirectory(prefix='bundle 설치 공간 ') as temporary:
            root = Path(temporary).resolve()
            source = root / 'source tree'
            build = root / 'build tree'
            contents = source / 'packages' / 'osx_bundle' / 'Contents'
            resources = contents / 'Resources'
            resources.mkdir(parents=True)
            (resources / 'fixture.icns').write_bytes(b'icns')
            (source / 'po').mkdir()
            (source / 'po' / 'ko.po').touch()
            (source / 'tools').mkdir()
            shutil.copyfile(TOOLS / 'osx-fix-libs.py', source / 'tools' / 'osx-fix-libs.py')
            (source / 'tools' / 'macos-copy-licenses.sh').write_text(
                'test -d "$1/tools" || exit 1\n'
                'printf license > "$2/Contents/SharedSupport/fixture-license.txt"\n',
                encoding='utf-8')
            dictionaries = root / 'local dictionaries'
            dictionaries.mkdir()
            (dictionaries / 'en_US.aff').write_text('SET UTF-8\n', encoding='utf-8')
            (dictionaries / 'en_US.dic').write_text('0\n', encoding='utf-8')
            library_source = root / 'fixture.c'
            library_source.write_text('int fixture(void) { return 0; }\n', encoding='utf-8')
            library = root / 'libfixture.dylib'
            subprocess.run(['clang', '-dynamiclib', str(library_source), '-o', str(library)],
                           check=True, capture_output=True, text=True, timeout=30)
            # Intel dependencies may have no signature; exercise that case on either architecture.
            subprocess.run(['codesign', '--remove-signature', str(library)],
                           check=True, capture_output=True, text=True, timeout=30)
            (source / 'main.c').write_text(
                'int fixture(void); int main(void) { return fixture(); }\n', encoding='utf-8')
            (source / 'meson.build').write_text(
                "project('bundle-fixture', 'c')\n"
                "executable('aegisub', 'main.c', install: true, "
                "c_args: ['-mmacosx-version-min=26.0'], "
                f"link_args: ['-mmacosx-version-min=26.0', '{library}'])\n"
                "subproject('excluded')\n", encoding='utf-8')
            subproject = source / 'subprojects' / 'excluded'
            subproject.mkdir(parents=True)
            marker = root / 'excluded install'
            (subproject / 'marker').touch()
            (subproject / 'meson.build').write_text(
                "project('excluded')\n"
                f"install_data('marker', install_dir: '{marker}')\n", encoding='utf-8')
            app = build / 'Aegisub.app'
            env = os.environ.copy()
            env['AEGISUB_BUNDLE_SIGNATURE'] = '-'
            env['CC'] = 'clang'
            subprocess.run(['meson', 'setup', str(build), str(source),
                            '--prefix', str(app / 'Contents'), '--bindir', 'MacOS'],
                           check=True, capture_output=True, text=True, env=env, timeout=60)
            (build / 'osx-bundle.sed').touch()
            template = {
                'CFBundleExecutable': 'aegisub',
                'CFBundleIdentifier': 'org.aegisub.bundle-fixture',
                'CFBundleName': 'Fixture',
                'CFBundlePackageType': 'APPL',
                'CFBundleVersion': '1',
            }
            for obsolete_keys, collect_licenses in ((True, False), (False, True)):
                with self.subTest(obsolete_keys=obsolete_keys, collect_licenses=collect_licenses):
                    metadata: dict[str, str | list[str]] = dict(template)
                    if obsolete_keys:
                        metadata['LSArchitecturePriority'] = ['i386', 'x86_64']
                        metadata['LSMinimumSystemVersion'] = '10.6'
                    (contents / 'Info.plist').write_bytes(plistlib.dumps(metadata))

                    # When: only this temporary fixture goes through the bundle script.
                    result = subprocess.run(['sh', str(TOOLS / 'osx-bundle.sh'),
                                             str(source), str(build), '', '',
                                             str(dictionaries), 'TRUE',
                                             'TRUE' if collect_licenses else 'FALSE'],
                                            capture_output=True, text=True, env=env, timeout=60)

                    # Then: metadata matches the binary, subprojects stay uninstalled and the seal verifies.
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    binary = app / 'Contents' / 'MacOS' / 'aegisub'
                    archs = subprocess.check_output(['lipo', '-archs', str(binary)], text=True).split()
                    actual = plistlib.loads((app / 'Contents' / 'Info.plist').read_bytes())
                    self.assertEqual(actual['LSArchitecturePriority'], archs)
                    self.assertEqual(actual['LSMinimumSystemVersion'], '26.0')
                    self.assertFalse(marker.exists())
                    origins = json.loads((app / 'Contents/SharedSupport' /
                                          'dependency-origins.json').read_text())
                    self.assertEqual(origins['phase'],
                                     'after-relocation-and-individual-signing-before-app-seal')
                    main = next(item for item in origins['images'] if item['path'] == 'MacOS/aegisub')
                    self.assertNotEqual(main['bundled_sha256'], hashlib.sha256(binary.read_bytes()).hexdigest())
                    license_file = app / 'Contents/SharedSupport/fixture-license.txt'
                    if collect_licenses:
                        self.assertEqual(license_file.read_text(), 'license')
                    else:
                        self.assertFalse(license_file.exists())
                    self.assertEqual((app / 'Contents' / 'SharedSupport' / 'dictionaries' /
                                      'en_US.aff').read_text(encoding='utf-8'), 'SET UTF-8\n')
                    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)],
                                   check=True, capture_output=True, text=True, timeout=30)
                    subprocess.run([str(binary)], check=True, timeout=30)


if __name__ == '__main__':
    unittest.main()
