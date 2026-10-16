#!/usr/bin/env python3
"""Offline regression checks. Never call systemctl/docker or touch /etc."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import go_numa as g


class RecipeTests(unittest.TestCase):
    def test_affinity_accepts_nginx_single_cpu_and_rejects_escape(self):
        self.assertTrue(g.allowed('96'))
        self.assertTrue(g.allowed('96-127,190-191'))
        for invalid in ['', '0-383', '95-191', '192']:
            self.assertFalse(g.allowed(invalid))

    def test_mapping_and_persistent_helper(self):
        files = g.proposed(Path('/data/private-go-numa'))
        self.assertEqual(len(files), 39)
        self.assertEqual(sum('Environment=GOGC=800' in c for c in files.values()), 1)
        self.assertEqual(sum('ExecStartPost=' in c for c in files.values()), 8)
        self.assertTrue(all('NUMAMask=1' in c for p, c in files.items() if p.endswith(g.DROP)))
        self.assertTrue(all('96-191' in c for p, c in files.items() if p.endswith('50-AllowedCPUs.conf')))

    def test_plan_avoids_pull_and_container_wrapper_restarts(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp).resolve()
            meta = {'managed': {p: {'content': c} for p, c in g.proposed(state).items()},
                    'files': {p: {'exists': False} for p in g.proposed(state)}}
            commands = g.plan(state, meta)
            restarts = [c for c in commands if c[:2] == ['systemctl', 'restart']]
            self.assertEqual([c[2] for c in restarts], [g.unit(c) for c in g.NATIVE])
            self.assertFalse(any('pull' in c for c in commands))
            wait_index = next(i for i, c in enumerate(commands) if c[0] == 'WAIT')
            self.assertGreater(commands.index(['systemctl', 'start', g.unit('cube-egress')]), wait_index)
            self.assertLess(commands.index(['systemctl', 'stop', g.unit('cube-egress')]), commands.index(['systemctl', 'restart', g.unit('cubelet')]))

    def fixture(self, state):
        first, second, unrelated = (state / p for p in ['original.conf', 'new.conf', 'unrelated.conf'])
        first.write_text('original exact bytes\n')
        unrelated.write_text('do not change\n')
        helper = state / 'container_cpuset.py'
        helper.write_text('# fixture\n')
        original = g.describe_file(str(first))
        backup = state / 'backup' / str(first).lstrip('/')
        backup.parent.mkdir(parents=True)
        backup.write_bytes(first.read_bytes())
        (state / 'runtime-before.json').write_text(json.dumps({'containers': {}}))
        meta = {'status': 'snapshot_complete', 'files': {str(first): original, str(second): {'exists': False}},
                'managed': {str(first): {'content': 'candidate1\n', 'sha256': g.digest(b'candidate1\n')},
                            str(second): {'content': 'candidate2\n', 'sha256': g.digest(b'candidate2\n')}},
                'helper_sha256': g.digest(helper.read_bytes()), 'writes_started': []}
        return meta, first, second, unrelated

    def test_partial_apply_failure_restores_only_own_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp).resolve()
            meta, first, second, unrelated = self.fixture(state)
            real_install = g.atomic_install
            def fail_second(path, data, *args):
                if path == str(second):
                    raise OSError('injected disk write failure')
                return real_install(path, data, *args)
            with patch.object(g.os, 'chown'), patch.object(g, 'atomic_install', side_effect=fail_second), patch.object(g, 'run', return_value='active'), patch.object(g, 'readiness'), patch.object(g.runtime_snapshot, 'snapshot', return_value={}):
                with self.assertRaisesRegex(RuntimeError, 'original configuration restored'):
                    g.apply(state, meta)
            self.assertEqual(first.read_text(), 'original exact bytes\n')
            self.assertFalse(second.exists())
            self.assertEqual(unrelated.read_text(), 'do not change\n')
            self.assertEqual(meta['status'], 'restored_config_and_basic_health')
            self.assertIn('injected disk write failure', meta['apply_error'])

    def test_late_apply_failure_restores_empty_container_cpuset(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp).resolve()
            meta, first, second, unrelated = self.fixture(state)
            old = {'cube-proxy': {'id': 'original-id', 'image': 'sha256:fixed', 'cpus': '', 'mems': ''}}
            (state / 'runtime-before.json').write_text(json.dumps({'containers': old}))
            commands = []
            def command(args, **kwargs):
                commands.append(args)
                if args[:2] == ['docker', 'inspect']:
                    return json.dumps([{'Id': 'original-id', 'Image': 'sha256:fixed', 'State': {'Running': True}, 'HostConfig': {'CpusetCpus': '', 'CpusetMems': ''}}])
                return 'active'
            with patch.object(g.os, 'chown'), patch.object(g, 'run', side_effect=command), patch.object(g, 'readiness', side_effect=[RuntimeError('injected bootstrap timeout'), None]), patch.object(g.runtime_snapshot, 'snapshot', return_value={}):
                with self.assertRaisesRegex(RuntimeError, 'original configuration restored'):
                    g.apply(state, meta)
            self.assertEqual(first.read_text(), 'original exact bytes\n')
            self.assertFalse(second.exists())
            self.assertIn(['docker', 'update', '--cpuset-cpus', '', '--cpuset-mems', '', 'cube-proxy'], commands)
            for c in g.NATIVE:
                self.assertEqual(commands.count(['systemctl', 'restart', g.unit(c)]), 2)
            self.assertEqual(commands.count(['systemctl', 'daemon-reload']), 2)
            self.assertEqual(meta['status'], 'restored_config_and_basic_health')
            self.assertIn('injected bootstrap timeout', meta['apply_error'])

    def test_restore_preserves_external_edit_and_reports_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp).resolve()
            meta, first, second, unrelated = self.fixture(state)
            first.write_text('someone else edited this\n')
            second.write_text('candidate2\n')
            meta['writes_started'] = [str(first), str(second)]
            with patch.object(g, 'run', return_value='active'), patch.object(g, 'readiness'), patch.object(g.runtime_snapshot, 'snapshot', return_value={}):
                with self.assertRaisesRegex(RuntimeError, 'Restore incomplete'):
                    g.restore(state, meta)
            self.assertEqual(first.read_text(), 'someone else edited this\n')
            self.assertFalse(second.exists())
            self.assertEqual(meta['status'], 'restore_failed')
            self.assertEqual(unrelated.read_text(), 'do not change\n')

    def test_snapshot_existing_directory_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp).resolve() / 'state.json'
            marker.write_text('existing snapshot')
            with self.assertRaises(FileExistsError):
                g.snapshot(Path(temp).resolve())
            self.assertEqual(marker.read_text(), 'existing snapshot')

    def test_apply_refuses_config_drift_before_mutating(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp).resolve()
            meta, first, second, unrelated = self.fixture(state)
            first.write_text('configuration changed since snapshot\n')
            with patch.object(g, 'run') as command:
                with self.assertRaisesRegex(RuntimeError, 'Configuration drift'):
                    g.apply(state, meta)
                command.assert_not_called()
            self.assertEqual(meta['status'], 'snapshot_complete')
            self.assertFalse(second.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
