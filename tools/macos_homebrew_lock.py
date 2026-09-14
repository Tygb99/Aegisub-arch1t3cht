from __future__ import annotations

import argparse
from graphlib import TopologicalSorter
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.macos_license_sources import LicenseError, fetch, recipe_sources, sha256, write_json


DIRECT = ('libass', 'fftw', 'hunspell', 'uchardet', 'xxhash', 'portaudio',
          'icu4c@78', 'pkgconf', 'gettext')
REGISTRY_HEADERS = ('Authorization: Bearer QQ==',
                    'Accept: application/vnd.oci.image.index.v1+json')


def keg_for(path: Path) -> Path | None:
    return next((parent for parent in path.resolve().parents
                 if (parent / 'INSTALL_RECEIPT.json').is_file()), None)


def receipt_identity(keg: Path):
    receipt = json.loads((keg / 'INSTALL_RECEIPT.json').read_text())
    recipe = keg / '.brew' / (keg.parent.name + '.rb')
    return {'version': keg.name, 'arch': receipt['arch'],
            'formula_sha256': sha256(recipe), 'source': recipe_sources(recipe)[0],
            'source_modified_time': receipt.get('source_modified_time'),
            'tap': receipt['source'].get('tap'),
            'tap_git_head': receipt['source'].get('tap_git_head'),
            'built_on': receipt.get('built_on'), 'used_options': receipt['used_options'],
            'poured_from_bottle': receipt['poured_from_bottle'],
            'runtime_dependencies': receipt.get('runtime_dependencies', [])}


def installed_graph(prefix: Path, origins: list[Path]) -> dict[str, Path]:
    selected: dict[str, Path] = {}
    for origin in origins:
        keg = keg_for(origin)
        if keg is not None:
            name = keg.parent.name
            if name in selected and selected[name] != keg:
                raise LicenseError(f'Two linked Homebrew versions: {selected[name]} and {keg}')
            selected[name] = keg
    pending = list(DIRECT) + list(selected)
    visited: set[str] = set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        keg = selected.setdefault(name, (prefix / 'opt' / name).resolve())
        receipt = json.loads((keg / 'INSTALL_RECEIPT.json').read_text())
        pending.extend(dependency['full_name'].split('/')[-1]
                       for dependency in receipt.get('runtime_dependencies', []))
    return selected


def bottle_for(keg: Path, cache: Path):
    identity = receipt_identity(keg)
    receipt = json.loads((keg / 'INSTALL_RECEIPT.json').read_text())
    repository = 'https://ghcr.io/v2/homebrew/core/' + keg.parent.name.replace('@', '/')
    recipe_name = f'{keg.parent.name}/{keg.name}/.brew/{keg.parent.name}.rb'
    for rebuild in range(5):
        tag = keg.name + (f'-{rebuild}' if rebuild else '')
        index_url = repository + '/manifests/' + tag
        try:
            index_path = fetch(cache, index_url, headers=REGISTRY_HEADERS)
        except subprocess.CalledProcessError:
            continue
        index = json.loads(index_path.read_text())
        for manifest in index.get('manifests', []):
            annotations = manifest.get('annotations', {})
            tab = json.loads(annotations.get('sh.brew.tab', '{}'))
            if (tab.get('arch') != identity['arch']
                    or tab.get('source_modified_time') != identity['source_modified_time']
                    or tab.get('built_on', {}).get('os_version') !=
                    receipt.get('built_on', {}).get('os_version')):
                continue
            digest = annotations.get('sh.brew.bottle.digest')
            if not digest:
                continue
            bottle_url = repository + '/blobs/sha256:' + digest
            bottle = fetch(cache, bottle_url, digest, REGISTRY_HEADERS)
            with tarfile.open(bottle) as archive:
                try:
                    content = archive.extractfile(recipe_name)
                except KeyError:
                    continue
                if content is None:
                    continue
                with content:
                    if hashlib.sha256(content.read()).hexdigest() != identity['formula_sha256']:
                        continue
            return {'tag': annotations['org.opencontainers.image.ref.name'],
                    'url': bottle_url, 'sha256': digest, 'rebuild': rebuild,
                    'index_url': repository + '/manifests/sha256:' + sha256(index_path),
                    'index_sha256': sha256(index_path), 'manifest_digest': manifest['digest'],
                    'formula_url': index.get('annotations', {}).get('org.opencontainers.image.source'),
                    'tap_git_head': index.get('annotations', {}).get('org.opencontainers.image.revision'),
                    'recipe_verified_against_installed': True}
    raise LicenseError(f'Cannot match an immutable bottle to installed recipe: {keg}')


