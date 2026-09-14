#!/usr/bin/env python3

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
from typing import Final, Literal


THIN_MAGIC: Final[dict[bytes, Literal['big', 'little']]] = {
    b'\xfe\xed\xfa\xce': 'big', b'\xce\xfa\xed\xfe': 'little',
    b'\xfe\xed\xfa\xcf': 'big', b'\xcf\xfa\xed\xfe': 'little'}
FAT_MAGIC: Final = (b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca',
                   b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca')


@dataclass(frozen=True, slots=True)
class Image:
    path: str
    architectures: tuple[str, ...]
    thin: bool
    executable: bool
    install_name: str
    rpaths: tuple[str, ...]
    dependencies: tuple[str, ...]
    minimum_os: str | None


def run(*args: str) -> str:
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()


def version(value: object) -> tuple[int, ...] | None:
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]+(?:\.[0-9]+){0,2}', value):
        return None
    parts = tuple(map(int, value.split('.')))
    return parts + (0,) * (3 - len(parts)) if parts[0] > 0 else None


def system_path(name: str) -> bool:
    normalized = os.path.normpath(name)
    return (normalized in ('/System/Library', '/usr/lib')
            or normalized.startswith(('/System/Library/', '/usr/lib/')))


def expand(name: str, loader: Path, executable: Path) -> Path | None:
    for token, directory in (('@loader_path', loader.parent),
                             ('@executable_path', executable.parent)):
        if name == token or name.startswith(token + '/'):
            return Path(str(directory) + name[len(token):])
    if system_path(name):
        return Path(os.path.normpath(name))
    return None


def inspect(path: Path, relative: str, header: bytes) -> Image:
    command = install_name = ''
    minimum_os = None
    rpaths: list[str] = []
    for line in run('otool', '-l', str(path)).splitlines():
        line = line.strip()
        if line.startswith('cmd '):
            command = line[4:]
        if ((command == 'LC_BUILD_VERSION' and line.startswith('minos '))
                or (command == 'LC_VERSION_MIN_MACOSX' and line.startswith('version '))):
            minimum_os = line.split()[1]
        field = re.fullmatch(r'(?:name|path) (.*) \(offset \d+\)', line)
        if field and command == 'LC_RPATH':
            rpaths.append(field.group(1))
        if field and command == 'LC_ID_DYLIB':
            install_name = field.group(1)
    dependencies = re.findall(r'^\s+(.+) \(compatibility version .*$',
                              run('otool', '-L', str(path)), re.MULTILINE)
    if install_name and dependencies and dependencies[0] == install_name:
        dependencies.pop(0)
    byteorder = THIN_MAGIC.get(header[:4])
    executable = byteorder is not None and int.from_bytes(header[12:16], byteorder) == 2
    return Image(relative, tuple(run('lipo', '-archs', str(path)).split()),
                 byteorder is not None, executable, install_name, tuple(rpaths),
                 tuple(dependencies), minimum_os)


