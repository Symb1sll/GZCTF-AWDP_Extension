#!/usr/bin/env python3
"""Stage AWDP production files; do not change or restart live services."""
import argparse
import ast
import io
import json
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path

EXTENSION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXTENSION / 'awdp/deploy'))
from stage_files import publish_private_directory

ROOT = Path('/srv/awdp/gzctf-prod')


def read_config(path):
    text = path.read_text(encoding='utf-8-sig')
    quoted = r'"(?:\\.|[^"\\])*"'
    text = re.sub(quoted + r'|//[^\r\n]*|/\*[\s\S]*?\*/',
                  lambda m: m.group(0) if m.group(0).startswith('"') else ' ', text)
    text = re.sub(quoted + r'|,(?=\s*[}\]])',
                  lambda m: m.group(0) if m.group(0).startswith('"') else '', text)
    return json.loads(text)


def connection_fields(value):
    """Parse the supported Npgsql key/value form without logging credentials."""
    fields, position = {}, 0
    while position < len(value):
        while position < len(value) and (value[position].isspace() or value[position] == ';'):
            position += 1
        if position == len(value):
            break
        start = position
        while position < len(value) and value[position] not in '=;':
            position += 1
        if position == len(value) or value[position] != '=':
            raise ValueError('Unsupported database connection syntax')
        key = value[start:position].strip().replace(' ', '').lower()
        position += 1
        while position < len(value) and value[position].isspace():
            position += 1
        if position < len(value) and value[position] in ('"', "'"):
            quote, content = value[position], []
            position += 1
            while True:
                if position == len(value):
                    raise ValueError('Unsupported database connection syntax')
                character = value[position]
                position += 1
                if character == quote:
                    if position < len(value) and value[position] == quote:
                        content.append(quote)
                        position += 1
                    else:
                        break
                else:
                    content.append(character)
            result = ''.join(content)
            while position < len(value) and value[position].isspace():
                position += 1
            if position < len(value) and value[position] != ';':
                raise ValueError('Unsupported database connection syntax')
        else:
            start = position
            while position < len(value) and value[position] != ';':
                position += 1
            result = value[start:position].strip()
            if '"' in result or "'" in result:
                raise ValueError('Unsupported database connection syntax')
        if not key or key in fields:
            raise ValueError('Duplicate or empty database connection key; review manually')
        fields[key] = result
    return fields


def check_host():
    if not Path('/var/run/docker.sock').is_socket():
        raise SystemExit('Native local /var/run/docker.sock required')
    endpoint = os.environ.get('DOCKER_HOST') if not os.environ.get('DOCKER_CONTEXT') else None
    if not endpoint:
        endpoint = subprocess.check_output(
            ['docker', 'context', 'inspect', '--format', '{{.Endpoints.docker.Host}}'], text=True).strip()
    if endpoint != 'unix:///var/run/docker.sock':
        raise SystemExit('Docker CLI must use the same local socket as Web and Runner')
    info = json.loads(subprocess.check_output(['docker', 'info', '--format', '{{json .}}'], text=True))
    security = info.get('SecurityOptions') or []
    if info.get('OSType') != 'linux' or any('rootless' in item for item in security):
        raise SystemExit('A native rootful Linux Docker Engine is required')
    if 'name=apparmor' not in security:
        raise SystemExit('AppArmor support required by the reviewed Runner')
    subprocess.run(['systemctl', 'is-active', '--quiet', 'docker.service'], check=True)


def runtime_version(container):
    # docker cp emits tar; no assumption that the application image has a shell/curl.
    blob = subprocess.check_output(['docker', 'cp', container + ':/app/files/version.txt', '-'])
    if len(blob) > 65536:
        raise ValueError('Unexpected version marker archive')
    with tarfile.open(fileobj=io.BytesIO(blob), mode='r:') as archive:
        members = archive.getmembers()
        if (len(members) != 1 or not members[0].isfile() or
                members[0].size > 128 or Path(members[0].name).name != 'version.txt'):
            raise ValueError('Unexpected version marker archive')
        return archive.extractfile(members[0]).read().decode('ascii').strip()


