from pathlib import Path
import hashlib
import io
import json
import os
import platform
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.macos_homebrew_lock import receipt_identity, restore_ci, validate_lock
from tools.macos_license_sources import LicenseError, sha256


@unittest.skipUnless(sys.platform == 'darwin' and platform.machine() == 'arm64',
                     'requires native ARM64 macOS')
class HomebrewRestoreTests(unittest.TestCase):
    def __init__(self, methodName: str = 'runTest') -> None:
        super().__init__(methodName)
        self.root = self.prefix = self.cache = self.log = Path()
        self.packages = {}
        self.lock = {'architecture': 'arm64', 'packages': self.packages}

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix='brew CI 복원 ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.prefix = self.root / 'prefix'
        self.cache = self.root / 'cache'
        self.log = self.root / 'commands.jsonl'
        executable = self.root / 'bin/brew'
        executable.parent.mkdir()
        executable.write_text(f'#!{sys.executable}\n' + '''
import json, os, pathlib, shutil, sys, tarfile
prefix = pathlib.Path(os.environ['FIXTURE_PREFIX'])
args = sys.argv[1:]
assert prefix.is_relative_to(pathlib.Path(os.environ['FIXTURE_ROOT']))
with open(os.environ['FIXTURE_LOG'], 'a') as stream:
    stream.write(json.dumps({'args': args, 'env': {k: v for k, v in os.environ.items()
                        if k.startswith('HOMEBREW_')}}) + '\\n')
if args[0] == 'uninstall':
    name = args[-1]
    shutil.rmtree(prefix / 'Cellar' / name)
    (prefix / 'opt' / name).unlink(missing_ok=True)
elif args[0] == 'install':
    bottle = pathlib.Path(args[-1])
    sidecar = bottle.with_name(bottle.name.removesuffix('.tar.gz') + '.json')
    metadata = json.loads(sidecar.read_text())
    name = next(iter(metadata))
    tab = next(iter(metadata[name]['bottle']['tags'].values()))['tab']
    for dependency in tab['runtime_dependencies']:
        assert (prefix / 'opt' / dependency['full_name']).is_dir()
    with tarfile.open(bottle) as archive:
        keg = prefix / 'Cellar' / '/'.join(archive.getnames()[0].split('/')[:2])
        archive.extractall(prefix / 'Cellar', filter='data')
    tab['poured_from_bottle'] = True
    if os.environ.get('FIXTURE_DRIFT'):
        tab['source_modified_time'] += 1
    for dependency in tab['runtime_dependencies']:
        dependency['version'] = 'latest-formula-metadata'
    (keg / 'INSTALL_RECEIPT.json').write_text(json.dumps(tab))
    (prefix / 'opt').mkdir(exist_ok=True)
    (prefix / 'opt' / name).symlink_to(keg)
else:
    raise RuntimeError(args)
''')
        executable.chmod(0o755)
        environment = {'PATH': str(executable.parent) + os.pathsep + os.environ['PATH'],
                       'CI': 'true', 'GITHUB_ACTIONS': 'true',
                       'FIXTURE_PREFIX': str(self.prefix), 'FIXTURE_ROOT': str(self.root),
                       'FIXTURE_LOG': str(self.log)}
        patcher = patch.dict(os.environ, environment)
        patcher.start()
        self.addCleanup(patcher.stop)

    def bottle(self, name: str, dependencies: tuple[str, ...] = ()) -> None:
        recipe = ('url "https://example.invalid/source.tar.gz"\nsha256 "' + 'a' * 64 + '"\n').encode()
        receipt = {'arch': 'arm64', 'source_modified_time': 1, 'used_options': [],
                   'source': {'tap': 'homebrew/core', 'tap_git_head': None},
                   'built_on': {'os_version': 'macOS 26'}, 'poured_from_bottle': True,
                   'runtime_dependencies': [{'full_name': dep, 'version': '1.0'} for dep in dependencies]}
        archive_path = self.root / (name + '.tar.gz')
        with tarfile.open(archive_path, 'w:gz') as archive:
            member = tarfile.TarInfo(f'{name}/1.0/.brew/{name}.rb')
            member.size = len(recipe)
            archive.addfile(member, io.BytesIO(recipe))
        digest = sha256(archive_path)
        manifest_digest = 'sha256:' + 'b' * 64
        index = self.root / (name + '.json')
        index.write_text(json.dumps({'manifests': [{
            'digest': manifest_digest, 'annotations': {'sh.brew.bottle.digest': digest,
                                                       'sh.brew.tab': json.dumps(receipt)}}]}))
        self.packages[name] = {
            **receipt, 'source': {'url': 'https://example.invalid/source.tar.gz', 'sha256': 'a' * 64},
            'tap': 'homebrew/core', 'tap_git_head': None, 'version': '1.0',
            'formula_sha256': hashlib.sha256(recipe).hexdigest(),
            'bottle': {'tag': '1.0.arm64_tahoe', 'url': archive_path.as_uri(), 'sha256': digest,
                       'index_url': index.as_uri(), 'index_sha256': sha256(index),
                       'manifest_digest': manifest_digest}}

    def installed(self, name: str, version: str) -> Path:
        keg = self.prefix / 'Cellar' / name / version
        (keg / '.brew').mkdir(parents=True)
        with tarfile.open(self.root / (name + '.tar.gz')) as archive:
            recipe = archive.extractfile(f'{name}/1.0/.brew/{name}.rb')
            assert recipe is not None
            (keg / '.brew' / (name + '.rb')).write_bytes(recipe.read())
        package = self.packages[name]
        receipt = {**package, 'source': {'tap': 'homebrew/core', 'tap_git_head': None}}
        (keg / 'INSTALL_RECEIPT.json').write_text(json.dumps(receipt))
        (self.prefix / 'opt').mkdir(exist_ok=True)
        (self.prefix / 'opt' / name).symlink_to(keg)
        return keg

    def test_refuses_without_both_ci_guards_before_any_brew_command(self) -> None:
        for ci, actions in (('', ''), ('true', ''), ('', 'true'), ('false', 'true')):
            with self.subTest(ci=ci, actions=actions), patch.dict(os.environ, CI=ci, GITHUB_ACTIONS=actions):
                with self.assertRaises(LicenseError):
                    restore_ci(self.lock, self.prefix, self.cache)
        self.assertFalse(self.log.exists())
        self.assertFalse(self.cache.exists())

    def test_restores_dependency_order_and_only_changes_mismatched_locked_formulae(self) -> None:
        self.bottle('consumer', ('base',))
        self.bottle('base')
        self.bottle('keep')
        self.installed('base', '2.0')
        kept = self.installed('keep', '1.0') / 'INSTALL_RECEIPT.json'
        kept_bytes = kept.read_bytes()
        unrelated = self.prefix / 'Cellar/unrelated/3.0/marker'
        unrelated.parent.mkdir(parents=True)
        unrelated.write_text('untouched')

        restore_ci(self.lock, self.prefix, self.cache)

        validate_lock(self.lock, self.prefix)
        commands = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertEqual([item['args'][0] for item in commands], ['uninstall', 'install', 'install'])
        self.assertEqual(commands[0]['args'][-1], 'base')
        self.assertIn('base--1.0.arm64_tahoe.bottle.tar.gz', commands[1]['args'][-1])
        self.assertIn('consumer--1.0.arm64_tahoe.bottle.tar.gz', commands[2]['args'][-1])
        for command in commands:
            self.assertIn('--ignore-dependencies', command['args'])
            self.assertEqual(command['env']['HOMEBREW_DEVELOPER'], '1')
            for key in ('HOMEBREW_NO_AUTO_UPDATE', 'HOMEBREW_NO_INSTALL_CLEANUP',
                        'HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK', 'HOMEBREW_NO_AUTOREMOVE'):
                self.assertEqual(command['env'][key], '1')
        self.assertEqual(kept.read_bytes(), kept_bytes)
        self.assertEqual(unrelated.read_text(), 'untouched')
        self.assertFalse((self.prefix / 'Cellar/base/2.0').exists())

    def test_bad_download_fails_before_uninstalling_anything(self) -> None:
        self.bottle('consumer', ('base',))
        self.bottle('base')
        old = self.installed('base', '2.0')
        (self.root / 'consumer.tar.gz').write_bytes(b'corrupt bottle')

        with self.assertRaises(LicenseError):
            restore_ci(self.lock, self.prefix, self.cache)

        self.assertTrue(old.exists())
        self.assertFalse(self.log.exists())

    def test_final_check_rejects_installation_drift(self) -> None:
        self.bottle('base')
        with patch.dict(os.environ, FIXTURE_DRIFT='1'):
            with self.assertRaises(LicenseError):
                restore_ci(self.lock, self.prefix, self.cache)
        self.assertTrue(self.log.is_file())

    def test_bad_oci_index_fails_before_uninstalling_anything(self) -> None:
        self.bottle('base')
        old = self.installed('base', '2.0')
        (self.root / 'base.json').write_text('{}')

        with self.assertRaises(LicenseError):
            restore_ci(self.lock, self.prefix, self.cache)

        self.assertTrue(old.exists())
        self.assertFalse(self.log.exists())

    def test_installation_tap_head_is_preserved_without_affecting_identity(self) -> None:
        self.bottle('base')
        keg = self.installed('base', '1.0')
        path = keg / 'INSTALL_RECEIPT.json'
        receipt = json.loads(path.read_text())
        receipt['source']['tap_git_head'] = '3cc40d0f3a316ece2c58491a8cc237490699ce03'
        path.write_text(json.dumps(receipt))
        before = path.read_bytes()

        validate_lock(self.lock, self.prefix)

        self.assertEqual(receipt_identity(keg)['tap_git_head'], receipt['source']['tap_git_head'])
        self.assertEqual(path.read_bytes(), before)
        self.assertIsNone(self.packages['base']['tap_git_head'])

    def test_locked_extra_dependency_does_not_trigger_subset_reinstallation(self) -> None:
        self.bottle('consumer', ('base',))
        self.bottle('base')
        self.bottle('extra')
        keg = self.installed('consumer', '1.0')
        self.installed('base', '1.0')
        self.installed('extra', '1.0')
        path = keg / 'INSTALL_RECEIPT.json'
        receipt = json.loads(path.read_text())
        receipt['runtime_dependencies'].append({'full_name': 'extra', 'version': 'latest-formula'})
        path.write_text(json.dumps(receipt))
        before = path.read_bytes()

        restore_ci(self.lock, self.prefix, self.cache)

        validate_lock(self.lock, self.prefix)
        self.assertFalse(self.log.exists())
        self.assertEqual(path.read_bytes(), before)

    def test_rejects_missing_required_runtime_dependency(self) -> None:
        self.bottle('consumer', ('base',))
        self.bottle('base')
        keg = self.installed('consumer', '1.0')
        self.installed('base', '1.0')
        path = keg / 'INSTALL_RECEIPT.json'
        receipt = json.loads(path.read_text())
        receipt['runtime_dependencies'] = []
        path.write_text(json.dumps(receipt))

        with self.assertRaisesRegex(LicenseError, 'base'):
            validate_lock(self.lock, self.prefix)

    def test_rejects_extra_dependency_outside_lock_even_when_installed(self) -> None:
        self.bottle('consumer')
        self.bottle('unknown')
        keg = self.installed('consumer', '1.0')
        self.installed('unknown', '1.0')
        del self.packages['unknown']
        path = keg / 'INSTALL_RECEIPT.json'
        receipt = json.loads(path.read_text())
        receipt['runtime_dependencies'] = [{'full_name': 'unknown', 'version': '1.0'}]
        path.write_text(json.dumps(receipt))

        with self.assertRaisesRegex(LicenseError, 'unknown'):
            validate_lock(self.lock, self.prefix)

    def test_subset_checks_actual_version_of_locked_extra_dependency(self) -> None:
        self.bottle('consumer')
        self.bottle('extra')
        keg = self.installed('consumer', '1.0')
        self.installed('extra', '2.0')
        path = keg / 'INSTALL_RECEIPT.json'
        receipt = json.loads(path.read_text())
        receipt['runtime_dependencies'] = [{'full_name': 'extra', 'version': '1.0'}]
        path.write_text(json.dumps(receipt))

        with self.assertRaisesRegex(LicenseError, 'extra.version'):
            validate_lock(self.lock, self.prefix, names=('consumer',))

    def test_subset_rejects_uninstalled_locked_extra_dependency(self) -> None:
        self.bottle('consumer')
        self.bottle('extra')
        keg = self.installed('consumer', '1.0')
        path = keg / 'INSTALL_RECEIPT.json'
        receipt = json.loads(path.read_text())
        receipt['runtime_dependencies'] = [{'full_name': 'extra', 'version': '1.0'}]
        path.write_text(json.dumps(receipt))

        with self.assertRaisesRegex(LicenseError, 'extra: not installed'):
            validate_lock(self.lock, self.prefix, names=('consumer',))


if __name__ == '__main__':
    unittest.main()
