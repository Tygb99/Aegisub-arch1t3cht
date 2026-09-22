#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
import re
import sys
import os
import shutil
import stat
import subprocess
import hashlib
import json
from typing import NamedTuple


class LoadCommands(NamedTuple):
    dependencies: tuple[str, ...]
    rpaths: tuple[str, ...]
    has_id: bool


class Library(NamedTuple):
    source: Path
    commands: LoadCommands


class BundleError(Exception):
    pass


def otool(cmdline: list[str]) -> list[str]:
    return subprocess.check_output(['otool'] + cmdline, encoding='utf-8').splitlines()


def load_commands(lib: Path) -> LoadCommands:
    dependencies: list[str] = []
    rpaths: list[str] = []
    has_id = False
    command = ''
    for line in otool(['-l', str(lib)]):
        line = line.strip()
        if line.startswith('cmd '):
            command = line[4:]
            has_id = has_id or command == 'LC_ID_DYLIB'
        field = re.fullmatch(r'(?:name|path) (.*) \(offset \d+\)', line)
        if field:
            if command == 'LC_RPATH':
                rpaths.append(field.group(1))
            elif command in ('LC_LOAD_DYLIB', 'LC_LOAD_WEAK_DYLIB', 'LC_REEXPORT_DYLIB',
                             'LC_LAZY_LOAD_DYLIB', 'LC_LOAD_UPWARD_DYLIB'):
                dependencies.append(field.group(1))
    return LoadCommands(tuple(dict.fromkeys(dependencies)),
                        tuple(dict.fromkeys(rpaths)), has_id)


