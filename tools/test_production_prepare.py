import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('production', Path(__file__).with_name('prepare_gzctf_production.py'))
production = importlib.util.module_from_spec(spec)
spec.loader.exec_module(production)


def marker(version):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as archive:
        payload = version.encode('ascii')
        info = tarfile.TarInfo('version.txt')
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    return stream.getvalue()


class ProductionTests(unittest.TestCase):
    def setUp(self):
        self.config = {'ConnectionStrings': {'Database': 'Host=db;Database=gzctf;Password="x;z"'},
                       'ContainerProvider': {'Type': 'Docker'}}
        self.live = {'Config': {'User': '', 'Env': []}, 'State': {'Running': True},
                     'Mounts': [{'Source': '/root/GZCTF/appsettings.json',
                                 'Destination': '/app/appsettings.json', 'RW': False}],
                     'NetworkSettings': {'Networks': {'control': {}}}}
        self.db = {'State': {'Running': True},
                   'NetworkSettings': {'Networks': {'control': {'Aliases': ['db']}}}}
        self.migrations = json.loads((production.EXTENSION / 'integration/manifest.json').read_text(
            encoding='utf-8'))['upstream_migrations']

    def check_baseline(self, version='1.2.5.0', migrations=None):
        migrations = self.migrations if migrations is None else migrations
        with patch.object(production, 'runtime_version', return_value=version), patch.object(
                production.subprocess, 'check_output', side_effect=[json.dumps([self.db]), '\n'.join(migrations)]):
            with contextlib.redirect_stdout(io.StringIO()):
                production.check_baseline(self.config, self.live)

    def test_connection_parser_preserves_quoted_values(self):
        fields = production.connection_fields('Host=db;Database="gzctf";Password="a;""b"; Username=postgres')
        self.assertEqual(fields['password'], 'a;"b')
        self.assertEqual(fields['database'], 'gzctf')
        self.assertEqual(fields['username'], 'postgres')

    def test_json_comments_and_trailing_commas_preserve_strings(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'config.json'
            config.write_text('{// comment\n"Url":"https://example.invalid/a//b",/* block */"Value":1,}', encoding='utf-8')
            self.assertEqual(production.read_config(config), {'Url': 'https://example.invalid/a//b', 'Value': 1})

    def test_malformed_connection_refused_without_disclosing_password(self):
        for value in ('Host=db;Host=other', 'Password="secret', 'bad', 'Database="gzctf"oops'):
            with self.subTest(value=value), self.assertRaises(ValueError) as result:
                production.connection_fields(value)
            self.assertNotIn('secret', str(result.exception))

    def test_runtime_version_uses_tar_without_extracting(self):
        with patch.object(production.subprocess, 'check_output', return_value=marker('1.2.5.0')):
            self.assertEqual(production.runtime_version('web'), '1.2.5.0')

    def test_invalid_version_archive_refused(self):
        with patch.object(production.subprocess, 'check_output', return_value=b'x' * 65537):
            with self.assertRaises(ValueError):
                production.runtime_version('web')

    def test_matching_baseline_accepted(self):
        self.check_baseline()

    def test_other_web_version_refused(self):
        with self.assertRaisesRegex(SystemExit, 'baseline'):
            self.check_baseline(version='1.3.0')

    def test_missing_or_newer_migrations_refused(self):
        for migrations in (self.migrations[:-1], self.migrations + ['20260920053850_AddAwdpSubmissionLedger']):
            with self.subTest(migrations=migrations), self.assertRaisesRegex(SystemExit, 'migration history'):
                self.check_baseline(migrations=migrations)

    def test_remote_provider_refused(self):
        self.config['ContainerProvider']['DockerConfig'] = {'Uri': 'tcp://remote:2375'}
        with self.assertRaisesRegex(SystemExit, 'local Docker'):
            self.check_baseline()

    def test_wrong_database_host_refused(self):
        self.config['ConnectionStrings']['Database'] = 'Host=remote;Database=gzctf'
        with self.assertRaisesRegex(SystemExit, 'original database'):
            self.check_baseline()

    def test_environment_connection_override_refused(self):
        self.live['Config']['Env'] = ['ConnectionStrings__Database=private-value']
        with self.assertRaisesRegex(SystemExit, 'Environment overrides'):
            self.check_baseline()

    def test_different_configuration_mount_refused(self):
        self.live['Mounts'][0]['Source'] = '/other/config.json'
        with self.assertRaisesRegex(SystemExit, 'config mount'):
            self.check_baseline()

    def test_database_connection_uri_refused(self):
        self.config['ConnectionStrings']['Database'] = 'Host=db;Database=postgresql://remote/example'
        with self.assertRaisesRegex(SystemExit, 'database name'):
            self.check_baseline()

    def test_rootless_or_missing_apparmor_refused(self):
        for security in (['name=rootless', 'name=apparmor'], []):
            info = {'OSType': 'linux', 'SecurityOptions': security}
            with self.subTest(security=security), patch.object(Path, 'is_socket', return_value=True), patch.dict(
                    production.os.environ, {}, clear=True), patch.object(production.subprocess, 'check_output',
                    side_effect=['unix:///var/run/docker.sock', json.dumps(info)]), self.assertRaises(SystemExit):
                production.check_host()

    def test_remote_docker_context_refused(self):
        with patch.object(Path, 'is_socket', return_value=True), patch.dict(production.os.environ, {}, clear=True), patch.object(
                production.subprocess, 'check_output', return_value='tcp://remote:2375'), self.assertRaisesRegex(SystemExit, 'same local socket'):
            production.check_host()

    def test_local_rootful_host_accepted(self):
        info = {'OSType': 'linux', 'SecurityOptions': ['name=apparmor', 'name=seccomp,profile=builtin']}
        with patch.object(Path, 'is_socket', return_value=True), patch.dict(production.os.environ, {}, clear=True), patch.object(
                production.subprocess, 'check_output', side_effect=['unix:///var/run/docker.sock', json.dumps(info)]), patch.object(
                production.subprocess, 'run') as run:
            production.check_host()
            run.assert_called_once_with(['systemctl', 'is-active', '--quiet', 'docker.service'], check=True)

    def run_main(self, check=False, compose_failure=False):
        image = 'sha256:' + 'a' * 64
        runner = (production.EXTENSION / 'awdp/runner/awdp_runner.py').read_text(encoding='utf-8')
        judge = {'challenges': [{'id': 'ticket-attachments', 'enabled': True,
                                 'target_image_id': image, 'checker_image_id': image}]}
        def read_text(path, *args, **kwargs):
            if path.name == 'awdp_runner.py':
                return runner
            if path.name == 'challenges.json':
                return json.dumps(judge)
            raise AssertionError('Unexpected file read: ' + str(path))
        def run(command, **kwargs):
            if 'compose' in command:
                self.assertIn('-', command)
                self.assertIn('input', kwargs)
                if compose_failure:
                    raise subprocess.CalledProcessError(1, command)
        argv = ['prepare', '--expected-image-id', image] + (['--check'] if check else [])
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(production.sys, 'argv', argv))
            stack.enter_context(patch.object(production.os, 'geteuid', return_value=0, create=True))
            stack.enter_context(patch.object(production.os, 'umask'))
            stack.enter_context(patch.object(production.os.path, 'ismount', return_value=True))
            stack.enter_context(patch.object(Path, 'exists', return_value=False))
            stack.enter_context(patch.object(Path, 'is_symlink', return_value=False))
            stack.enter_context(patch.object(Path, 'read_text', read_text))
            stack.enter_context(patch.object(production, 'read_config', return_value=self.config))
            stack.enter_context(patch.object(production, 'check_host'))
            stack.enter_context(patch.object(production, 'check_baseline'))
            stack.enter_context(patch.object(production.subprocess, 'check_output', side_effect=[image, json.dumps([self.live])]))
            stack.enter_context(patch.object(production.subprocess, 'run', side_effect=run))
            publish = stack.enter_context(patch.object(production, 'publish_private_directory'))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            if compose_failure:
                with self.assertRaises(subprocess.CalledProcessError):
                    production.main()
                publish.assert_not_called()
            else:
                production.main()
                if check:
                    publish.assert_not_called()
                else:
                    publish.assert_called_once()
                    files = publish.call_args.args[2]
                    config = json.loads(files['config/platform.json'])
                    self.assertEqual({k: v for k, v in config.items() if k != 'Awdp'}, self.config)
                    self.assertEqual(config['Awdp']['Challenges'], {})

    def test_compose_failure_precedes_publication(self):
        self.run_main(compose_failure=True)

    def test_check_does_not_publish(self):
        self.run_main(check=True)

    def test_prepare_preserves_config_and_empty_mappings(self):
        self.run_main()


if __name__ == '__main__':
    unittest.main()
