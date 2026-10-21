#!/usr/bin/env python3
"""One serialized ZIP -> FBK -> Firebird -> bridge run; driven by systemd timer."""
import argparse
import configparser
import datetime as dt
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
import time
import zipfile
from zoneinfo import ZoneInfo

PRAGUE = ZoneInfo('Europe/Prague')
LOG = logging.getLogger('winvet.backup')
NAME = re.compile(r'^WINVET_zaloha_(\d{2}\.\d{2}\.\d{4}_\d{2}-\d{2})\.zip$', re.I)


class ImportRejected(ValueError):
    """Safe operational message: no source records or credentials."""


def failure_reason(exc):
    return str(exc) if isinstance(exc, ImportRejected) else type(exc).__name__


def is_ready(path):
    return path.suffix.lower() == '.zip' and path.is_file() and not path.is_symlink()


def backup_time(name, now, max_age_hours):
    match = NAME.fullmatch(name)
    if not match:
        raise ImportRejected('Expected WINVET_zaloha_DD.MM.YYYY_HH-MM.zip')
    stamp = dt.datetime.strptime(match[1], '%d.%m.%Y_%H-%M').replace(tzinfo=PRAGUE)
    age = now.timestamp() - stamp.timestamp()
    if age < -300 or age > max_age_hours * 3600:
        raise ImportRejected('Backup timestamp is in the future or too old')
    return stamp


def ensure_newer(stamp, state):
    started = state.get('last_started_backup')
    if started and dt.datetime.fromisoformat(stamp) < dt.datetime.fromisoformat(started):
        raise ImportRejected('Cannot go backwards after a partially imported snapshot')
    previous = state.get('last_backup')
    if previous and dt.datetime.fromisoformat(stamp) <= dt.datetime.fromisoformat(previous):
        raise ImportRejected('Backup is not newer than the last imported snapshot')


def load_state(path):
    return json.loads(path.read_text()) if path.exists() else {}


