from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from urllib.parse import urlsplit


class LicenseError(Exception):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def fetch(cache: Path, url: str, expected: str = '', headers: tuple[str, ...] = ()) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    key = expected or hashlib.sha256(url.encode()).hexdigest()
    target = cache / (key + '-' + Path(urlsplit(url).path).name)
    if target.is_file():
        if expected and sha256(target) != expected:
            raise LicenseError(f'Source cache checksum mismatch: {target}')
        return target
    with tempfile.NamedTemporaryFile(dir=cache, suffix='.part') as temporary:
        command = ['curl', '-fLsS', '--connect-timeout', '20', '--max-time', '180']
        for header in headers:
            command.extend(['-H', header])
        subprocess.run(command + [url, '-o', temporary.name], check=True)
        downloaded = Path(temporary.name)
        if expected and sha256(downloaded) != expected:
            raise LicenseError(f'Source checksum mismatch: {url}')
        shutil.copyfile(downloaded, target)
    return target


def is_notice(path: PurePosixPath) -> bool:
    return (bool(re.match(r'^(licen[cs]e|copying|copyright|notice|unlicense|authors|'
                          r'ftl|[al]?gpl|lgpl|ofl)(?:[._-].*)?$', path.name, re.I))
            or any(part.lower() in ('licenses', 'licences') for part in path.parts)
            or str(path).endswith(('src/jpeg/README', 'src/zlib/README', 'src/gl/glext.h')))


def copy_notices(source: Path, target: Path) -> int:
    count = 0
    for directory, dirs, files in os.walk(source):
        dirs[:] = [name for name in dirs if name not in ('.git', '.venv', '__pycache__')]
        for name in files:
            path = Path(directory) / name
            relative = path.relative_to(source)
            if is_notice(PurePosixPath(relative.as_posix())) and path.is_file():
                destination = target / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
                count += 1
    return count


def archive_notices(archive: Path, target: Path) -> int:
    count = 0
    with tarfile.open(archive) as stream:
        for member in stream:
            path = PurePosixPath(member.name)
            if member.isfile() and is_notice(path):
                if path.is_absolute() or '..' in path.parts:
                    raise LicenseError(f'Unsafe source archive path: {member.name}')
                content = stream.extractfile(member)
                if content is None:
                    raise LicenseError(f'Unreadable archive member: {member.name}')
                with content:
                    destination = target / str(path)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with destination.open('wb') as output:
                        shutil.copyfileobj(content, output)
                count += 1
    return count


def recipe_sources(recipe: Path) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    url = ''
    for line in recipe.read_text(encoding='utf-8').splitlines():
        match = re.match(r'\s*url "(https?://[^"]+)"', line)
        if match:
            url = match.group(1)
        match = re.match(r'\s*sha256 "([0-9a-f]{64})"', line)
        if match and url:
            sources.append({'url': url, 'sha256': match.group(1)})
            url = ''
    if not sources:
        raise LicenseError(f'No pinned source in installed Homebrew recipe: {recipe}')
    return sources


def git_snapshot(source: Path, destination: Path) -> dict[str, str]:
    def git(*args: str) -> str:
        return subprocess.check_output(['git', '-C', str(source), *args], text=True).strip()

    revision = git('rev-parse', 'HEAD')
    remote = git('remote', 'get-url', 'origin')
    names = subprocess.check_output(['git', '-C', str(source), 'ls-files', '-z',
                                     '--cached', '--others', '--exclude-standard']).decode().split('\0')
    with tarfile.open(destination, 'w:gz') as archive:
        for name in sorted(set(names) - {''}):
            path = source / name
            if path.is_file() or path.is_symlink():
                archive.add(path, arcname=name, recursive=False)
    return {'revision': revision, 'repository': remote, 'snapshot_sha256': sha256(destination),
            'working_tree_status': git('status', '--porcelain'), 'snapshot': destination.name}


def preserve_overrides(archive: Path, source: Path, destination: Path) -> list[str]:
    changed: list[str] = []

    def compare(name: str, data: bytes) -> None:
        path = PurePosixPath(name)
        parts = path.parts
        if path.is_absolute() or len(parts) < 2 or '..' in parts:
            raise LicenseError(f'Unsafe source archive path: {name}')
        relative = Path(*parts[1:])
        local = source / relative
        if not local.is_file():
            changed.append('deleted:' + relative.as_posix())
        elif hashlib.sha256(data).hexdigest() != sha256(local):
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(local, target)
            changed.append(relative.as_posix())

    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as zipped:
            for entry in zipped.infolist():
                if not entry.is_dir():
                    compare(entry.filename, zipped.read(entry))
    else:
        with tarfile.open(archive) as stream:
            for member in stream:
                if member.isfile():
                    content = stream.extractfile(member)
                    if content is None:
                        raise LicenseError(f'Unreadable archive member: {member.name}')
                    with content:
                        compare(member.name, content.read())
    return changed
