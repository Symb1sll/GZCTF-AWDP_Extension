#!/usr/bin/env python3
"""Run only after creating a NEW game/challenge in the development platform."""
import argparse
import json
import pathlib

p = argparse.ArgumentParser()
p.add_argument('--game', required=True, type=int)
p.add_argument('--challenge', required=True, type=int)
args = p.parse_args()
if args.game <= 0 or args.challenge <= 0:
    p.error('IDs must be positive')
path = pathlib.Path('/srv/awdp-dev/config/platform.json')
data = json.loads(path.read_text())
mapping = data['Awdp']['Challenges'].setdefault(str(args.game), {})
key = str(args.challenge)
if key in mapping:
    raise SystemExit('Mapping already exists; not overwritten')
mapping[key] = 'ticket-attachments'
data['Awdp']['Scores'].setdefault(str(args.game), {})[key] = 100
# Stop the test web container before invoking this script; file bind mount remains valid.
with path.open('w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
print('Test mapping saved. Start the test web service to load it.')