def create_lock(prefix: Path, origins: list[Path], cache: Path):
    selected = installed_graph(prefix, origins)
    def package(item: tuple[str, Path]):
        name, keg = item
        print(f'Locking Homebrew {name} {keg.name}', flush=True)
        return name, {**receipt_identity(keg), 'bottle': bottle_for(keg, cache),
                      'receipt_sha256': sha256(keg / 'INSTALL_RECEIPT.json')}
    with ThreadPoolExecutor(max_workers=4) as executor:
        packages = dict(executor.map(package, sorted(selected.items())))
    return {'schema': 1, 'architecture': platform.machine(), 'direct': list(DIRECT),
            'packages': packages,
            'policy': '버전 또는 recipe가 바뀌면 실패. 의도적인 재빌드·재검증 후 명시적으로 갱신.',
            'non_homebrew_build_tools': {'uv': subprocess.check_output(['uv', '--version'], text=True).strip()}}


def validate_lock(lock, prefix: Path, *, names: tuple[str, ...] | None = None) -> None:
    differences = []
    if platform.machine() != lock['architecture']:
        differences.append(f"architecture: {platform.machine()} != {lock['architecture']}")
    packages = lock['packages']
    pending = list(packages if names is None else names)
    checked: set[str] = set()
    while pending:
        name = pending.pop()
        if name in checked:
            continue
        checked.add(name)
        expected = packages[name]
        keg = (prefix / 'opt' / name).resolve()
        if not (keg / 'INSTALL_RECEIPT.json').is_file():
            differences.append(f'{name}: not installed')
            continue
        actual = receipt_identity(keg)
        for key, value in actual.items():
            # Homebrew FormulaInstaller.pour()는 설치 머신의 tap HEAD를 receipt에 다시 쓴다.
            # 이 값은 기록용이며, 고정 bottle/OCI/recipe의 해시 검증과는 별개다.
            if key == 'tap_git_head':
                continue
            locked = expected.get(key)
            if key == 'runtime_dependencies' and isinstance(value, list):
                # FormulaInstaller.finish()는 현재 formula 그래프로 목록을 재계산한다.
                # 필수 항목은 유지하고, 추가 항목도 전체 lock의 실제 keg를 검증해야 한다.
                actual_names = {item['full_name'] for item in value}
                required_names = {item['full_name'] for item in locked or []}
                missing = required_names - actual_names
                unknown = actual_names - packages.keys()
                if missing:
                    differences.append(f'{name}.runtime_dependencies: missing required {sorted(missing)}')
                if unknown:
                    differences.append(f'{name}.runtime_dependencies: not in lock {sorted(unknown)}')
                pending.extend(sorted(actual_names - required_names - unknown))
                continue
            if locked != value:
                differences.append(f'{name}.{key}: {value!r} != locked {locked!r}')
    if differences:
        raise LicenseError('Homebrew drift; do not regenerate the lock automatically:\n' +
                           '\n'.join(differences))


