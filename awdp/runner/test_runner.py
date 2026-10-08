import importlib.util
import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('runner', pathlib.Path(__file__).with_name('awdp_runner.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def diff(path):
    return ('--- a/' + path + '\n+++ b/' + path + '\n@@ -1 +1 @@\n-a\n+b\n').encode()


class RunnerTests(unittest.TestCase):
    def test_exact_file(self):
        runner.validate_patch(diff('src/app.py'), ['src/app.py'])

    def test_prefix_bypass_rejected(self):
        with self.assertRaises(ValueError):
            runner.validate_patch(diff('src/app.py.evil'), ['src/app.py'])

    def test_directory_allowlist(self):
        runner.validate_patch(diff('src/nested/app.py'), ['src/'])

    def test_traversal(self):
        with self.assertRaises(ValueError):
            runner.validate_patch(diff('../secret'), ['src/'])

    def test_cleanup_is_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(runner, 'QUEUE_DIR', pathlib.Path(directory)), patch.object(runner, 'run_command') as run:
                run.return_value = subprocess.CompletedProcess([], 0, '')
                runner.recover_previous_jobs()
                args = run.call_args.args[0]
                self.assertIn('label=gzctf.awdp.dev.managed=true', args)
                self.assertNotIn('label=awdp.managed=true', args)

    def test_result_protocol(self):
        self.assertTrue(runner.parse_checker('AWDP_RESULT={"passed":true}')['passed'])
        with self.assertRaises(ValueError):
            runner.parse_checker('no result')

    def test_result_carries_server_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / 'running').mkdir()
            (root / 'results').mkdir()
            job = {'team_id': 'g1-p2', 'challenge_id': 'ticket', 'patch_sha256': 'hash'}
            (root / 'running/job.json').write_text(json.dumps(job))
            with patch.object(runner, 'QUEUE_DIR', root):
                runner.write_result('job', {'status': 'passed', 'team_id': 'spoof'})
            result = json.loads((root / 'results/job.json').read_text())
            self.assertEqual(result['team_id'], 'g1-p2')
            self.assertEqual(result['patch_sha256'], 'hash')

    def test_malformed_job_emits_unbound_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / 'running').mkdir()
            (root / 'results').mkdir()
            (root / 'running/job.json').write_text('not JSON')
            with patch.object(runner, 'QUEUE_DIR', root):
                runner.write_result('job', {'status': 'error'})
            result = json.loads((root / 'results/job.json').read_text())
            self.assertEqual(result['status'], 'error')
            self.assertIsNone(result['team_id'])


if __name__ == '__main__':
    unittest.main()