class Audit:
    def __init__(self, app: Path) -> None:
        self.app = app.resolve(strict=True)
        self.images: dict[Path, Image] = {}
        self.symlinks: list[dict[str, str]] = []
        self.errors: list[str] = []
        self.resolutions: set[str] = set()
        self.visited: set[tuple[Path, Path, tuple[Path, ...]]] = set()
        self.codesign_verified = False
        self.minimum_os: str | None = None

    def label(self, path: Path) -> str:
        return str(path.relative_to(self.app))

    def error(self, code: str, detail: str) -> None:
        self.errors.append(f'{code}: {detail}'.replace(str(self.app), '<app>'))

    def inside(self, path: Path) -> bool:
        return path.resolve().is_relative_to(self.app)

    def scan(self) -> None:
        def walk_error(error: OSError) -> None:
            self.error('filesystem', str(error))

        for directory, directories, files in os.walk(self.app, onerror=walk_error):
            directories.sort()
            for name in sorted(directories + files):
                path = Path(directory) / name
                relative = self.label(path)
                try:
                    if path.is_symlink():
                        self.symlinks.append({'path': relative, 'target': os.readlink(path)})
                        if not path.resolve(strict=True).is_relative_to(self.app):
                            self.error('symlink_escape', relative)
                        continue
                    if path.is_dir():
                        continue
                    with path.open('rb') as stream:
                        header = stream.read(16)
                    if header[:4] not in THIN_MAGIC and header[:4] not in FAT_MAGIC:
                        continue
                    image = inspect(path, relative, header)
                    self.images[path] = image
                    if not image.thin or image.architectures != ('arm64',):
                        self.error('not_thin_arm64', f'{relative}: {image.architectures}')
                    if version(image.minimum_os) is None:
                        self.error('minimum_os_missing_or_invalid', relative)
                    if image.install_name and not (
                            image.install_name.startswith(('@rpath/', '@loader_path/',
                                                           '@executable_path/'))
                            or system_path(image.install_name)):
                        self.error('install_name', f'{relative}: {image.install_name}')
                except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
                    self.error('symlink' if path.is_symlink() else 'inspection',
                               f'{relative}: {error}')

    def rpaths(self, path: Path, executable: Path,
               inherited: tuple[Path, ...]) -> tuple[Path, ...]:
        paths: list[Path] = []
        for name in self.images[path].rpaths:
            expanded = expand(name, path, executable)
            if expanded is None or not (system_path(name) or self.inside(expanded)):
                self.error('rpath', f'{self.label(path)}: {name}')
            else:
                paths.append(expanded)
        return tuple(dict.fromkeys((*paths, *inherited)))

    def visit(self, path: Path, executable: Path, inherited: tuple[Path, ...],
              ancestors: tuple[Path, ...] = ()) -> None:
        if path in ancestors:
            return
        rpaths = self.rpaths(path, executable, inherited)
        context = (path, executable, rpaths)
        if context in self.visited:
            return
        self.visited.add(context)
        for name in self.images[path].dependencies:
            edge = f'{self.label(executable)}: {self.label(path)} -> {name}'
            if system_path(name):
                self.resolutions.add(f'{edge} -> system')
                continue
            if name.startswith('@rpath/'):
                candidates = [directory / name[7:] for directory in rpaths]
            else:
                expanded = expand(name, path, executable)
                candidates = [expanded] if expanded is not None else []
            resolved = False
            for candidate in candidates:
                if system_path(str(candidate)) and name.startswith('@rpath/'):
                    self.resolutions.add(f'{edge} -> {os.path.normpath(candidate)}')
                    resolved = True
                    break
                if not self.inside(candidate):
                    self.error('dependency_escape', edge)
                    break
                if not candidate.exists():
                    continue
                target = candidate.resolve(strict=True)
                if target not in self.images:
                    break
                self.resolutions.add(f'{edge} -> {self.label(target)}')
                resolved = True
                self.visit(target, executable, rpaths, (*ancestors, path))
                break
            if not resolved:
                self.error('dependency_unresolved', edge)

    def check(self) -> None:
        self.scan()
        if not self.images:
            self.error('mach_o', '앱에 Mach-O 파일이 없습니다.')
        try:
            with (self.app / 'Contents' / 'Info.plist').open('rb') as stream:
                metadata = plistlib.load(stream)
            minimum = metadata.get('LSMinimumSystemVersion') if isinstance(metadata, dict) else None
            self.minimum_os = minimum if isinstance(minimum, str) else None
            advertised = version(self.minimum_os)
            if advertised is None:
                self.error('plist_minimum_os', 'LSMinimumSystemVersion 값이 없거나 올바르지 않습니다.')
            else:
                for image in self.images.values():
                    required = version(image.minimum_os)
                    if required is not None and required > advertised:
                        self.error('minimum_os_exceeds_plist',
                                   f'{image.path}: {image.minimum_os} > {self.minimum_os}')
            name = metadata.get('CFBundleExecutable') if isinstance(metadata, dict) else None
            if not isinstance(name, str) or not name or Path(name).name != name:
                self.error('executable', 'CFBundleExecutable 값이 올바르지 않습니다.')
            else:
                main = (self.app / 'Contents' / 'MacOS' / name).resolve(strict=True)
                if main not in self.images or not self.images[main].executable:
                    self.error('executable', 'CFBundleExecutable이 Mach-O 실행 파일이 아닙니다.')
                else:
                    self.visit(main, main, ())
                    for path, image in self.images.items():
                        if image.executable and path != main:
                            self.visit(path, path, ())
                    reached = {context[0] for context in self.visited}
                    inherited = self.rpaths(main, main, ())
                    for path in self.images:
                        if path not in reached:
                            self.visit(path, main, inherited)
        except (OSError, RuntimeError, ValueError, plistlib.InvalidFileException) as error:
            self.error('bundle', str(error))
        try:
            run('codesign', '--verify', '--deep', '--strict', str(self.app))
            self.codesign_verified = True
        except (OSError, subprocess.CalledProcessError) as error:
            detail = error.output if isinstance(error, subprocess.CalledProcessError) else str(error)
            self.error('codesign', detail)

    def report(self) -> str:
        return json.dumps({
            'schema_version': 1,
            'status': 'failed' if self.errors else 'passed',
            'bundle': self.app.name,
            'minimum_os': self.minimum_os,
            'mach_o': [asdict(image) for _, image in sorted(self.images.items())],
            'symlinks': sorted(self.symlinks, key=lambda link: link['path']),
            'dependency_resolutions': sorted(self.resolutions),
            'codesign_verified': self.codesign_verified,
            'errors': sorted(set(self.errors)),
        }, ensure_ascii=False, sort_keys=True, indent=2) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description='macOS 앱의 ARM64 아키텍처·최소 OS·의존성·서명을 검사합니다.')
    parser.add_argument('app', type=Path, help='검사할 .app 경로')
    parser.add_argument('--output', type=Path, help='JSON 보고서 저장 경로 (표준 출력에도 기록)')
    args = parser.parse_args()
    try:
        audit = Audit(args.app)
        audit.check()
        report = audit.report()
        status = int(bool(audit.errors))
    except (OSError, RuntimeError) as error:
        report = json.dumps({'schema_version': 1, 'status': 'failed',
                             'errors': [f'bundle: {error}']}, ensure_ascii=False, indent=2) + '\n'
        status = 1
    print(report, end='')
    if args.output:
        args.output.write_text(report, encoding='utf-8')
    return status


if __name__ == '__main__':
    raise SystemExit(main())
