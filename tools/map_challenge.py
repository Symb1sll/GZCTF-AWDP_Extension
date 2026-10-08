#!/usr/bin/env python3
"""Bind an existing production GZCTF challenge; run as root during idle time."""
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path('/srv/awdp/gzctf-prod')
WEB = 'gzctf-gzctf-1'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=int, required=True)
    parser.add_argument('--challenge', type=int, required=True)
    args = parser.parse_args()
    if os.geteuid() != 0 or min(args.game, args.challenge) <= 0:
        parser.error('Run as root with positive game/challenge IDs')
    if not os.path.ismount('/srv/awdp'):
        raise SystemExit('/srv/awdp is not mounted')
    os.umask(0o077)
    with (ROOT / '.map.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = ROOT / 'config/platform.json'
        original = path.read_bytes()
        data = json.loads(original)
        awdp = data['Awdp']
        if awdp.get('Root') != str(ROOT) or awdp.get('Enabled') is not True:
            raise SystemExit('Unexpected production AWDP configuration')
        game, challenge = str(args.game), str(args.challenge)
        mapping = awdp['Challenges'].setdefault(game, {})
        scores = awdp['Scores'].setdefault(game, {})
        if challenge in mapping or challenge in scores:
            raise SystemExit('Existing mapping/score; nothing overwritten')
        judges = json.loads((ROOT / 'config/challenges.json').read_text())['challenges']
        matches = [j for j in judges if j['id'] == 'ticket-attachments' and j.get('enabled', True)]
        if len(matches) != 1:
            raise SystemExit('Expected enabled ticket-attachments judge missing')
        for field in ('target_image_id', 'checker_image_id'):
            subprocess.run(['docker', 'image', 'inspect', matches[0][field]],
                           check=True, stdout=subprocess.DEVNULL)
        live = json.loads(subprocess.check_output(['docker', 'inspect', WEB], text=True))[0]
        if not live['State']['Running']:
            raise SystemExit('Production Web is not running; investigate first')
        if not any(m['Source'] == str(path) and m['Destination'] == '/app/appsettings.json'
                   for m in live['Mounts']):
            raise SystemExit('Production configuration mount mismatch')
        mapping[challenge] = 'ticket-attachments'
        scores[challenge] = 100
        payload = (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode()
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-%fUTC')
        backup = path.with_name(path.name + '.bak-' + stamp)
        shutil.copy2(path, backup)
        print('Configuration backup: ' + str(backup), flush=True)
        try:
            subprocess.run(['docker', 'stop', WEB], check=True)
            if path.read_bytes() != original:
                raise RuntimeError('Configuration changed concurrently; no write performed')
            try:
                # Preserve the inode used by the existing single-file Docker bind mount.
                with path.open('wb') as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
            except BaseException:
                with path.open('wb') as stream:
                    stream.write(original)
                    stream.flush()
                    os.fsync(stream.fileno())
                raise
        finally:
            subprocess.run(['docker', 'start', WEB], check=True)
        print('Binding saved: game={} challenge={} judge=ticket-attachments fix=100'.format(game, challenge))
        print('Web start requested; browser acceptance is still required.')


if __name__ == '__main__':
    main()
