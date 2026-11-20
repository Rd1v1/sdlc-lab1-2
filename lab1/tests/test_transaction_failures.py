import contextlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from lab1.src import app
from lab1.src.audit import AuditStore
from lab1.src.errors import SafeFileError
from lab1.src.safe_file_manager import SafeFileManager


class FailCommitOnce:
    def __init__(self, connection, fail_on=1):
        self.connection = connection
        self.fail_on = fail_on
        self.commits = 0
        self.before_rollback = None

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def commit(self):
        self.commits += 1
        if self.commits == self.fail_on:
            raise sqlite3.OperationalError('simulated commit failure')
        self.connection.commit()

    def rollback(self):
        if self.before_rollback is not None:
            self.before_rollback()
        self.connection.rollback()


class TransactionFailureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.database = self.base / 'audit.db'
        self.store = AuditStore(self.database)
        self.owner = self.store.create_user('owner', 'review password')
        self.other = self.store.create_user('other', 'review password')
        self.manager = SafeFileManager(self.base / 'files', self.store)
        self.manager.write_text('original.txt', 'old', self.owner)
        self.manager.write_text('existing/keep.txt', 'keep', self.owner)
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as output:
            output.writestr('folder/first.txt', 'first')
            output.writestr('folder/second.txt', 'second')
            output.writestr('empty/', '')
        self.manager.write_bytes('source.zip', archive.getvalue(), self.owner)

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def snapshot(self):
        files = {}
        for path in self.manager.root.rglob('*'):
            if path.is_file():
                data = path.read_bytes()
                info = path.stat()
                files[path.relative_to(self.manager.root).as_posix()] = (
                    data, info.st_mode, info.st_mtime_ns,
                )
            else:
                files[path.relative_to(self.manager.root).as_posix()] = None
        metadata = [tuple(row) for row in self.store._connection.execute('SELECT * FROM Files ORDER BY id')]
        operations = [tuple(row) for row in self.store._connection.execute('SELECT * FROM Operations ORDER BY id')]
        return files, metadata, operations

    def cli(self, arguments, factory=AuditStore):
        output = io.StringIO()
        with patch.object(app, 'DATA_ROOT', self.manager.root), patch.object(
            app, 'AUDIT_DATABASE', self.database
        ), patch.object(app, 'AuditStore', side_effect=factory), patch.object(
            app.getpass, 'getpass', return_value='review password'
        ), contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = app.run(arguments)
        return code, output.getvalue()

    def test_cli_denied_operations_are_audited_without_password_or_content(self):
        for arguments in (
            ['read', 'original.txt'],
            ['write', 'original.txt', '--text', 'private payload must not be logged'],
            ['delete', 'original.txt'],
            ['zip-create', 'blocked.zip', 'original.txt'],
        ):
            with self.subTest(command=arguments[0]):
                code, output = self.cli(arguments + ['--user', 'other'])
                self.assertEqual(code, 2)
                self.assertIn('Нет доступа', output)
                row = self.store._connection.execute('SELECT * FROM Operations ORDER BY id DESC LIMIT 1').fetchone()
                self.assertEqual(row['operation_type'], arguments[0] + '_failed')
                self.assertEqual(row['user_id'], self.other)
                detail = json.loads(row['detail'])
                self.assertEqual(detail['path'], arguments[1])
                self.assertIn('Нет доступа', detail['error'])
                self.assertNotIn('review password', row['detail'])
                self.assertNotIn('private payload', row['detail'])
                if arguments[0] == 'zip-create':
                    self.assertEqual(detail['files'], ['original.txt'])
        self.assertEqual((self.manager.root / 'original.txt').read_text(), 'old')

    def test_cli_invalid_path_and_json_are_audited(self):
        for arguments in (
            ['read', '../outside'],
            ['json-write', 'bad.json', '--value', 'not JSON'],
        ):
            with self.subTest(command=arguments[0]):
                self.assertEqual(self.cli(arguments + ['--user', 'owner'])[0], 2)
                row = self.store._connection.execute('SELECT * FROM Operations ORDER BY id DESC LIMIT 1').fetchone()
                self.assertEqual(row['operation_type'], arguments[0] + '_failed')
                self.assertEqual(json.loads(row['detail'])['path'], arguments[1])
                self.assertIsNone(row['file_id'])

    def test_cli_commit_failure_restores_file_and_records_failure(self):
        def factory(database):
            store = AuditStore(database)
            # Authentication commits first; the file operation fails second.
            store._connection = FailCommitOnce(store._connection, fail_on=2)
            return store

        code, output = self.cli(['write', 'original.txt', '--text', 'new content', '--user', 'owner'], factory)
        self.assertEqual(code, 2)
        self.assertIn('simulated commit failure', output)
        self.assertEqual((self.manager.root / 'original.txt').read_text(), 'old')
        size = self.store._connection.execute("SELECT size FROM Files WHERE location='original.txt'").fetchone()[0]
        self.assertEqual(size, 3)
        row = self.store._connection.execute('SELECT * FROM Operations ORDER BY id DESC LIMIT 1').fetchone()
        self.assertEqual(row['operation_type'], 'write_failed')
        self.assertIn('simulated commit failure', json.loads(row['detail'])['error'])

    def test_commit_failure_restores_create_modify_delete_and_archives(self):
        operations = [
            lambda: self.manager.write_text('new/created.txt', 'created', self.owner),
            lambda: self.manager.write_text('original.txt', 'new content', self.owner),
            lambda: self.manager.delete('original.txt', self.owner),
            lambda: self.manager.create_zip('new/archive.zip', ['original.txt'], self.owner),
            lambda: self.manager.extract_zip('source.zip', 'new-output', self.owner),
            lambda: self.manager.extract_zip('source.zip', 'existing', self.owner),
        ]
        for index, operation in enumerate(operations):
            with self.subTest(operation=index):
                before = self.snapshot()
                connection = self.store._connection
                with patch.object(self.store, '_connection', FailCommitOnce(connection)):
                    with self.assertRaisesRegex(sqlite3.OperationalError, 'simulated commit failure'):
                        operation()
                self.assertFalse(connection.in_transaction)
                self.assertEqual(self.snapshot(), before)

    def test_partial_zip_extraction_failure_restores_files_and_database(self):
        before = self.snapshot()
        original = self.store.record_file

        def fail_second(path, *arguments):
            if path.endswith('second.txt'):
                raise sqlite3.OperationalError('audit write failed')
            return original(path, *arguments)

        with patch.object(self.store, 'record_file', side_effect=fail_second):
            with self.assertRaisesRegex(sqlite3.OperationalError, 'audit write failed'):
                self.manager.extract_zip('source.zip', 'existing', self.owner)
        self.assertEqual(self.snapshot(), before)

    def test_outer_failure_restores_multiple_changes_in_reverse_order(self):
        before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, 'cancel batch'):
            with self.store.transaction():
                self.manager.write_text('original.txt', 'intermediate', self.owner)
                self.manager.write_text('original.txt', 'final', self.owner)
                self.manager.delete('existing/keep.txt', self.owner)
                self.manager.create_zip('batch/archive.zip', ['original.txt'], self.owner)
                raise RuntimeError('cancel batch')
        self.assertEqual(self.snapshot(), before)

    def test_caught_nested_error_prevents_partial_commit(self):
        before = self.snapshot()
        with self.assertRaises(SafeFileError):
            with self.store.transaction():
                self.manager.write_text('original.txt', 'changed', self.owner)
                try:
                    with self.store.transaction():
                        self.manager.delete('existing/keep.txt', self.owner)
                        raise ValueError('nested failure')
                except ValueError:
                    pass
        self.assertEqual(self.snapshot(), before)

    def test_files_are_restored_before_sqlite_write_lock_is_released(self):
        connection = self.store._connection
        proxy = FailCommitOnce(connection)
        observed = []

        def check():
            self.assertTrue(connection.in_transaction)
            observed.append((self.manager.root / 'original.txt').read_text())

        proxy.before_rollback = check
        with patch.object(self.store, '_connection', proxy):
            with self.assertRaises(sqlite3.OperationalError):
                self.manager.write_text('original.txt', 'new content', self.owner)
        self.assertEqual(observed, ['old'])


if __name__ == '__main__':
    unittest.main()
