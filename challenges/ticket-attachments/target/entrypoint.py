import os
import pathlib
import secrets
import shutil
import subprocess


def fixtures(root, flag):
    attachments = root / 'attachments'
    (attachments / 'tickets' / '1042').mkdir(parents=True)
    files = {'welcome.txt': b'Welcome to HelpDesk\n',
             'tickets/1042/report.txt': b'Ticket 1042: repaired\n',
             'release..notes.txt': b'Two dots inside a filename are valid\n',
             'space name.txt': b'Spaces are valid\n',
             'empty.txt': b'',
             'binary.bin': bytes(range(256))}
    for name, payload in files.items():
        (attachments / name).write_bytes(payload)
    for _ in range(3):
        name = 'tickets/1042/' + secrets.token_hex(8) + '.txt'
        (attachments / name).write_text(secrets.token_hex(24), encoding='utf-8')
    (root / 'flag.txt').write_text(flag + '\n', encoding='utf-8')
    (root / 'private.txt').write_text(secrets.token_hex(32), encoding='utf-8')
    sibling = root / 'attachments-private'
    sibling.mkdir()
    (sibling / 'secret.txt').write_text(secrets.token_hex(32), encoding='utf-8')
    (attachments / 'external-link.txt').symlink_to(root / 'private.txt')
    return attachments


def main():
    work = pathlib.Path('/work/submission')
    work.mkdir()
    shutil.copytree('/opt/challenge/src', str(work / 'src'))
    if os.environ.get('TICKET_MODE') != 'attack':
        result = subprocess.run(['patch', '-p1', '--batch', '--forward',
                                 '--reject-file=-', '-i', '/submission/patch.diff'],
                                cwd=str(work), timeout=15)
        if result.returncode:
            raise SystemExit(21)
    flag = os.environ.pop('TICKET_FLAG', 'flag{judge_' + secrets.token_hex(16) + '}')
    root = fixtures(pathlib.Path('/work/runtime'), flag)
    os.environ['ATTACHMENT_ROOT'] = str(root)
    os.chdir(str(work))
    os.execv('/usr/bin/python3', ['python3', str(work / 'src/app.py')])


if __name__ == '__main__':
    main()