def check_baseline(original, live):
    if not live.get('State', {}).get('Running'):
        raise SystemExit('Original Web must be running for the compatibility check')
    if runtime_version('gzctf-gzctf-1') not in ('1.2.5', '1.2.5.0'):
        raise SystemExit('Original Web is not the reviewed v1.2.5 baseline; migration refused')
    mounts = [m for m in live.get('Mounts', []) if m.get('Destination') == '/app/appsettings.json']
    if (len(mounts) != 1 or mounts[0].get('Source') != '/root/GZCTF/appsettings.json' or
            mounts[0].get('RW', True)):
        raise SystemExit('Original Web config mount differs from the reviewed deployment')
    environment = [item.split('=', 1)[0].lower() for item in live['Config'].get('Env', [])]
    if any(key == 'connectionstrings__database' or key.startswith(('containerprovider__', 'awdp__'))
           for key in environment):
        raise SystemExit('Environment overrides require manual configuration review')
    provider = original.get('ContainerProvider') or {}
    docker_config = provider.get('DockerConfig') or {}
    if (provider.get('Type') != 'Docker' or docker_config.get('SwarmMode', False) or
            docker_config.get('Uri', '') not in ('', 'unix:///var/run/docker.sock')):
        raise SystemExit('Only the reviewed local Docker provider is supported')
    fields = connection_fields(original['ConnectionStrings']['Database'])
    if any(first in fields and second in fields for first, second in
           (('host', 'server'), ('database', 'initialcatalog'))):
        raise SystemExit('Ambiguous database connection aliases; review manually')
    database = fields.get('database', fields.get('initialcatalog', ''))
    host = fields.get('host', fields.get('server', ''))
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,62}', database) or fields.get('port', '5432') != '5432':
        raise SystemExit('Explicit local database name and default port required')
    db = json.loads(subprocess.check_output(['docker', 'inspect', 'gzctf-db-1'], text=True))[0]
    if not db.get('State', {}).get('Running'):
        raise SystemExit('Original database must be running')
    web_networks = live.get('NetworkSettings', {}).get('Networks') or {}
    db_networks = db.get('NetworkSettings', {}).get('Networks') or {}
    aliases = {'gzctf-db-1'}
    common = set(web_networks).intersection(db_networks)
    for name in common:
        aliases.update(db_networks[name].get('Aliases') or [])
    if not common or host not in aliases:
        raise SystemExit('Connection must target the original database on a shared Docker network')
    sql = 'SELECT "MigrationId" FROM "__EFMigrationsHistory" ORDER BY "MigrationId";'
    command = ('exec psql -X -A -t -U "${POSTGRES_USER:-postgres}" -d "$1" '
               '-v ON_ERROR_STOP=1 -c \'' + sql + '\'')
    actual = subprocess.check_output(
        ['docker', 'exec', 'gzctf-db-1', 'sh', '-c', command, 'sh', database], text=True).splitlines()
    expected = json.loads((EXTENSION / 'integration/manifest.json').read_text(encoding='utf-8'))['upstream_migrations']
    if actual != expected:
        raise SystemExit('Database migration history differs from the reviewed pre-AWDP baseline; nothing written')
    print('Original Web version and baseline migration history verified')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-image-id', required=True,
                        help='sha256 image ID of the platform image you tested, not a registry tag')
    parser.add_argument('--check', action='store_true', help='Read-only compatibility and Compose validation')
    args = parser.parse_args()
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', args.expected_image_id):
        parser.error('Expected a full sha256: image ID')
    if os.geteuid() != 0:
        raise SystemExit('Run as root')
    check_host()
    if not os.path.ismount('/srv/awdp'):
        raise SystemExit('/srv/awdp is not mounted')
    unit_path = Path('/etc/systemd/system/gzctf-awdp-prod-runner.service')
    if ROOT.exists() or ROOT.is_symlink() or unit_path.exists() or unit_path.is_symlink():
        raise SystemExit('Production staging path or service already exists; nothing overwritten')
    image = subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{.Id}}',
                                     'gzctf-awdp-dev:1.2.5-local'], text=True).strip()
    if image != args.expected_image_id:
        raise SystemExit('Tested platform image mismatch')
    live = json.loads(subprocess.check_output(['docker', 'inspect', 'gzctf-gzctf-1'], text=True))[0]
    if live['Config'].get('User') not in ('', 'root', '0', '0:0'):
        raise SystemExit('Unexpected production Web user; review directory permissions first')
    original = read_config(Path('/root/GZCTF/appsettings.json'))
    if 'Awdp' in original:
        raise SystemExit('Production already has Awdp configuration; nothing overwritten')
    if not original.get('ConnectionStrings', {}).get('Database'):
        raise SystemExit('Production database connection missing')
    check_baseline(original, live)
    source = Path('/srv/awdp-dev/runner/awdp_runner.py').read_text(encoding='utf-8')
    if source != (EXTENSION / 'awdp/runner/awdp_runner.py').read_text(encoding='utf-8'):
        raise SystemExit('Test Runner differs from this extension; review and retest before production')
    replacements = {
        '/srv/awdp-dev/': ROOT.as_posix() + '/',
        'gzctf.awdp.dev.managed=true': 'gzctf.awdp.prod.managed=true',
        'gzctf-awdp-dev-target-': 'gzctf-awdp-prod-target-',
        'gzctf-awdp-dev-checker-': 'gzctf-awdp-prod-checker-',
    }
    expected_counts = [4, 1, 1, 1]
    for (old, new), count in zip(replacements.items(), expected_counts):
        if source.count(old) != count:
            raise SystemExit('Runner differs from reviewed version; nothing written')
        source = source.replace(old, new)
    ast.parse(source)
    if any(s in source for s in ('/srv/awdp-dev', 'gzctf.awdp.dev.managed', 'gzctf-awdp-dev-')):
        raise SystemExit('Unexpected remaining development reference')
    judge = json.loads(Path('/srv/awdp-dev/config/challenges.json').read_text(encoding='utf-8'))
    matches = [c for c in judge['challenges'] if c['id'] == 'ticket-attachments']
    if len(matches) != 1 or not matches[0].get('enabled', True):
        raise SystemExit('Expected enabled ticket challenge missing')
    for field in ('target_image_id', 'checker_image_id'):
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', matches[0][field]):
            raise SystemExit('Judge allowlist must contain full image IDs, not tags')
        subprocess.run(['docker', 'image', 'inspect', matches[0][field]],
                       stdout=subprocess.DEVNULL, check=True)
    candidate = dict(original)
    candidate['Awdp'] = {'Enabled': True, 'Root': ROOT.as_posix(), 'Challenges': {}, 'Scores': {}}
    assert {k: v for k, v in candidate.items() if k != 'Awdp'} == original
    mounts = [(ROOT / 'config/platform.json').as_posix() + ':/app/appsettings.json:ro']
    for rel, readonly in [('data/submissions', False), ('queue/pending', False),
                          ('queue/running', True), ('queue/results', True), ('queue/archive', True)]:
        path = (ROOT / rel).as_posix()
        mounts.append(path + ':' + path + (':ro' if readonly else ''))
    override = {'services': {'gzctf': {'image': 'gzctf-awdp-dev:1.2.5-local', 'volumes': mounts}}}
    unit = '''[Unit]
Description=GZCTF AWDP production judge
After=docker.service
Requires=docker.service
RequiresMountsFor=/srv/awdp
[Service]
Type=simple
User=root
Group=root
UMask=0077
ExecStart=/usr/bin/python3 /srv/awdp/gzctf-prod/runner/awdp_runner.py
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/srv/awdp/gzctf-prod
ProtectHome=true
[Install]
WantedBy=multi-user.target
'''
    # Validate the merge through stdin BEFORE creating the runtime destination.
    subprocess.run(['docker', 'compose', '-p', 'gzctf', '-f', '/root/GZCTF/docker-compose.yml',
                    '-f', '-', 'config', '--quiet'], input=json.dumps(override), text=True, check=True)
    if args.check:
        print('Read-only checks passed; no files, services or database contents changed')
        return
    os.umask(0o077)
    publish_private_directory(ROOT,
        ('config', 'runner', 'data/submissions', 'queue/pending', 'queue/running',
         'queue/results', 'queue/archive', 'queue/failed', 'tmp/jobs'), {
        'runner/awdp_runner.py': source,
        'config/challenges.json': json.dumps({'challenges': matches}, indent=2) + '\n',
        'config/platform.json': json.dumps(candidate, ensure_ascii=False, indent=2) + '\n',
        'compose.awdp.json': json.dumps(override, indent=2) + '\n',
        'gzctf-awdp-prod-runner.service': unit,
    })
    print('Production files prepared: ' + str(ROOT))
    print('Original configuration values preserved; production mappings start empty')
    print('Runner label: gzctf.awdp.prod.managed=true')
    print('Compose merge syntax verified; no services restarted or installed')


if __name__ == '__main__':
    main()
