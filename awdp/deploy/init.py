#!/usr/bin/env python3
"""Run on the test host as root once; never touches production directories."""
import json
import os
import pathlib
import secrets
import subprocess
from stage_files import publish_private_directory

ROOT = pathlib.Path('/srv/awdp-dev')

def image_id(tag):
    return subprocess.check_output(['docker', 'image', 'inspect', '-f', '{{.Id}}', tag], text=True).strip()

def main():
    if os.geteuid() != 0:
        raise SystemExit('Run with sudo python3')
    if ROOT.exists() or ROOT.is_symlink():
        raise SystemExit('/srv/awdp-dev already exists; refusing to overwrite')
    target = image_id('awdp/ticket-target:1.0')
    checker = image_id('awdp/ticket-checker:1.0')
    os.umask(0o077)
    runner = (pathlib.Path(__file__).resolve().parents[1] / 'runner/awdp_runner.py').read_text(encoding='utf-8')
    password = secrets.token_hex(32)
    admin = 'Dev!9-' + secrets.token_hex(20)
    config = {
        'ConnectionStrings': {'Database': 'Host=db;Port=5432;Database=gzctf_awdp_dev;Username=awdp_dev;Password=' + password},
        'ADMIN_PASSWORD': admin, 'XorKey': secrets.token_hex(32),
        'ContainerProvider': {'Type': 'Docker', 'PublicEntry': '127.0.0.1',
            'DockerConfig': {'Uri': 'unix:///var/run/docker.sock', 'ChallengeNetwork': 'gzctf-awdp-dev-attack'}},
        'Awdp': {'Enabled': True, 'Root': str(ROOT), 'Challenges': {}, 'Scores': {}}
    }
    judge = {'challenges': [{'id': 'ticket-attachments', 'enabled': True,
        'target_image_id': target, 'checker_image_id': checker, 'allowed_paths': ['src/app.py'],
        'fix_score': 100, 'timeout_seconds': 90, 'target_memory': '512m', 'target_cpus': '1.0'}]}
    unit = '''[Unit]
Description=GZCTF AWDP isolated development judge
After=docker.service
Requires=docker.service
RequiresMountsFor=/srv/awdp-dev
[Service]
Type=simple
User=root
Group=root
UMask=0077
ExecStart=/usr/bin/python3 /srv/awdp-dev/runner/awdp_runner.py
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/srv/awdp-dev
ProtectHome=true
[Install]
WantedBy=multi-user.target
'''
    publish_private_directory(ROOT,
        ['config', 'data/submissions', 'queue/pending', 'queue/running', 'queue/results',
         'queue/archive', 'tmp/jobs', 'files', 'postgres', 'runner'], {
        'compose.env': 'DEV_DB_PASSWORD=' + password + '\n',
        'config/platform.json': json.dumps(config, indent=2) + '\n',
        'admin-password.txt': admin + '\n',
        'config/challenges.json': json.dumps(judge, indent=2) + '\n',
        'runner/awdp_runner.py': runner,
        'awdp-dev-runner.service': unit,
    })
    print('Initialized /srv/awdp-dev only. Admin password: /srv/awdp-dev/admin-password.txt (keep private).')

if __name__ == '__main__':
    main()
