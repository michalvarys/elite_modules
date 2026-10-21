import datetime as dt
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'backup_import.py'
spec = importlib.util.spec_from_file_location('backup_import', MODULE)
m = importlib.util.module_from_spec(spec)
if MODULE.exists():
    spec.loader.exec_module(m)


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_part_is_not_ready(self):
        self.assertFalse(m.is_ready(self.root / 'WINVET_zaloha_21.10.2026_04-03.zip.part'))

    def test_ready_must_be_regular_not_symlink(self):
        p = self.root / 'WINVET_zaloha_21.10.2026_04-03.zip'
        p.write_bytes(b'zip')
        self.assertTrue(m.is_ready(p))
        alias = self.root / 'alias.zip'
        alias.symlink_to(p)
        self.assertFalse(m.is_ready(alias))

    def test_timestamp_and_rollback(self):
        now = dt.datetime(2026, 10, 21, 8, tzinfo=m.PRAGUE)
        stamp = m.backup_time('WINVET_zaloha_21.10.2026_04-03.zip', now, 36)
        self.assertEqual(stamp.hour, 4)
        with self.assertRaises(ValueError):
            m.backup_time('WINVET_zaloha_19.10.2026_04-03.zip', now, 36)
        with self.assertRaises(ValueError):
            m.ensure_newer(stamp.isoformat(), {'last_backup': stamp.isoformat()})

    def make_zip(self, entries):
        path = self.root / 'test.zip'
        with zipfile.ZipFile(path, 'w') as z:
            for name, content in entries:
                z.writestr(name, content)
        return path

    def test_extract_single_fbk(self):
        p = self.make_zip([('folder/source.fbk', b'backup')])
        out = self.root / 'source.fbk'
        m.extract_fbk(p, out, 100)
        self.assertEqual(out.read_bytes(), b'backup')

    def test_reject_traversal_multiple_and_oversize(self):
        for entries, limit in [([('../source.fbk', b'x')], 100),
                               ([('a.fbk', b'x'), ('b.fbk', b'y')], 100),
                               ([('a.fbk', b'12345')], 4)]:
            with self.subTest(entries=entries):
                with self.assertRaises(ValueError):
                    m.extract_fbk(self.make_zip(entries), self.root / 'out.fbk', limit)

    def test_counts_stop_empty_or_large_drop(self):
        with self.assertRaises(ValueError):
            m.validate_counts({'owners': 0}, {'owners': 20}, {'owners': 1}, .8)
        with self.assertRaises(ValueError):
            m.validate_counts({'owners': 70}, {'owners': 100}, {'owners': 1}, .8)
        m.validate_counts({'owners': 90}, {'owners': 100}, {'owners': 1}, .8)

    def test_state_atomic_and_dedup(self):
        p = self.root / 'state.json'
        m.save_state(p, {'processed': ['abc']})
        self.assertEqual(m.load_state(p)['processed'], ['abc'])
        self.assertFalse(p.with_suffix('.tmp').exists())

    def test_partial_import_cannot_be_replaced_by_older_snapshot(self):
        with self.assertRaises(ValueError):
            m.ensure_newer('2026-10-21T04:03:00+02:00',
                           {'last_started_backup': '2026-10-22T04:03:00+02:00'})
        m.ensure_newer('2026-10-22T04:03:00+02:00',
                       {'last_started_backup': '2026-10-22T04:03:00+02:00'})

    def test_skipped_odoo_records_are_not_success(self):
        class Receiver:
            def push(self, payload):
                return {'ok': True, 'skipped': 1}
        with self.assertRaises(ValueError):
            m.StrictClient(Receiver()).push({})

    def options(self):
        inbox = self.root / 'incoming'
        inbox.mkdir()
        return {'state': str(self.root / 'state'), 'inbox': str(inbox),
                'stale_hours': '30', 'retry_seconds': '900'}

    def test_no_backup_is_unhealthy(self):
        self.assertEqual(m.run(self.options()), 1)

    def test_latest_ready_snapshot_only_and_success_not_repeated(self):
        opts = self.options()
        now = dt.datetime.now(m.PRAGUE).replace(second=0, microsecond=0)
        for hours in (1, 2):
            stamp = now - dt.timedelta(hours=hours)
            (Path(opts['inbox']) / stamp.strftime('WINVET_zaloha_%d.%m.%Y_%H-%M.zip')).write_bytes(b'zip')
        (Path(opts['inbox']) / 'unfinished.zip.part').write_bytes(b'partial')
        seen = []
        def importer(path, state, options, state_path=None):
            seen.append(path.name)
            stamp = m.backup_time(path.name, now, 36)
            state.update(last_backup=stamp.isoformat(), processed=['digest'])
        with patch.object(m, 'process', importer):
            self.assertEqual(m.run(opts), 0)
            self.assertEqual(m.run(opts), 0)
        self.assertEqual(seen, [(now - dt.timedelta(hours=1)).strftime('WINVET_zaloha_%d.%m.%Y_%H-%M.zip')])

    def test_failed_import_retries_after_cooldown_and_keeps_watermark(self):
        opts = self.options()
        now = dt.datetime.now(m.PRAGUE)
        path = Path(opts['inbox']) / now.strftime('WINVET_zaloha_%d.%m.%Y_%H-%M.zip')
        path.write_bytes(b'zip')
        attempts = []
        def importer(path, state, options, state_path=None):
            attempts.append(path)
            state['last_started_backup'] = now.isoformat()
            m.save_state(state_path, state)
            raise ConnectionError('simulated Odoo outage')
        with patch.object(m, 'process', importer):
            self.assertEqual(m.run(opts), 1)
            self.assertEqual(m.run(opts), 1)
            state_path = Path(opts['state']) / 'state.json'
            state = m.load_state(state_path)
            self.assertNotIn('last_backup', state)
            self.assertEqual(state['last_started_backup'], now.isoformat())
            state['retry_at'] = 0
            m.save_state(state_path, state)
            self.assertEqual(m.run(opts), 1)
        self.assertEqual(len(attempts), 2)


if __name__ == '__main__':
    unittest.main()
