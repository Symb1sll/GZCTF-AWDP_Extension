import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('overlay', Path(__file__).with_name('apply_overlay.py'))
overlay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(overlay)


class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.extension, self.upstream = self.root / 'extension', self.root / 'upstream'
        self.upstream.mkdir()
        self.source = self.extension / 'integration/overlay/src/file.cs'
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b'new\n')
        self.target = self.upstream / 'src/file.cs'
        self.target.parent.mkdir()
        self.target.write_bytes(b'old\n')
        self.manifest = {
            'schema_version': 1, 'hash_mode': 'raw-bytes', 'upstream_commit': 'expected-head',
            'files': [{'path': 'src/file.cs', 'original_sha256': overlay.digest(b'old\n'),
                       'overlay_sha256': overlay.digest(b'new\n')}], 'support_files': []}
        self.save_manifest()

    def save_manifest(self):
        (self.extension / 'integration/manifest.json').write_text(json.dumps(self.manifest))

    def run_apply(self, check=False):
        return overlay.apply(self.extension, self.upstream, check=check, source_archive=True)

    def test_check_does_not_write(self):
        self.assertEqual(self.run_apply(check=True), 1)
        self.assertEqual(self.target.read_bytes(), b'old\n')

    def test_apply_and_repeat(self):
        self.assertEqual(self.run_apply(), 1)
        self.assertEqual(self.target.read_bytes(), b'new\n')
        self.assertEqual(self.run_apply(), 0)

    def test_modified_target_refused(self):
        self.target.write_bytes(b'user edit\n')
        with self.assertRaisesRegex(ValueError, 'refusing overwrite'):
            self.run_apply()
        self.assertEqual(self.target.read_bytes(), b'user edit\n')

    def test_tampered_overlay_refused(self):
        self.source.write_bytes(b'tampered\n')
        with self.assertRaisesRegex(ValueError, 'integrity mismatch'):
            self.run_apply()
        self.assertEqual(self.target.read_bytes(), b'old\n')

    def test_wrong_revision_refused(self):
        with patch.object(overlay.subprocess, 'check_output', return_value='wrong-head\n'):
            with self.assertRaisesRegex(ValueError, 'HEAD'):
                overlay.apply(self.extension, self.upstream)

    def test_support_file_installed(self):
        source = self.extension / 'awdp/runner/file.py'
        source.parent.mkdir(parents=True)
        source.write_bytes(b'runner\n')
        self.manifest['support_files'] = [{'path': 'awdp/runner/file.py', 'original_sha256': None,
                                          'overlay_sha256': overlay.digest(b'runner\n')}]
        self.save_manifest()
        self.assertEqual(self.run_apply(), 2)
        self.assertEqual((self.upstream / 'awdp/runner/file.py').read_bytes(), b'runner\n')

    def test_all_validated_before_write(self):
        self.manifest['support_files'] = [{'path': 'awdp/missing.py', 'original_sha256': None,
                                          'overlay_sha256': 'invalid'}]
        self.save_manifest()
        with self.assertRaises(OSError):
            self.run_apply()
        self.assertEqual(self.target.read_bytes(), b'old\n')

    def test_documentation_installed_and_idempotent(self):
        source = self.extension / 'docs/DEPLOYMENT.md'
        source.parent.mkdir()
        source.write_bytes(b'deployment\n')
        self.manifest['support_files'] = [{'path': 'docs/DEPLOYMENT.md', 'original_sha256': None,
                                          'overlay_sha256': overlay.digest(b'deployment\n')}]
        self.save_manifest()
        self.assertEqual(self.run_apply(), 2)
        self.assertEqual((self.upstream / 'docs/DEPLOYMENT.md').read_bytes(), b'deployment\n')
        self.assertEqual(self.run_apply(), 0)

    def test_existing_documentation_preserved(self):
        source = self.extension / 'docs/DEPLOYMENT.md'
        source.parent.mkdir()
        source.write_bytes(b'deployment\n')
        target = self.upstream / 'docs/DEPLOYMENT.md'
        target.parent.mkdir()
        target.write_bytes(b'user documentation\n')
        self.manifest['support_files'] = [{'path': 'docs/DEPLOYMENT.md', 'original_sha256': None,
                                          'overlay_sha256': overlay.digest(b'deployment\n')}]
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'refusing overwrite'):
            self.run_apply()
        self.assertEqual(target.read_bytes(), b'user documentation\n')
        self.assertEqual(self.target.read_bytes(), b'old\n')

    def test_unsafe_and_restricted_paths_refused(self):
        for relative in ('../escape', 'src/../escape', 'src/GZCTF/Services/Container/Manager/X.cs',
                         'src/GZCTF/ClientApp/src/hooks/useConfig.ts'):
            with self.subTest(path=relative), self.assertRaises(ValueError):
                overlay.safe_path(self.upstream, relative)

    def test_write_failure_restores_original(self):
        original_write = overlay.atomic_write
        calls = 0
        def fail_once(path, data, mode):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError('simulated write failure')
            original_write(path, data, mode)
        with patch.object(overlay, 'atomic_write', side_effect=fail_once):
            with self.assertRaises(OSError):
                self.run_apply()
        self.assertEqual(self.target.read_bytes(), b'old\n')


if __name__ == '__main__':
    unittest.main()