def is_macho(path: Path) -> bool:
    with path.open('rb') as stream:
        return stream.read(4) in (b'\xfe\xed\xfa\xce', b'\xce\xfa\xed\xfe',
                                  b'\xfe\xed\xfa\xcf', b'\xcf\xfa\xed\xfe',
                                  b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca',
                                  b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca')


def is_sys_lib(path: Path) -> bool:
    return os.path.normpath(path).startswith(('/usr/lib/', '/System/Library/'))


def expand_path(name: str, loader: Path, executable_dir: Path) -> Path | None:
    for token, directory in (('@loader_path', loader.parent),
                             ('@executable_path', executable_dir)):
        if name == token or name.startswith(token + '/'):
            return Path(os.path.normpath(str(directory) + name[len(token):]))
    if name.startswith('@'):
        return None
    return Path(os.path.abspath(name))


class Bundle:
    def __init__(self, executable: Path) -> None:
        self.executable = executable.parent.resolve() / executable.name
        self.targetdir = self.executable.parent
        self.contents = (self.targetdir.parent if self.targetdir.name == 'MacOS'
                         and self.targetdir.parent.name == 'Contents' else self.targetdir)
        self.libraries: dict[Path, Library] = {}
        self.destinations: dict[Path, Path] = {}
        self.changes: dict[Path, dict[str, Path]] = {}
        self.visited: set[tuple[Path, tuple[Path, ...]]] = set()

    def register(self, source: Path, target: Path) -> Path:
        source = source.resolve(strict=True)
        previous = self.libraries.get(target)
        if previous and previous.source != source:
            raise BundleError(f'Conflicting library name {target.name}: '
                              f'{previous.source} and {source}')
        if target.exists() and target.resolve() != source:
            raise BundleError(f'Conflicting bundle path: {target} and {source}')
        if not previous:
            if not is_macho(source):
                raise BundleError(f'Not a Mach-O library: {source}')
            self.libraries[target] = Library(source, load_commands(source))
            self.destinations.setdefault(source, target)
        return target

    def rpaths(self, library: Library, inherited: tuple[Path, ...]) -> tuple[Path, ...]:
        paths: list[Path] = []
        for name in library.commands.rpaths:
            if name.startswith('@rpath/'):
                paths.extend(path / name[7:] for path in inherited)
            else:
                path = expand_path(name, library.source, self.targetdir)
                if path is not None:
                    paths.append(path)
        return tuple(dict.fromkeys((*paths, *inherited)))

    def visit(self, target: Path, inherited: tuple[Path, ...]) -> None:
        library = self.libraries[target]
        rpaths = self.rpaths(library, inherited)
        context = (target, rpaths)
        if context in self.visited:
            return
        self.visited.add(context)
        changes = self.changes.setdefault(target, {})
        for name in library.commands.dependencies:
            if name.startswith('@rpath/'):
                candidates = [path / name[7:] for path in rpaths]
            else:
                path = expand_path(name, library.source, self.targetdir)
                candidates = [path] if path is not None else []
                if not name.startswith(('/', '@')):
                    candidates.append(library.source.parent / name)
            dependency = next((path for path in candidates
                               if is_sys_lib(path) or path.is_file()), None)
            if dependency is None:
                attempted = ', '.join(map(str, candidates)) or '(no search paths)'
                raise BundleError(f'Unresolved dependency {name} in {library.source}; '
                                  f'tried: {attempted}')
            if is_sys_lib(dependency):
                destination = dependency
            else:
                source = dependency.resolve(strict=True)
                destination = self.destinations.get(source)
                if destination is None:
                    destination = self.register(source, self.targetdir / source.name)
            if name in changes and changes[name] != destination:
                raise BundleError(f'Conflicting resolution of {name} in {library.source}: '
                                  f'{changes[name]} and {destination}')
            changes[name] = destination
            if not is_sys_lib(destination):
                self.visit(destination, rpaths)

    def collect(self) -> None:
        self.register(self.executable, self.executable)
        for directory, _, files in os.walk(self.contents):
            for name in sorted(files):
                path = Path(directory) / name
                if path.is_file() and is_macho(path):
                    self.register(path, path)
        roots = list(self.libraries)
        self.visit(self.executable, ())
        inherited = self.rpaths(self.libraries[self.executable], ())
        for target in roots:
            if target not in self.changes:
                self.visit(target, inherited)

    def source_name(self, source: Path) -> str:
        for token, root in (('@bundle', self.contents),
                            ('@source', Path(__file__).resolve().parents[1])):
            if source.is_relative_to(root):
                return token + '/' + source.relative_to(root).as_posix()
        for parent in source.parents:
            if (parent / 'INSTALL_RECEIPT.json').is_file():
                return '@homebrew/Cellar/' + source.relative_to(parent.parent.parent).as_posix()
        return '@external/' + source.name

    def repair(self) -> None:
        manifest_path = self.contents / 'SharedSupport' / 'dependency-origins.json'
        previous = (json.loads(manifest_path.read_text()).get('images', [])
                    if manifest_path.is_file() else [])
        previous = {item['path']: item for item in previous}
        origins = []
        for target, library in self.libraries.items():
            source_hash = hashlib.sha256(library.source.read_bytes()).hexdigest()
            relative = target.relative_to(self.contents).as_posix()
            recorded = previous.get(relative, {})
            if (library.source == target and recorded.get('bundled_sha256') == source_hash):
                origin = recorded['source']
                origins.append({**recorded, 'source': self.source_name(Path(origin))
                                if origin.startswith('/') else origin})
            else:
                origins.append({'path': relative, 'source': self.source_name(library.source),
                                'source_sha256': source_hash})
        for target, library in self.libraries.items():
            if target != library.source:
                if target.is_symlink():
                    target.unlink()
                shutil.copyfile(library.source, target)
                shutil.copymode(library.source, target)
                print(f'Copied {library.source} to {target}')

        for target, library in self.libraries.items():
            command = ['install_name_tool']
            for name, destination in self.changes[target].items():
                replacement = (str(destination) if is_sys_lib(destination) else
                               '@loader_path/' + os.path.relpath(destination, target.parent))
                if name != replacement:
                    command.extend(['-change', name, replacement])
            if library.commands.has_id:
                command.extend(['-id', '@executable_path/' +
                                os.path.relpath(target, self.targetdir)])
            for name in library.commands.rpaths:
                path = expand_path(name, target, self.targetdir)
                if (not name.startswith(('@loader_path', '@executable_path'))
                        or path is None
                        or self.contents not in (path.resolve(), *path.resolve().parents)):
                    command.extend(['-delete_rpath', name])
            mode = stat.S_IMODE(target.stat().st_mode)
            try:
                target.chmod(mode | stat.S_IWUSR)
                if len(command) > 1:
                    subprocess.run(command + [str(target)], check=True)
            finally:
                target.chmod(mode)

        signature = os.environ.get('AEGISUB_BUNDLE_SIGNATURE') or '-'
        # Signing the main executable also checks the enclosing app's nested code.
        for target in sorted(self.libraries,
                             key=lambda path: (path == self.executable, -len(path.parts))):
            mode = stat.S_IMODE(target.stat().st_mode)
            try:
                target.chmod(mode | stat.S_IWUSR)
                subprocess.run(['codesign', '--force', '--sign', signature, str(target)], check=True)
            finally:
                target.chmod(mode)

        for item in origins:
            item['bundled_sha256'] = hashlib.sha256(
                (self.contents / item['path']).read_bytes()).hexdigest()
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps({
            'schema': 1, 'phase': 'after-relocation-and-individual-signing-before-app-seal',
            'images': origins}, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(f'Usage: {sys.argv[0]} executable')
    try:
        bundle = Bundle(Path(sys.argv[1]))
        print('Searching for libraries in', bundle.executable, '...')
        bundle.collect()
        bundle.repair()
    except (BundleError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(f'Bundle repair failed: {error}')
    print('All done!')
