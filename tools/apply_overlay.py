#!/usr/bin/env python3
"""Apply the reviewed AWDP extension to an independently obtained GZCTF baseline."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(root, relative):
    path = PurePosixPath(relative)
    if (path.is_absolute() or not path.parts or '..' in path.parts or
            '\\' in relative or ':' in relative or
            path.parts[0] not in ('src', 'awdp', 'docs')):
        raise ValueError('Unsafe target path: ' + relative)
    if ('Services/Container/Manager/' in relative or
            relative.endswith('/hooks/useConfig.ts')):
        raise ValueError('Restricted upstream file must not be distributed: ' + relative)
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('Symbolic link in target/source path: ' + relative)
    return current


def atomic_write(path, data, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.awdp-overlay-', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def apply(extension, upstream, check=False, source_archive=False):
    extension, upstream = Path(extension).resolve(), Path(upstream).resolve()
    if extension == upstream or extension in upstream.parents or upstream in extension.parents:
        raise ValueError('Keep the extension repository and upstream checkout separate')
    if not upstream.is_dir():
        raise ValueError('Upstream directory does not exist')
    manifest = json.loads((extension / 'integration/manifest.json').read_text(encoding='utf-8-sig'))
    if manifest['schema_version'] != 1 or manifest['hash_mode'] != 'raw-bytes':
        raise ValueError('Unsupported manifest')
    if not source_archive:
        head = subprocess.check_output(
            ['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip()
        if head != manifest['upstream_commit']:
            raise ValueError('Upstream HEAD does not match the reviewed baseline')
    # Hashes also detect local edits and Windows CRLF conversion in affected files.
    planned, seen = [], set()
    for entry, source_root in (
            [(e, extension / 'integration/overlay') for e in manifest['files']] +
            [(e, extension) for e in manifest['support_files']]):
        relative = entry['path']
        if relative in seen:
            raise ValueError('Duplicate manifest path: ' + relative)
        seen.add(relative)
        source = safe_path(source_root, relative)
        target = safe_path(upstream, relative)
        payload = source.read_bytes()
        if digest(payload) != entry['overlay_sha256']:
            raise ValueError('Extension integrity mismatch: ' + relative)
        previous = target.read_bytes() if target.is_file() else None
        if previous is not None and digest(previous) == entry['overlay_sha256']:
            continue  # Already installed; never apply an incremental patch twice.
        if target.exists() and previous is None:
            raise ValueError('Target is not a file: ' + relative)
        actual = digest(previous) if previous is not None else None
        if actual != entry['original_sha256']:
            raise ValueError('Modified or missing upstream file; refusing overwrite: ' + relative)
        mode = (target.stat().st_mode & 0o777) if previous is not None else 0o644
        planned.append((relative, target, previous, payload, mode))
    if check:
        return len(planned)
    # Validate ALL entries before the first write. Restore written files on a normal exception.
    written = []
    try:
        for relative, target, previous, payload, mode in planned:
            safe_path(upstream, relative)
            current = target.read_bytes() if target.is_file() else None
            if current != previous:
                raise ValueError('Target changed after validation: ' + relative)
            written.append((target, previous, mode))
            atomic_write(target, payload, mode)
    except BaseException:
        for target, previous, mode in reversed(written):
            if previous is None:
                target.unlink(missing_ok=True)
            else:
                atomic_write(target, previous, mode)
        raise
    return len(planned)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--check', action='store_true', help='Validate without writing files')
    parser.add_argument('--source-archive', action='store_true',
                        help='For a trusted upstream source archive: verify affected hashes, not Git HEAD')
    args = parser.parse_args()
    try:
        count = apply(Path(__file__).resolve().parents[1], args.upstream,
                      args.check, args.source_archive)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        parser.exit(1, 'Overlay refused: ' + str(exc) + '\n')
    print(('Validated; files to install: ' if args.check else 'Installed files: ') + str(count))


if __name__ == '__main__':
    main()