def restore_ci(lock, prefix: Path, cache: Path) -> None:
    if os.environ.get('CI') != 'true' or os.environ.get('GITHUB_ACTIONS') != 'true':
        raise LicenseError('--restore-ci requires CI=true and GITHUB_ACTIONS=true')
    if (sys.platform != 'darwin' or platform.machine() != 'arm64'
            or lock['architecture'] != 'arm64' or int(platform.mac_ver()[0].split('.')[0]) < 26):
        raise LicenseError('--restore-ci requires native ARM64 macOS 26 or later')
    if os.environ.get('HOMEBREW_FORBID_PACKAGES_FROM_PATHS'):
        raise LicenseError('Homebrew policy forbids installing local bottles')
    packages = lock['packages']
    graph = {name: {item['full_name'].split('/')[-1] for item in package['runtime_dependencies']}
             for name, package in packages.items()}
    if set().union(*graph.values()) - packages.keys():
        raise LicenseError('Homebrew lock is missing transitive dependencies')
    order = list(TopologicalSorter(graph).static_order())
    changed = []
    for name in order:
        try:
            validate_lock(lock, prefix, names=(name,))
        except LicenseError:
            changed.append(name)
    environment = {**os.environ, 'HOMEBREW_DEVELOPER': '1', **dict.fromkeys((
        'HOMEBREW_NO_AUTO_UPDATE', 'HOMEBREW_NO_INSTALL_CLEANUP',
        'HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK', 'HOMEBREW_NO_INSTALL_UPGRADE',
        'HOMEBREW_NO_AUTOREMOVE', 'HOMEBREW_NO_ANALYTICS', 'HOMEBREW_NO_ASK'), '1')}
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='restore-ci-', dir=cache) as temporary:
        bottles: dict[str, Path] = {}
        for name in changed:
            package = packages[name]
            bottle = package['bottle']
            if package['arch'] != 'arm64' or '.arm64_' not in bottle['tag']:
                raise LicenseError(f'Non-ARM64 bottle in lock: {name}')
            downloaded = fetch(cache, bottle['url'], bottle['sha256'], REGISTRY_HEADERS)
            with tarfile.open(downloaded) as archive:
                recipe = archive.extractfile(f'{name}/{package["version"]}/.brew/{name}.rb')
                if recipe is None:
                    raise LicenseError(f'Missing bottle recipe: {name}')
                with recipe:
                    if hashlib.sha256(recipe.read()).hexdigest() != package['formula_sha256']:
                        raise LicenseError(f'Bottle recipe differs from lock: {name}')
            index = fetch(cache, bottle['index_url'], bottle['index_sha256'], REGISTRY_HEADERS)
            manifests = json.loads(index.read_text())['manifests']
            annotations = next(item['annotations'] for item in manifests
                               if item['digest'] == bottle['manifest_digest'])
            if annotations['sh.brew.bottle.digest'] != bottle['sha256']:
                raise LicenseError(f'OCI bottle digest differs from lock: {name}')
            tab = json.loads(annotations['sh.brew.tab'])
            if any(tab.get(key) != package[key] for key in ('arch', 'built_on', 'source_modified_time')):
                raise LicenseError(f'OCI build receipt differs from lock: {name}')
            tag = bottle['tag'].split('.arm64_', 1)[1].split('.')[0]
            tag = 'arm64_' + tag
            local = Path(temporary) / f'{name}--{package["version"]}.{tag}.bottle.tar.gz'
            shutil.copyfile(downloaded, local)
            write_json(local.with_name(local.name.removesuffix('.tar.gz') + '.json'),
                       {name: {'bottle': {'tags': {tag: {'tab': tab}}}}})
            bottles[name] = local
        for name in changed:
            print(f'Restoring CI Homebrew {name} {packages[name]["version"]}', flush=True)
            if any((prefix / 'Cellar' / name).glob('*/INSTALL_RECEIPT.json')):
                subprocess.run(['brew', 'uninstall', '--formula', '--force',
                                '--ignore-dependencies', name], check=True, env=environment)
            subprocess.run(['brew', 'install', '--formula', '--force-bottle',
                            '--ignore-dependencies', '--skip-post-install', str(bottles[name])],
                           check=True, env=environment)
    validate_lock(lock, prefix)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', type=Path)
    mode.add_argument('--write', type=Path)
    mode.add_argument('--restore-ci', type=Path)
    parser.add_argument('--prefix', type=Path)
    parser.add_argument('--origins', type=Path)
    args = parser.parse_args()
    try:
        prefix = args.prefix or Path(subprocess.check_output(['brew', '--prefix'], text=True).strip())
        if args.check:
            validate_lock(json.loads(args.check.read_text()), prefix)
            print('Homebrew lock matches installed dependencies.')
        elif args.restore_ci:
            cache = args.restore_ci.resolve().parents[1] / '.deps' / 'license-sources'
            restore_ci(json.loads(args.restore_ci.read_text()), prefix, cache)
            print('CI Homebrew restore complete; lock matches installed dependencies.')
        else:
            origins = []
            if args.origins:
                if args.origins.suffix == '.json':
                    origins = [prefix / item['source'][len('@homebrew/'):]
                               if item['source'].startswith('@homebrew/') else Path(item['source'])
                               for item in json.loads(args.origins.read_text())['images']]
                else:
                    origins = [Path(match.group(1)) for line in args.origins.read_text().splitlines()
                               if (match := re.match(r'^Copied (.+) to .+$', line))]
            cache = args.write.resolve().parents[1] / '.deps' / 'license-sources'
            write_json(args.write, create_lock(prefix, origins, cache))
    except (LicenseError, OSError, subprocess.CalledProcessError, ValueError,
            KeyError, StopIteration, tarfile.TarError) as error:
        parser.exit(1, str(error) + '\n')
