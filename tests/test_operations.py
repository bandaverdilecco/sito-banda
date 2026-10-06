"""Account setup, durable backups and media maintenance on isolated instances."""
from contextlib import closing
import io
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from werkzeug.datastructures import FileStorage
from werkzeug.security import check_password_hash

from app import create_app
from app.content import sync_album
from app.db import get_db
from app.uploads import store_image


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='filarmonica-operations-')
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.config = dict(TESTING=True, INSTANCE_PATH=str(self.path))
        self.app = create_app(self.config)

    def test_templates_reload_without_debug(self):
        from flask import render_template
        from jinja2 import DictLoader

        self.assertFalse(self.app.debug)
        templates = {'reload-test.html': 'Prima modifica'}
        self.app.jinja_loader = DictLoader(templates)
        self.app.add_url_rule('/template-test', 'template_test', lambda: render_template('reload-test.html'))
        client = self.app.test_client()
        self.assertEqual(client.get('/template-test').get_data(as_text=True), 'Prima modifica')
        templates['reload-test.html'] = 'Seconda modifica'
        self.assertEqual(client.get('/template-test').get_data(as_text=True), 'Seconda modifica')

    def test_app_environment_configures_storage_and_secure_cookies(self):
        instance = self.path / 'configured-instance'
        with patch.dict(os.environ, APP_INSTANCE_PATH=str(instance), APP_HTTPS='1'):
            app = create_app({'TESTING': True})
        self.assertEqual(Path(app.instance_path), instance)
        self.assertEqual(Path(app.config['DATABASE']), instance / 'site.sqlite3')
        self.assertEqual(Path(app.config['UPLOAD_FOLDER']), instance / 'uploads')
        self.assertTrue(app.config['SESSION_COOKIE_SECURE'])
        with patch.dict(os.environ, APP_INSTANCE_PATH=str(instance), APP_HTTPS='0'):
            self.assertFalse(create_app({'TESTING': True}).config['SESSION_COOKIE_SECURE'])

    def test_new_installation_starts_empty_and_stays_empty_after_restart(self):
        for app in (self.app, create_app(self.config)):
            with app.app_context():
                db = get_db()
                for table in ('events', 'news', 'albums', 'photos', 'users', 'sessions'):
                    with self.subTest(table=table):
                        self.assertEqual(db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0)
                self.assertEqual(db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0], '1')
            client = app.test_client()
            for path in ('/', '/prossimi-eventi.html', '/notizie.html', '/foto.html', '/admin'):
                with self.subTest(path=path):
                    self.assertEqual(client.get(path).status_code, 200)

    def test_admin_setup_and_reset_accept_short_passwords_and_revoke_sessions(self):
        runner = self.app.test_cli_runner()
        password = 'a'
        result = runner.invoke(args=['create-admin'], input=f'{password}\n{password}\n')
        self.assertEqual(result.exit_code, 0, result.output)
        with self.app.app_context():
            db = get_db()
            user = db.execute('SELECT * FROM users').fetchone()
            self.assertTrue(check_password_hash(user['password_hash'], password))
            self.assertNotEqual(user['password_hash'], password)
            db.execute('INSERT INTO sessions VALUES(?,?,?)', ('session-to-revoke', user['id'], 9999999999))
            db.commit()
        replacement = 'b'
        result = runner.invoke(args=['create-admin', '--reset-password'], input=f'{replacement}\n{replacement}\n')
        self.assertEqual(result.exit_code, 0, result.output)
        with self.app.app_context():
            db = get_db()
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0], 0)
            self.assertTrue(check_password_hash(db.execute('SELECT password_hash FROM users').fetchone()[0], replacement))

    def test_legacy_usernames_are_removed_without_losing_passwords_or_sessions(self):
        from app.db import init_db

        with self.app.app_context():
            db = get_db()
            db.execute('DROP TABLE users')
            db.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE, password_hash TEXT NOT NULL)')
            db.execute("INSERT INTO users VALUES(7, 'legacy-admin', 'preserved-hash')")
            db.execute("INSERT INTO sessions VALUES('preserved-token', 7, 9999999999)")
            db.commit()
            init_db()
            init_db()
            self.assertEqual([row['name'] for row in db.execute('PRAGMA table_info(users)')], ['id', 'password_hash'])
            self.assertEqual(tuple(db.execute('SELECT * FROM users').fetchone()), (7, 'preserved-hash'))
            self.assertEqual(db.execute('SELECT user_id FROM sessions').fetchone()[0], 7)
            self.assertEqual(db.execute('PRAGMA foreign_keys').fetchone()[0], 1)

    def test_existing_photos_gain_visibility_without_losing_data(self):
        from app.db import init_db

        with self.app.app_context():
            db = get_db()
            db.execute('DROP TABLE photos')
            db.execute('CREATE TABLE photos (id INTEGER PRIMARY KEY, album_id INTEGER NOT NULL REFERENCES albums(id) ON DELETE CASCADE, src TEXT NOT NULL, thumbnail TEXT NOT NULL DEFAULT "", original TEXT NOT NULL DEFAULT "", alt TEXT NOT NULL DEFAULT "", sort_order INTEGER NOT NULL DEFAULT 0, source TEXT NOT NULL DEFAULT "upload", UNIQUE(album_id,src))')
            album_id = db.execute("INSERT INTO albums(slug,title,date) VALUES('old','Album esistente','2026-10')").lastrowid
            db.execute("INSERT INTO photos(album_id,src,alt) VALUES(?, '/assets/concert.jpg', 'Foto esistente')", (album_id,))
            db.commit()
            init_db()
            self.assertEqual(tuple(db.execute('SELECT src,alt,published FROM photos').fetchone()), ('/assets/concert.jpg', 'Foto esistente', 1))
            db.execute('UPDATE photos SET published=0')
            db.commit()
            init_db()
            self.assertEqual(db.execute('SELECT published FROM photos').fetchone()[0], 0)

    def test_password_reset_requires_id_only_when_multiple_accounts_exist(self):
        runner = self.app.test_cli_runner()
        self.assertNotEqual(runner.invoke(args=['create-admin', '--reset-password']).exit_code, 0)
        for password in ('a', 'b'):
            result = runner.invoke(args=['create-admin'], input=f'{password}\n{password}\n')
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertNotIn('Nome utente', result.output)
        result = runner.invoke(args=['create-admin', '--reset-password'])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn('--admin-id', result.output)
        result = runner.invoke(args=['create-admin', '--reset-password', '--admin-id', '2'], input='c\nc\n')
        self.assertEqual(result.exit_code, 0, result.output)
        with self.app.app_context():
            users = get_db().execute('SELECT password_hash FROM users ORDER BY id').fetchall()
            self.assertTrue(check_password_hash(users[0][0], 'a'))
            self.assertTrue(check_password_hash(users[1][0], 'c'))

    def test_backup_contains_committed_wal_content_and_refuses_overwrite(self):
        with self.app.app_context():
            db = get_db()
            db.execute("INSERT INTO events(slug,title,date) VALUES('backup-event','Concerto salvato','2027-01')")
            db.commit()
            destination = self.path / 'backup.sqlite3'
            result = self.app.test_cli_runner().invoke(args=['backup-db', str(destination)])
            self.assertEqual(result.exit_code, 0, result.output)
            with closing(sqlite3.connect(destination)) as backup:
                self.assertEqual(backup.execute('SELECT title FROM events').fetchone()[0], 'Concerto salvato')
                self.assertEqual(backup.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            result = self.app.test_cli_runner().invoke(args=['backup-db', str(destination)])
            self.assertNotEqual(result.exit_code, 0)

    def test_session_key_is_persistent_without_environment_secret(self):
        key = self.app.config['SECRET_KEY']
        restarted = create_app(self.config)
        self.assertEqual(restarted.config['SECRET_KEY'], key)
        self.assertTrue(key)
        self.assertNotEqual(create_app(dict(self.config, SECRET_KEY='explicit-test-key')).config['SECRET_KEY'], key)

    def test_palette_image_upload_keeps_transparency(self):
        image = Image.new('P', (4, 4), 0)
        image.putpalette([118, 32, 56] + [0, 0, 0] * 255)
        stream = io.BytesIO()
        image.save(stream, 'PNG', transparency=0)
        stream.seek(0)
        with self.app.app_context():
            url = store_image(FileStorage(stream=stream, filename='transparent.png'))
            with Image.open(Path(self.app.config['UPLOAD_FOLDER']) / url.rsplit('/', 1)[1]) as stored:
                self.assertEqual(stored.convert('RGBA').getpixel((0, 0))[3], 0)

    def test_drive_reconciliation_keeps_captions_order_and_manual_images(self):
        with self.app.app_context():
            db = get_db()
            album = db.execute("INSERT INTO albums(slug,title,date,folder) VALUES('album','Concerto','2026-10','https://drive.google.com/drive/folders/example')").lastrowid
            db.commit()
            initial = [{'id': 'kept-photo'}, {'id': 'removed-photo'}]
            with patch('app.content.read_drive_folder', return_value=initial):
                self.assertEqual(sync_album(album), 2)
            kept = db.execute("SELECT * FROM photos WHERE src LIKE '%kept-photo=%'").fetchone()
            db.execute('UPDATE photos SET alt=?,sort_order=?,published=0 WHERE id=?', ('Descrizione personalizzata', -3, kept['id']))
            db.execute('INSERT INTO photos(album_id,src,alt,source) VALUES(?,?,?,?)', (album, '/assets/concert.jpg', 'Manuale', 'link'))
            db.commit()
            refreshed = [{'id': 'kept-photo', 'resourceKey': 'updated-key'}, {'id': 'new-photo'}]
            with patch('app.content.read_drive_folder', return_value=refreshed):
                self.assertEqual(sync_album(album), 2)
            updated = db.execute('SELECT * FROM photos WHERE id=?', (kept['id'],)).fetchone()
            self.assertEqual(updated['alt'], 'Descrizione personalizzata')
            self.assertEqual(updated['sort_order'], -3)
            self.assertEqual(updated['published'], 0)
            self.assertIn('updated-key', updated['original'])
            self.assertEqual(db.execute("SELECT count(*) FROM photos WHERE src LIKE '%removed-photo=%'").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM photos WHERE source='link'").fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM photos').fetchone()[0], 3)

    def test_production_command_configures_waitress_directly(self):
        with patch('waitress.serve') as serve:
            result = self.app.test_cli_runner().invoke(args=['serve', '--port', '9090'])
        self.assertEqual(result.exit_code, 0, result.output)
        serve.assert_called_once_with(self.app, host='127.0.0.1', port=9090, max_request_body_size=16 * 1024 * 1024)

    def test_production_command_trusts_only_configured_local_proxy(self):
        with patch.dict(os.environ, APP_TRUST_PROXY='1'):
            app = create_app(self.config)
            with patch('waitress.serve') as serve:
                result = app.test_cli_runner().invoke(args=['serve'])
        self.assertEqual(result.exit_code, 0, result.output)
        serve.assert_called_once_with(app, host='127.0.0.1', port=8080, max_request_body_size=16 * 1024 * 1024,
            trusted_proxy='127.0.0.1', trusted_proxy_count=1,
            trusted_proxy_headers={'x-forwarded-for', 'x-forwarded-proto'})
