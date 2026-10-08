import contextlib
import io
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'awdp/deploy'))
import stage_files

spec = importlib.util.spec_from_file_location('development_init',
    Path(__file__).resolve().parents[1] / 'awdp/deploy/init.py')
development = importlib.util.module_from_spec(spec)
spec.loader.exec_module(development)


class StagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.destination = self.parent / 'runtime'

    def publish(self):
        stage_files.publish_private_directory(self.destination, ['queue/pending', 'config'],
                                              {'config/settings.json': '{"value":"测试"}\n'})

    def test_success_publishes_complete_directory(self):
        self.publish()
        self.assertTrue((self.destination / 'queue/pending').is_dir())
        self.assertEqual((self.destination / 'config/settings.json').read_bytes(),
                         '{"value":"测试"}\n'.encode('utf-8'))
        self.assertEqual(list(self.parent.glob('.runtime.prepare-*')), [])
        if os.name == 'posix':
            self.assertEqual(self.destination.stat().st_mode & 0o777, 0o700)
            self.assertEqual((self.destination / 'config/settings.json').stat().st_mode & 0o777, 0o600)

    def test_existing_destination_preserved(self):
        self.destination.mkdir()
        (self.destination / 'keep').write_bytes(b'user file')
        with self.assertRaises(FileExistsError):
            self.publish()
        self.assertEqual((self.destination / 'keep').read_bytes(), b'user file')

    def test_write_failure_allows_retry_and_retains_private_stage(self):
        with contextlib.redirect_stderr(io.StringIO()), patch.object(Path, 'open', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.publish()
        self.assertFalse(self.destination.exists())
        self.assertEqual(len(list(self.parent.glob('.runtime.prepare-*'))), 1)
        self.publish()
        self.assertTrue(self.destination.is_dir())

    def test_unsafe_paths_rejected_before_staging(self):
        for relative in ('../escape', '/absolute', 'x/../../escape', 'x\\escape', 'C:escape'):
            with self.subTest(path=relative), self.assertRaises(ValueError):
                stage_files.publish_private_directory(self.destination, [], {relative: 'data'})
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_new_destination_during_staging_not_overwritten(self):
        rename = Path.rename
        original_open = Path.open
        def concurrent_open(path, *args, **kwargs):
            self.destination.mkdir(exist_ok=True)
            return original_open(path, *args, **kwargs)
        with contextlib.redirect_stderr(io.StringIO()), patch.object(Path, 'open', concurrent_open):
            with self.assertRaises(FileExistsError):
                self.publish()
        self.assertTrue(self.destination.is_dir())
        self.assertEqual(list(self.destination.iterdir()), [])
        self.assertEqual(Path.rename, rename)

    def test_development_init_writes_complete_temp_fixture(self):
        with patch.object(development, 'ROOT', self.destination), patch.object(
                development.os, 'geteuid', return_value=0, create=True), patch.object(
                development.os, 'umask'), patch.object(development, 'image_id', return_value='sha256:' + 'a' * 64), contextlib.redirect_stdout(io.StringIO()):
            development.main()
        self.assertTrue((self.destination / 'config/platform.json').is_file())
        self.assertTrue((self.destination / 'runner/awdp_runner.py').is_file())
        self.assertTrue((self.destination / 'awdp-dev-runner.service').is_file())
        self.assertTrue((self.destination / 'queue/pending').is_dir())

    def test_development_init_refuses_existing_directory(self):
        self.destination.mkdir()
        with patch.object(development, 'ROOT', self.destination), patch.object(
                development.os, 'geteuid', return_value=0, create=True), self.assertRaises(SystemExit):
            development.main()
        self.assertEqual(list(self.destination.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
