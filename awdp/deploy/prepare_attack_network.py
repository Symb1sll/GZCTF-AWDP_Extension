#!/usr/bin/env python3
"""Prepare or validate the existing AWDP development attack network."""
import argparse
import json
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--check', action='store_true', help='Validate without creating a network')
args = parser.parse_args()
name = 'gzctf-awdp-dev-attack'
options = {
    'com.docker.network.bridge.enable_icc': 'false',
    'com.docker.network.bridge.host_binding_ipv4': '127.0.0.1',
}
config = json.loads(Path('/srv/awdp-dev/config/platform.json').read_text())
if config['ContainerProvider']['DockerConfig']['ChallengeNetwork'] != name:
    raise SystemExit('ChallengeNetwork mismatch; no changes made')
names = subprocess.check_output(['docker', 'network', 'ls', '--format', '{{.Name}}'], text=True).splitlines()
if name not in names:
    if args.check:
        raise SystemExit('Attack network missing; run prepare_attack_network.py without --check')
    command = ['docker', 'network', 'create', '--driver', 'bridge']
    for key, value in options.items():
        command += ['--opt', key + '=' + value]
    subprocess.run(command + [name], check=True)
network = json.loads(subprocess.check_output(['docker', 'network', 'inspect', name], text=True))[0]
if network['Driver'] != 'bridge' or network['Internal'] or network.get('Ingress', False):
    raise SystemExit('Attack network type mismatch; existing network left unchanged')
if any((network.get('Options') or {}).get(key) != value for key, value in options.items()):
    raise SystemExit('Attack network options mismatch; existing network left unchanged')
print('Attack network and ChallengeNetwork verified: ' + name)
