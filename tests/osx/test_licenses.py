from pathlib import Path
import hashlib
import io
import json
import platform
import runpy
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.macos_homebrew_lock import validate_lock
from tools.macos_license_sources import (LicenseError, archive_notices, fetch,
                                        preserve_overrides, sha256)

TOOLS = Path(__file__).resolve().parents[2] / 'tools'
Collector = runpy.run_path(str(TOOLS / 'macos-copy-licenses.py'))['Collector']


class LicenseTests(unittest.TestCase):
    def test_requires_manifest_even_when_legacy_log_exists(self) -> None:
        with tempfile.TemporaryDirectory(prefix='고지 경로 ') as temporary:
            root = Path(temporary)
            app = root / 'Fixture.app'
            collector = Collector(root, app)
            binary = app / 'Contents/MacOS/libvalue.dylib'
            binary.parent.mkdir()
            binary.write_bytes(b'fixture')
            log = root / 'artifacts/logs/bundle-second.log'
            log.parent.mkdir(parents=True)
            log.write_text(f'Copied /Users/private/build/libvalue.dylib to {binary}\n')

            with self.assertRaises(LicenseError):
                collector.origins()

            self.assertFalse((collector.output / 'evidence').exists())

    def test_rejects_private_source_path_before_copying_manifest(self) -> None:
        with tempfile.TemporaryDirectory(prefix='고지 경로 ') as temporary:
            root = Path(temporary)
            app = root / 'Fixture.app'
            collector = Collector(root, app)
            binary = app / 'Contents/MacOS/aegisub'
            binary.parent.mkdir()
            binary.write_bytes(b'fixture')
            manifest = app / 'Contents/SharedSupport/dependency-origins.json'
            manifest.write_text(json.dumps({'schema': 1, 'images': [{
                'path': 'MacOS/aegisub', 'source': '/Users/private/build/aegisub',
                'bundled_sha256': sha256(binary)}]}))

            with self.assertRaises(LicenseError):
                collector.origins()

            self.assertFalse((collector.output / 'evidence').exists())

    @unittest.skipUnless(sys.platform == 'darwin' and shutil.which('clang'),
                         'requires macOS and Xcode command line tools')
    def test_consumes_manifest_generated_by_current_relocator(self) -> None:
        with tempfile.TemporaryDirectory(prefix='고지 MachO 경로 ') as temporary:
            root = Path(temporary).resolve()
            source = root / 'source tree'
            (source / 'tools').mkdir(parents=True)
            relocator = source / 'tools/osx-fix-libs.py'
            shutil.copyfile(TOOLS / 'osx-fix-libs.py', relocator)
            library = source / 'libvalue.dylib'
            app = root / 'Fixture.app'
            binary = app / 'Contents/MacOS/aegisub'
            binary.parent.mkdir(parents=True)
            subprocess.run(['clang', '-dynamiclib', '-x', 'c', '-', '-o', str(library),
                            '-Wl,-install_name,' + str(library)],
                           input='int value(void) { return 0; }', text=True,
                           check=True, capture_output=True, timeout=30)
            subprocess.run(['clang', '-x', 'c', '-', '-x', 'none', str(library),
                            '-Wl,-headerpad_max_install_names', '-o', str(binary)],
                           input='int value(void); int main(void) { return value(); }',
                           text=True, check=True, capture_output=True, timeout=30)
            subprocess.run([sys.executable, str(relocator), str(binary)],
                           check=True, capture_output=True, timeout=30)
            collector = Collector(source, app)

            origins = collector.origins()

            self.assertEqual(set(origins), {binary, library})
            manifest = app / 'Contents/SharedSupport/dependency-origins.json'
            evidence = collector.output / 'evidence/dependency-origins.json'
            self.assertEqual(evidence.read_bytes(), manifest.read_bytes())
            self.assertNotIn(str(root), evidence.read_text())

    def test_preserves_original_notices_and_embedded_jpeg_readme(self) -> None:
        with tempfile.TemporaryDirectory(prefix='고지 원문 ') as temporary:
            root = Path(temporary)
            source = root / 'source.tar.gz'
            notices = {'project/LICENCE': b'original copyright\n',
                       'project/nested/NOTICE': b'attribution\n',
                       'project/src/jpeg/README': b'JPEG terms\n',
                       'project/src/zlib/LICENSE': b'zlib terms\n'}
            with tarfile.open(source, 'w:gz') as archive:
                for name, data in {**notices, 'project/main.c': b'int main(void);'}.items():
                    member = tarfile.TarInfo(name)
                    member.size = len(data)
                    archive.addfile(member, io.BytesIO(data))

            count = archive_notices(source, root / 'notices')

            self.assertEqual(count, len(notices))
            for name, data in notices.items():
                self.assertEqual((root / 'notices' / name).read_bytes(), data)
            self.assertFalse((root / 'notices/project/main.c').exists())

    def test_rejects_archive_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source.tar.gz'
            with tarfile.open(source, 'w:gz') as archive:
                member = tarfile.TarInfo('../../LICENSE')
                member.size = 1
                archive.addfile(member, io.BytesIO(b'x'))

            with self.assertRaises(LicenseError):
                archive_notices(source, root / 'notices')

            self.assertFalse((root / 'LICENSE').exists())

    def test_fetch_verifies_source_checksum_and_rejects_corrupt_cache(self) -> None:
        with tempfile.TemporaryDirectory(prefix='source 해시 ') as temporary:
            root = Path(temporary)
            source = root / 'source.tar.gz'
            source.write_bytes(b'exact corresponding source')
            expected = hashlib.sha256(b'exact corresponding source').hexdigest()
            cached = fetch(root / 'cache', source.as_uri(), expected)
            self.assertEqual(sha256(cached), expected)
            cached.write_bytes(b'changed source')

            with self.assertRaises(LicenseError):
                fetch(root / 'cache', source.as_uri(), expected)

    def test_preserves_local_changes_against_zip_source(self) -> None:
        with tempfile.TemporaryDirectory(prefix='ZIP 소스 ') as temporary:
            root = Path(temporary)
            archive = root / 'source.zip'
            source = root / 'source'
            source.mkdir()
            (source / 'changed.c').write_bytes(b'local fix')
            (source / 'LICENSE').write_bytes(b'original terms')
            with zipfile.ZipFile(archive, 'w') as zipped:
                zipped.writestr('project/changed.c', b'upstream code')
                zipped.writestr('project/LICENSE', b'original terms')
                zipped.writestr('project/deleted.c', b'removed code')

            changes = preserve_overrides(archive, source, root / 'overrides')

            self.assertEqual(changes, ['changed.c', 'deleted:deleted.c'])
            self.assertEqual((root / 'overrides/changed.c').read_bytes(), b'local fix')
            self.assertFalse((root / 'overrides/LICENSE').exists())

    def test_lock_rejects_version_recipe_and_build_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix='brew 잠금 ') as temporary:
            prefix = Path(temporary)
            keg = prefix / 'Cellar/fixture/1.0'
            (keg / '.brew').mkdir(parents=True)
            (prefix / 'opt').mkdir()
            (prefix / 'opt/fixture').symlink_to(keg, target_is_directory=True)
            recipe = 'url "https://example.invalid/source.tar.gz"\nsha256 "' + 'a' * 64 + '"\n'
            (keg / '.brew/fixture.rb').write_text(recipe)
            receipt = {'arch': platform.machine(), 'source_modified_time': 1,
                       'source': {'tap': 'homebrew/core', 'tap_git_head': 'abc'},
                       'built_on': {'os_version': 'macOS 26'}, 'used_options': [],
                       'poured_from_bottle': True}
            receipt_path = keg / 'INSTALL_RECEIPT.json'
            receipt_path.write_text(json.dumps(receipt))
            expected = {'version': '1.0', 'arch': platform.machine(),
                        'formula_sha256': hashlib.sha256(recipe.encode()).hexdigest(),
                        'source': {'url': 'https://example.invalid/source.tar.gz', 'sha256': 'a' * 64},
                        'source_modified_time': 1, 'tap': 'homebrew/core', 'tap_git_head': 'abc',
                        'built_on': {'os_version': 'macOS 26'}, 'used_options': [],
                        'poured_from_bottle': True, 'runtime_dependencies': []}
            lock = {'architecture': platform.machine(), 'packages': {'fixture': expected}}
            validate_lock(lock, prefix)
            for field, value in (('version', '1.1'), ('formula_sha256', 'b' * 64),
                                 ('source_modified_time', 2),
                                 ('runtime_dependencies', [{'full_name': 'unexpected'}])):
                with self.subTest(field=field):
                    changed = {'architecture': platform.machine(),
                               'packages': {'fixture': {**expected, field: value}}}
                    with self.assertRaises(LicenseError):
                        validate_lock(changed, prefix)


if __name__ == '__main__':
    unittest.main()
