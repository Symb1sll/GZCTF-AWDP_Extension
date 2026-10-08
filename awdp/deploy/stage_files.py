"""Publish a new private runtime directory only after all files are written.

Run during a maintenance window, without concurrent writers. Failed staging
directories are retained for inspection; no live directory is removed.
"""
import os
from pathlib import Path, PurePosixPath
import sys
import tempfile


def private_path(root, relative):
    path = PurePosixPath(relative)
    if (not path.parts or path.is_absolute() or '..' in path.parts or
            '\\' in relative or ':' in relative):
        raise ValueError('Unsafe staging path: ' + relative)
    return root.joinpath(*path.parts)


def publish_private_directory(destination, directories, files):
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Destination already exists; nothing overwritten')
    # Validate paths before writing anything. Parent must be prepared by the operator.
    for relative in list(directories) + list(files):
        private_path(destination, relative)
    if not destination.parent.is_dir():
        raise FileNotFoundError('Destination parent is missing')
    stage = Path(tempfile.mkdtemp(prefix='.' + destination.name + '.prepare-',
                                 dir=str(destination.parent)))
    stage.chmod(0o700)
    try:
        for relative in directories:
            private_path(stage, relative).mkdir(parents=True, exist_ok=True, mode=0o700)
        for relative, content in files.items():
            target = private_path(stage, relative)
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with target.open('x', encoding='utf-8', newline='\n') as stream:
                stream.write(content)
            target.chmod(0o600)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError('Destination appeared during staging; nothing overwritten')
        stage.rename(destination)
    except BaseException:
        print('Preparation failed; private staging retained: ' + str(stage), file=sys.stderr)
        raise