def save_state(path, state):
    tmp = path.with_suffix('.tmp')
    with tmp.open('w') as stream:
        json.dump(state, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def extract_fbk(path, target, max_bytes):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > 100:
            raise ImportRejected('Too many ZIP entries')
        for info in entries:
            name = PurePosixPath(info.filename)
            if name.is_absolute() or '..' in name.parts or '\\' in info.filename:
                raise ImportRejected('Unsafe ZIP path')
            if stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1:
                raise ImportRejected('Symlink or encrypted ZIP entry')
        files = [i for i in entries if not i.is_dir()]
        if len(files) != 1 or PurePosixPath(files[0].filename).suffix.lower() != '.fbk':
            raise ImportRejected('ZIP must contain exactly one FBK and no other files')
        info = files[0]
        if info.file_size > max_bytes:
            raise ImportRejected('FBK exceeds size limit')
        with archive.open(info) as src, target.open('xb') as out:
            total = 0
            while chunk := src.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise ImportRejected('FBK exceeds size limit')
                out.write(chunk)
        # Reading to EOF verifies the ZIP CRC too.


def validate_counts(counts, previous, minimums, ratio):
    for entity, count in counts.items():
        if count < minimums.get(entity, 0):
            raise ImportRejected(f'{entity}: below configured minimum')
        if previous.get(entity, 0) and count < previous[entity] * ratio:
            raise ImportRejected(f'{entity}: suspicious drop against previous import')


def private_copy(source, target, max_bytes):
    digest = hashlib.sha256()
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as src, target.open('xb') as out:
        before = os.fstat(src.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
            raise ImportRejected('ZIP is not a regular file or exceeds size limit')
        size = 0
        while chunk := src.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                raise ImportRejected('ZIP exceeds size limit')
            out.write(chunk)
            digest.update(chunk)
        after = os.fstat(src.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ImportRejected('ZIP changed during copy; sender must rename only after close')
    return digest.hexdigest()


def docker(container, *args):
    return subprocess.run(['docker', 'exec', container, *args], check=True,
                          capture_output=True, text=True, timeout=1900).stdout.strip()


def preflight(config, state, options, inspect=False):
    from winvet_bridge.db import ReadOnlyDatabase
    from winvet_bridge.sync import make_runner
    with ReadOnlyDatabase(config.firebird) as db:
        runner = make_runner(config, db)
        report = runner.run(full=True, dry_run=True)
        if report.guard.blocked_entities:
            raise ImportRejected('Schema guard blocked one or more entities; review required')
        counts = report.counts()
        rows = db.query_all(options['identity_sql'])
        if len(rows) != 1:
            raise ImportRejected('Identity query must return exactly one stable reference row')
        identity = hashlib.sha256(json.dumps(rows, ensure_ascii=False, default=str).encode()).hexdigest()
        if inspect:
            print(json.dumps({'identity_sha256': identity, 'counts': counts}, indent=2))
            return counts
        if identity != options['identity_sha256']:
            raise ImportRejected('Database identity does not match configured reference')
        validate_counts(counts, state.get('counts', {}), json.loads(options['minimum_counts']),
                        float(options['minimum_ratio']))
        maximum = runner.source.journal_max()
        if maximum < state.get('journal_max', 0):
            raise ImportRejected('Journal moved backwards; verify backup/database before resetting baseline')
        return counts


class StrictClient:
    def __init__(self, client):
        self.client = client

    def status(self, payload):
        return self.client.status(payload)

    def push(self, payload):
        result = self.client.push(payload)
        if result.get('skipped', 0):
            raise ImportRejected('Odoo skipped records; import is incomplete')
        return result


def process(path, state, options, inspect=False, state_path=None):
    from winvet_bridge.config import load_config
    from winvet_bridge.db import ReadOnlyDatabase
    from winvet_bridge.odoo_client import make_client
    from winvet_bridge.sync import make_runner

    now = dt.datetime.now(PRAGUE)
    stamp = backup_time(path.name, now, float(options['max_age_hours']))
    if not inspect:
        ensure_newer(stamp.isoformat(), state)
    work_root = Path(options['work'])
    if shutil.disk_usage(work_root).free < max(path.stat().st_size * 12, 2 * 1024**3):
        raise ImportRejected('Insufficient free disk space for restore')
    with tempfile.TemporaryDirectory(prefix='job-', dir=work_root) as folder:
        job = Path(folder)
        digest = private_copy(path, job / 'input.zip', int(options['max_zip_bytes']))
        if not inspect and digest in state.get('processed', []):
            raise ImportRejected('ZIP contents already imported under a different filename')
        extract_fbk(job / 'input.zip', job / 'source.fbk', int(options['max_fbk_bytes']))
        container = options['container']
        uid = int(docker(container, 'id', '-u', 'firebird'))
        gid = int(docker(container, 'id', '-g', 'firebird'))
        os.chown(job, uid, gid)
        os.chmod(job, 0o700)
        os.chown(job / 'source.fbk', uid, gid)
        os.chmod(job / 'source.fbk', 0o400)
        remote = '/work/' + job.name
        # The remote server creates the DB as firebird. Never replace an existing DB.
        docker(container, 'timeout', '--signal=TERM', '1800', '/opt/firebird/bin/gbak',
               '-create_database', '-user', 'SYSDBA', '-fetch_password',
               '/run/secrets/firebird_password', remote + '/source.fbk',
               'localhost:' + remote + '/restored.fdb')
        config = load_config(Path(options['bridge_config']))
        config.firebird.dsn = options['dsn_prefix'] + remote + '/restored.fdb'
        config.source = 'backup'
        config.state_file = job / 'bridge_state.json'  # every backup is a FULL snapshot
        counts = preflight(config, state, options, inspect)
        if inspect:
            return None
        config.require_odoo()
        if not config.odoo.url.startswith('https://'):
            raise ImportRejected('Production Odoo URL must use HTTPS')
        state['last_started_backup'] = stamp.isoformat()
        save_state(state_path, state)  # persist watermark BEFORE first Odoo write
        client = StrictClient(make_client(config.odoo))
        with ReadOnlyDatabase(config.firebird) as db:
            runner = make_runner(config, db, client)
            report = runner.run(full=True)
            journal_max = runner.source.journal_max()
            if report.guard.blocked_entities or any(e.unsupported for e in report.entities):
                raise ImportRejected('Not all entities imported; install receiving modules / review guard')
        state.update(last_backup=stamp.isoformat(), last_success=dt.datetime.now(PRAGUE).isoformat(), counts=counts,
                     journal_max=journal_max,
                     processed=state.get('processed', []) + [digest])
        return digest


def run(options, inspect_path=None):
    root = Path(options['state'])
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    with (root / 'worker.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            LOG.info('Another import is running')
            return 0
        state_path = root / 'state.json'
        state = load_state(state_path)
        if inspect_path:
            process(Path(inspect_path), state, options, inspect=True)
            return 0
        errors = False
        inbox = Path(options['inbox'])
        # Strict filename timestamp order, not upload mtime. Newest snapshot is enough.
        ready = [p for p in inbox.iterdir() if is_ready(p)]
        candidates = []
        for path in ready:
            if not NAME.fullmatch(path.name):
                LOG.error('Unrecognized filename: %r', path.name)
                errors = True
                continue
            stamp = dt.datetime.strptime(NAME.fullmatch(path.name)[1], '%d.%m.%Y_%H-%M')
            candidates.append((stamp, path))
        candidates.sort(reverse=True)
        if candidates:
            _, path = candidates[0]
            failure_key = f'{path.name}:{path.stat().st_size}:{path.stat().st_mtime_ns}'
            if state.get('retry_key') != failure_key or time.time() >= state.get('retry_at', 0):
                try:
                    # Historical/duplicate files remain in inbox until the sender removes them.
                    stamp = dt.datetime.strptime(NAME.fullmatch(path.name)[1], '%d.%m.%Y_%H-%M').replace(tzinfo=PRAGUE)
                    previous = state.get('last_backup')
                    if not previous or stamp > dt.datetime.fromisoformat(previous):
                        process(path, state, options, state_path=state_path)
                        state.pop('last_error', None)
                        state['retry_at'] = 0
                        save_state(state_path, state)
                        LOG.info('Full import completed: %s', path.name)
                except Exception as exc:
                    # Never persist subprocess output / personal records / credentials.
                    LOG.error('Import failed: %s (%s)', path.name, failure_reason(exc))
                    state.update(last_error=failure_reason(exc), retry_key=failure_key,
                                 retry_at=time.time() + int(options['retry_seconds']))
                    save_state(state_path, state)
                    errors = True
        last = state.get('last_backup')
        if not last or (dt.datetime.now(PRAGUE) - dt.datetime.fromisoformat(last)).total_seconds() > float(options['stale_hours']) * 3600:
            LOG.error('No successfully imported fresh backup (limit %sh)', options['stale_hours'])
            errors = True
        if state.get('last_error'):
            errors = True
        return 1 if errors else 0


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--inspect', help='Restore and dry-run only; print identity hash and counts')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    # Existing bridge can log detailed data errors. Keep worker journal to generic errors/counts.
    logging.getLogger('winvet_bridge').setLevel(logging.CRITICAL)
    conf = configparser.ConfigParser(interpolation=None)
    conf.read(args.config)
    try:
        return run(conf['import'], args.inspect)
    except Exception as exc:
        LOG.error('Worker failed (%s); inspect configuration, Docker and disk space', failure_reason(exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
