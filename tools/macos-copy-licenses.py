#!/usr/bin/env python3
from __future__ import annotations

import configparser
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.macos_homebrew_lock import keg_for, validate_lock
from tools.macos_license_sources import (LicenseError, archive_notices, copy_notices, fetch,
                                   git_snapshot, preserve_overrides, recipe_sources,
                                   sha256, write_json)


DICTIONARY_REVISION = '6d792f04521b3ac8823c8e8972fcfd757342da4d'
LOCAL_SOURCES = {
    'ffmpeg': ('ffmpeg-7.1.2', 'https://ffmpeg.org/releases/ffmpeg-7.1.2.tar.xz',
               '089bc60fb59d6aecc5d994ff530fd0dcb3ee39aa55867849a2bbc4e555f9c304'),
    'wx': ('wxWidgets-3.2.9',
           'https://github.com/wxWidgets/wxWidgets/releases/download/v3.2.9/wxWidgets-3.2.9.tar.bz2',
           'fb90f9538bffd6a02edbf80037a0c14c2baf9f509feac8f76ab2a5e4321f112b'),
}


class Collector:
    def __init__(self, source: Path, app: Path) -> None:
        self.source = source.resolve()
        self.app = app.resolve()
        self.build = Path(os.environ.get('AEGISUB_BUILD_DIR', str(self.app.parent))).resolve()
        self.cache = self.source / '.deps' / 'license-sources'
        self.output = self.app / 'Contents' / 'SharedSupport' / 'licenses'
        self.output.mkdir(parents=True, exist_ok=True)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d-%H-%M-%S')
        self.components = []
        self.archives: dict[str, Path] = {}

    def copy(self, source: Path, destination: Path) -> None:
        target = self.output / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    def archive(self, path: Path) -> str:
        name = sha256(path)[:16] + '-' + path.name
        self.archives[name] = path
        return 'sources/' + name

    def origins(self) -> list[Path]:
        manifest = self.app / 'Contents' / 'SharedSupport' / 'dependency-origins.json'
        if not manifest.is_file():
            raise LicenseError('Missing dependency-origins.json; run osx-fix-libs.py before license collection')
        data = json.loads(manifest.read_text())
        origins = []
        for item in data['images']:
            binary = self.app / 'Contents' / item['path']
            if sha256(binary) != item['bundled_sha256']:
                raise LicenseError(f'Bundle changed after dependency discovery: {binary}')
            name = item['source']
            if name.startswith('@source/'):
                path = self.source / name[len('@source/'):]
            elif name.startswith('@bundle/'):
                path = self.app / 'Contents' / name[len('@bundle/'):]
            elif name.startswith('@homebrew/'):
                prefix = subprocess.check_output(['brew', '--prefix'], text=True).strip()
                path = Path(prefix) / name[len('@homebrew/'):]
            elif name.startswith('@external/'):
                raise LicenseError(f'Unknown external source; place it under the source tree: {name}')
            else:
                raise LicenseError('Non-portable dependency origin; regenerate with osx-fix-libs.py')
            origins.append(path)
        self.copy(manifest, Path('evidence/dependency-origins.json'))
        return origins

    def homebrew(self, origins: list[Path]) -> None:
        kegs = sorted({keg for path in origins if (keg := keg_for(path)) is not None})
        if not kegs:
            return
        lock_path = self.source / 'tools' / 'macos-homebrew-lock.json'
        lock = json.loads(lock_path.read_text())
        prefix = kegs[0].parents[2]
        validate_lock(lock, prefix)
        self.copy(lock_path, Path('homebrew-lock.json'))
        for name, package in lock['packages'].items():
            keg = prefix / 'Cellar' / name / package['version']
            for path in (keg / 'INSTALL_RECEIPT.json', keg / '.brew' / (name + '.rb')):
                self.copy(path, Path('evidence/Homebrew') / name / path.name)
        for keg in kegs:
            name = keg.parent.name
            package = lock['packages'].get(name)
            if package is None or keg != prefix / 'Cellar' / name / package['version']:
                raise LicenseError(f'Linked Homebrew keg is outside the lock: {keg}')
            print(f'Collecting Homebrew notices: {name} {keg.name}', flush=True)
            recipe = keg / '.brew' / (name + '.rb')
            downloads = recipe_sources(recipe)
            for index, item in enumerate(downloads):
                urls = [item['url']]
                if index == 0:
                    urls.extend(re.findall(r'^\s*mirror "(https://[^"]+)"', recipe.read_text(), re.M))
                for url in urls:
                    try:
                        downloaded = fetch(self.cache, url, item['sha256'])
                        item['download_url'] = url
                        break
                    except subprocess.CalledProcessError:
                        if url == urls[-1]:
                            raise
                        print(f'Trying recorded source mirror for {name}', flush=True)
                else:
                    raise LicenseError(f'No usable source URL for {name}')
                item['archive'] = self.archive(downloaded)
                if index == 0:
                    count = archive_notices(downloaded, self.output / 'Homebrew' / name / 'source')
                    if not count:
                        raise LicenseError(f'No original notices found in {item["url"]}')
            copy_notices(keg, self.output / 'Homebrew' / name / 'installed')
            self.components.append({'name': name, 'version': keg.name, 'scope': 'linked-Homebrew',
                                    'sources': downloads, 'lock': lock['packages'][name]})

    def git_component(self, directory: Path, name: str, scope: str) -> None:
        archive = self.cache / (self.timestamp + '-' + name + '.tar.gz')
        record = git_snapshot(directory, archive)
        record.update(name=name, scope=scope, archive=self.archive(archive))
        self.components.append(record)
        modules = directory / '.gitmodules'
        if modules.is_file():
            config = configparser.ConfigParser()
            config.read(modules)
            for section in config.sections():
                subpath = directory / config[section]['path']
                self.git_component(subpath, name + '-' + subpath.name, 'git-submodule')

    def project(self) -> None:
        for name in ('LICENCE', 'LICENSE', 'COPYING', 'NOTICE'):
            if (self.source / name).is_file():
                self.copy(self.source / name, Path('Aegisub') / name)
        for name in ('src', 'libaegisub', 'include', 'automation', 'vendor'):
            if (self.source / name).is_dir():
                copy_notices(self.source / name, self.output / 'Aegisub' / name)
        self.git_component(self.source, 'Aegisub', 'application-source-snapshot')
        info = self.build / 'meson-info'
        for path in info.glob('intro-*.json'):
            if path.name in ('intro-projectinfo.json', 'intro-buildoptions.json',
                             'intro-dependencies.json', 'intro-compilers.json', 'intro-targets.json'):
                self.copy(path, Path('evidence/Meson') / path.name)
        build_script = self.source / 'tools' / 'macos-arm64-build.sh'
        if build_script.is_file():
            self.copy(build_script, Path('evidence/macos-arm64-build.sh'))
        project_info = json.loads((info / 'intro-projectinfo.json').read_text())
        versions = {item['name']: item['version'] for item in project_info.get('subprojects', [])}
        for wrap in sorted((self.source / 'subprojects').glob('*.wrap')):
            config = configparser.ConfigParser(interpolation=None)
            config.read(wrap)
            section = next(name for name in config.sections() if name.startswith('wrap-'))
            settings = config[section]
            directory = self.source / 'subprojects' / settings.get('directory', wrap.stem)
            if not directory.is_dir():
                continue
            name = wrap.stem
            notices = self.output / 'subprojects' / name
            copy_notices(directory, notices)
            self.copy(wrap, Path('evidence/wraps') / wrap.name)
            if section == 'wrap-git':
                self.git_component(directory, name, 'meson-subproject')
            else:
                url, expected = settings['source_url'], settings['source_hash']
                archive = self.source / 'subprojects' / 'packagecache' / settings['source_filename']
                if not archive.is_file():
                    archive = fetch(self.cache, url, expected)
                if sha256(archive) != expected:
                    raise LicenseError(f'Source checksum mismatch: {archive}')
                overrides = self.output / 'evidence' / 'overrides' / name
                changed = preserve_overrides(archive, directory, overrides)
                patches = []
                if 'patch_url' in settings:
                    patch = self.source / 'subprojects/packagecache' / settings['patch_filename']
                    if not patch.is_file():
                        patch = fetch(self.cache, settings['patch_url'], settings['patch_hash'])
                    if sha256(patch) != settings['patch_hash']:
                        raise LicenseError(f'Patch checksum mismatch: {patch}')
                    patches.append({'url': settings['patch_url'], 'sha256': settings['patch_hash'],
                                    'archive': self.archive(patch)})
                self.components.append({'name': name, 'version': versions.get(name),
                                        'scope': 'meson-subproject', 'url': url, 'sha256': expected,
                                        'archive': self.archive(archive), 'overrides': changed,
                                        'patches': patches})
        for name in ('iconv', 'csri', 'packagefiles'):
            directory = self.source / 'subprojects' / name
            if directory.is_dir():
                copy_notices(directory, self.output / 'subprojects' / name)

    def local(self) -> None:
        for name, (directory_name, url, expected) in LOCAL_SOURCES.items():
            directory = self.source / '.deps' / 'src' / directory_name
            if not directory.is_dir():
                raise LicenseError(f'Missing local dependency source: {directory}')
            archive = directory.parent / url.rsplit('/', 1)[1]
            if not archive.is_file():
                archive = fetch(self.cache, url, expected)
            if sha256(archive) != expected:
                raise LicenseError(f'Source checksum mismatch: {archive}')
            copy_notices(directory, self.output / directory_name)
            evidence = self.output / 'evidence' / directory_name
            changed = preserve_overrides(archive, directory, evidence / 'overrides')
            configuration = {}
            if name == 'ffmpeg':
                config = (directory / 'config.h').read_text()
                license_name = re.search(r'#define FFMPEG_LICENSE "([^"]+)"', config)
                if not license_name:
                    raise LicenseError('Missing FFmpeg license configuration')
                for flag in ('GPL', 'NONFREE', 'VERSION3'):
                    if not re.search(rf'^#define CONFIG_{flag} 0$', config, re.M):
                        raise LicenseError(f'FFmpeg LGPL 2.1 configuration changed: CONFIG_{flag}')
                configuration['license'] = license_name.group(1)
                for relative in ('config.h', 'config_components.h', 'ffbuild/config.mak', 'ffbuild/config.log'):
                    self.copy(directory / relative, Path('evidence') / directory_name / relative)
            else:
                for relative in ('config.log', 'config.status'):
                    self.copy(directory.parent / 'wx-build' / relative,
                              Path('evidence') / directory_name / relative)
                configuration['wx_config'] = subprocess.check_output(
                    [str(self.source / '.deps/wx/bin/wx-config'), '--version', '--selected-config', '--libs'], text=True)
            self.components.append({'name': name, 'version': directory_name, 'url': url,
                                    'sha256': expected, 'archive': self.archive(archive),
                                    'configuration': configuration, 'overrides': changed})

    def dictionary(self) -> None:
        url = ('https://raw.githubusercontent.com/TypesettingTools/Aegisub-dictionaries/' +
               DICTIONARY_REVISION + '/dicts/README_en_US.txt')
        readme = fetch(self.cache, url)
        self.copy(readme, Path('dictionaries/README_en_US.txt'))
        self.components.append({'name': 'en_US dictionary', 'revision': DICTIONARY_REVISION,
                                'notice_url': url, 'notice_sha256': sha256(readme)})

    def finish(self) -> None:
        companion = self.app.parent / (self.timestamp + '-Aegisub-corresponding-sources.tar')
        source_manifest = {'schema': 1, 'components': self.components,
                           'corresponding_sources_file': companion.name}
        write_json(self.output / 'sources.json', source_manifest)
        with tarfile.open(companion, 'w') as archive:
            for name, path in sorted(self.archives.items()):
                archive.add(path, arcname='sources/' + name, recursive=False)
            archive.add(self.output, arcname='notices-and-build-evidence')
        source_manifest['corresponding_sources_sha256'] = sha256(companion)
        write_json(self.output / 'sources.json', source_manifest)
        for pattern in ('*-제삼자-고지.ko.md', '*-third-party-notices.ko.md'):
            for previous in self.output.glob(pattern):
                previous.unlink()
        (self.output / (self.timestamp + '-third-party-notices.ko.md')).write_text(
            '# 제삼자 소프트웨어 고지와 대응 소스\n\n'
            '원본 LICENSE·COPYING·NOTICE와 저작권 고지를 하위 디렉터리에 원문 그대로 보존했습니다. '
            'sources.json은 실제 구성요소의 버전·소스 URL·SHA-256과 빌드 설정을 기록합니다. '
            '시험 및 빌드용 하위 프로젝트 고지도 포함되며, 포함된 모든 고지가 앱에 링크되었다는 뜻은 아닙니다.\n\n'
            '이 앱은 FFmpeg 라이브러리를 LGPL 2.1 이상 조건으로 사용합니다. '
            'GPL·nonfree·version3 옵션의 비활성화 여부와 실제 configure 설정을 evidence에 기록했습니다. '
            '[FFmpeg 원문 안내](https://ffmpeg.org/legal.html)를 함께 확인하십시오.\n\n'
            'FFTW의 GPL 2 이상 원문과 저작권 고지, 설치 당시 Homebrew recipe·receipt 및 '
            '해당 소스 아카이브를 보존했습니다. '
            '[FFTW 원문 안내](https://www.fftw.org/fftw3_doc/License-and-Copyright.html)를 함께 확인하십시오.\n\n'
            f'대응 소스 제공 파일: `{companion.name}`\n\n'
            f'SHA-256: `{source_manifest["corresponding_sources_sha256"]}`\n\n'
            '이 파일은 앱 밖에 생성됩니다. 배포 시 앱과 함께 제공하거나 같은 배포 위치에 게시하십시오. '
            '원본 소스 아카이브, 현재 Aegisub·Git 하위 프로젝트 소스 스냅샷, 로컬 변경 파일, '
            '빌드 설정 및 고지가 들어 있습니다. 아카이브를 풀고 evidence의 설정·recipe와 '
            'overrides 기록을 적용하면 수집 시점의 소스를 확인할 수 있습니다. '
            '공개 게시 여부는 이 스크립트가 대신 보장하지 않습니다.\n', encoding='utf-8')
        print(f'License manifest: {self.output / "sources.json"}')
        print(f'Corresponding sources: {companion}')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(f'Usage: {sys.argv[0]} source-directory app-bundle')
    try:
        collector = Collector(Path(sys.argv[1]), Path(sys.argv[2]))
        collector.homebrew(collector.origins())
        collector.project()
        collector.local()
        collector.dictionary()
        collector.finish()
    except (LicenseError, OSError, subprocess.CalledProcessError, tarfile.TarError) as error:
        sys.exit(f'License collection failed: {error}')
