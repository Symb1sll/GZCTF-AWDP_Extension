"""Generate player archive and reference patches; run local HTTP regression."""
import difflib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tarfile
import tempfile
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
ORIGINAL = (ROOT / 'target/src/app.py').read_text(encoding='utf-8')
OLD = '    return (ROOT / name).read_bytes()\n'
FIX = '''    base = ROOT.resolve()
    candidate = (base / name).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        raise ValueError('outside attachment directory')
    if not candidate.is_file():
        raise ValueError('not a file')
    return candidate.read_bytes()
'''


def main():
    if ORIGINAL.count(OLD) != 1:
        raise SystemExit('Unexpected original source; refusing to generate reference patches')
    (ROOT / 'examples').mkdir(exist_ok=True)
    variants = {'good-fix': ORIGINAL.replace(OLD, FIX),
                'bad-fix': ORIGINAL.replace(OLD, '    # Keep the current behavior.\n' + OLD),
                'disable-download': ORIGINAL.replace(OLD, "    raise ValueError('disabled')\n")}
    for name, text in variants.items():
        patch = ''.join(difflib.unified_diff(ORIGINAL.splitlines(True), text.splitlines(True),
                                           fromfile='a/src/app.py', tofile='b/src/app.py'))
        with (ROOT / 'examples' / (name + '.patch')).open('w', encoding='utf-8', newline='\n') as stream:
            stream.write(patch)
    # Portable HTTP regression. Linux symlink case is tested in Docker separately.
    for name, code in [('original', ORIGINAL)] + list(variants.items()):
        with tempfile.TemporaryDirectory(prefix='ticket-regression-') as directory:
            runtime = pathlib.Path(directory)
            spec = importlib.util.spec_from_file_location('fixtures', ROOT / 'target/entrypoint.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            symlink_supported = True
            try:
                module.fixtures(runtime, 'flag{local-test-only}')
            except OSError as exc:
                if getattr(exc, 'winerror', None) != 1314:
                    raise
                symlink_supported = False
            namespace = {'__name__': 'ticket_test'}
            exec(compile(code, name, 'exec'), namespace)
            namespace['ROOT'] = runtime / 'attachments'
            server = namespace['http'].server.ThreadingHTTPServer(('127.0.0.1', 0), namespace['Handler'])
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                env = dict(os.environ, CHECK_BASE='http://127.0.0.1:' + str(server.server_port),
                           PYTHONIOENCODING='utf-8')
                checked = subprocess.run([sys.executable, str(ROOT / 'checker/checker.py')],
                                         env=env, capture_output=True, timeout=30)
                output = checked.stdout.decode('utf-8')
                expected = 0 if name == 'good-fix' else 1
                messages = [line[len('AWDP_RESULT='):] for line in output.splitlines()
                            if line.startswith('AWDP_RESULT=')]
                if len(messages) != 1:
                    raise SystemExit('checker did not emit exactly one result: ' + name)
                protocol = json.loads(messages[0])
                if protocol.get('passed') is not (expected == 0):
                    raise SystemExit('checker result did not match the scenario: ' + name)
                print(name, 'PASS' if checked.returncode == expected else 'FAIL', output.strip())
                if checked.returncode != expected:
                    raise SystemExit('regression failed')
                if not symlink_supported:
                    print('NOTE: Windows symlink creation unavailable; Linux container test required.')
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
    with tarfile.open(ROOT / 'ticket-player.tar.gz', 'w:gz') as archive:
        archive.add(ROOT / 'target/src/app.py', arcname='ticket-player/src/app.py')
        archive.add(ROOT / 'PLAYER.md', arcname='ticket-player/README.md')
    print('Player archive contains only source and player instructions.')


if __name__ == '__main__':
    main()
