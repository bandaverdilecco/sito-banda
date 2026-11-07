"""Request-scoped SQLite connections and additive schema initialization."""
import sqlite3
from pathlib import Path

from flask import current_app, g


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(current_app.config['DATABASE'], timeout=15)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db


def close_db(error=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.execute('PRAGMA journal_mode = WAL')
    db.executescript(Path(__file__).with_name('schema.sql').read_text())
    version = db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0]
    if version != '1':
        raise RuntimeError('Versione database non supportata: ' + version)
    # Rebuild legacy accounts without names, preserving IDs and session references.
    db.execute('PRAGMA foreign_keys = OFF')
    try:
        db.execute('BEGIN IMMEDIATE')
        for table in ('news', 'teachers', 'photos'):
            columns = {row['name'] for row in db.execute(f'PRAGMA table_info({table})')}
            if 'image_position' not in columns:
                db.execute(f"ALTER TABLE {table} ADD COLUMN image_position TEXT NOT NULL DEFAULT ''")
            if 'image_zoom' not in columns:
                db.execute(f'ALTER TABLE {table} ADD COLUMN image_zoom REAL NOT NULL DEFAULT 1 CHECK(image_zoom BETWEEN 1 AND 10)')
        if 'cover_zoom' not in {row['name'] for row in db.execute('PRAGMA table_info(albums)')}:
            db.execute('ALTER TABLE albums ADD COLUMN cover_zoom REAL NOT NULL DEFAULT 1 CHECK(cover_zoom BETWEEN 1 AND 10)')
        if 'published' not in {row['name'] for row in db.execute('PRAGMA table_info(photos)')}:
            db.execute('ALTER TABLE photos ADD COLUMN published INTEGER NOT NULL DEFAULT 1 CHECK(published IN (0,1))')
        if 'username' in {row['name'] for row in db.execute('PRAGMA table_info(users)')}:
            db.execute('CREATE TABLE users_without_names (id INTEGER PRIMARY KEY, password_hash TEXT NOT NULL)')
            db.execute('INSERT INTO users_without_names SELECT id, password_hash FROM users')
            db.execute('DROP TABLE users')
            db.execute('ALTER TABLE users_without_names RENAME TO users')
        if db.execute('PRAGMA foreign_key_check').fetchone():
            raise RuntimeError('Riferimenti database non validi.')
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.execute('PRAGMA foreign_keys = ON')
