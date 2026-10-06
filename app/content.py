"""Content validation and transactional mutations shared by admin and CLI."""
import os
import re
import sqlite3
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import bleach
from flask import current_app

from .db import get_db
from .drive import DriveError, read_drive_folder
from .uploads import store_image


# Storage allowlists and server-side validation only; forms live in the templates.
SECTIONS = {
    'eventi': dict(table='events',
        fields=('title', 'slug', 'date', 'location', 'description', 'published'),
        required=('title', 'slug', 'date', 'location'), images=()),
    'notizie': dict(table='news',
        fields=('title', 'slug', 'date', 'summary', 'body', 'external_url', 'image', 'image_alt', 'published'),
        required=('title', 'slug', 'date', 'summary'), images=('image',)),
    'foto': dict(table='albums',
        fields=('title', 'slug', 'date', 'description', 'folder', 'cover', 'cover_alt', 'cover_position', 'published'),
        required=('title', 'slug', 'date'), images=('cover',)),
}


def clean_body(value):
    return bleach.clean(value, tags={'p', 'br', 'strong', 'em', 'b', 'i', 'u', 'h2', 'h3', 'h4',
        'ul', 'ol', 'li', 'blockquote', 'a', 'img', 'figure', 'figcaption', 'div', 'span'},
        attributes={'a': ['href', 'title', 'rel'], 'img': ['src', 'alt', 'width', 'height'],
                    '*': ['class']}, protocols={'https', 'http', 'mailto', 'tel'}, strip=True)


def image_url(value):
    value = value.strip()
    if not value:
        return ''
    if value.startswith('assets/'):
        value = '/' + value
    if re.fullmatch(r'/(?:assets|uploads)/[\w./-]+', value) and '..' not in value.split('/'):
        return value
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or '\\' in value or any(ord(c) < 32 for c in value):
        raise ValueError('image_url_invalid')
    if parsed.hostname == 'drive.google.com':
        match = re.match(r'^/file/d/([\w-]+)', parsed.path)
        id = match.group(1) if match else parse_qs(parsed.query).get('id', [''])[0]
        if not re.fullmatch(r'[\w-]+', id):
            raise ValueError('drive_photo_invalid')
        return f'https://lh3.googleusercontent.com/d/{id}=s1600'
    return value


def https_url(value):
    if not value:
        return ''
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or '\\' in value or any(ord(c) < 32 for c in value):
        raise ValueError('https_invalid')
    return value


def folder_url(value):
    https_url(value)
    if value:
        parsed = urlsplit(value)
        if parsed.hostname != 'drive.google.com' or not re.fullmatch(r'/drive/(?:u/\d+/)?folders/[\w-]+/?', parsed.path):
            raise ValueError('drive_folder_invalid')
    return value


def valid_date(value, month_only=False, allow_month=False):
    pattern = r'\d{4}-\d{2}' if month_only else r'\d{4}-\d{2}(?:-\d{2})?' if allow_month else r'\d{4}-\d{2}-\d{2}'
    try:
        if not re.fullmatch(pattern, value):
            raise ValueError()
        date.fromisoformat(value + '-01' if len(value) == 7 else value)
    except ValueError as exc:
        raise ValueError('date_invalid') from exc
    return value


def order(value):
    try:
        result = int(value or 0)
        if abs(result) > 1_000_000:
            raise ValueError()
        return result
    except ValueError as exc:
        raise ValueError('order_invalid') from exc


def validate_content(section, form, files, existing=None):
    spec = SECTIONS[section]
    data = {}
    for name in spec['fields']:
        value = form.get(name, '').strip()
        if name == 'published':
            data[name] = int(value in ('on', '1', 'true', 'yes'))
            continue
        if name in spec['required'] and not value:
            raise ValueError('required_fields')
        maximum = 100_000 if name == 'body' else 10_000 if name in ('description', 'summary') else 2000
        if len(value) > maximum:
            raise ValueError({'code': 'field_too_long', 'field': name, 'maximum': maximum})
        data[name] = value
    if 'slug' in data and not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', data['slug']):
        raise ValueError('slug_invalid')
    if 'date' in data:
        valid_date(data['date'], month_only=section == 'foto', allow_month=section in {'eventi', 'notizie'})
    if 'sort_order' in data:
        data['sort_order'] = order(data['sort_order'])
    if 'body' in data:
        data['body'] = clean_body(data['body'])
        data['external_url'] = https_url(data['external_url'])
        if not data['external_url'] and not bleach.clean(data['body'], tags=set(), strip=True).strip():
            raise ValueError('article_required')
    if 'folder' in data:
        data['folder'] = folder_url(data['folder'])
        if data['cover_position'] and not re.fullmatch(r'-?\d+(?:\.\d+)?% -?\d+(?:\.\d+)?%', data['cover_position']):
            raise ValueError('cover_position_invalid')
    if 'slug' in data:
        duplicate = get_db().execute(f'SELECT id FROM {spec["table"]} WHERE slug = ?', (data['slug'],)).fetchone()
        if duplicate and (not existing or duplicate['id'] != existing['id']):
            raise ValueError('slug_duplicate')
    # Files are saved only after other fields have passed validation.
    for name in spec['images']:
        upload = files.get(name + '_upload')
        data[name] = store_image(upload) if upload and upload.filename else image_url(data[name])
    return data


def save_content(section, data, id=None):
    table = SECTIONS[section]['table']
    allowed = set(SECTIONS[section]['fields'])
    if not data or not set(data) <= allowed:
        raise ValueError('fields_invalid')
    db = get_db()
    try:
        with db:
            if id is None:
                columns = ','.join(data)
                placeholders = ','.join('?' for _ in data)
                return db.execute(f'INSERT INTO {table} ({columns}) VALUES ({placeholders})', tuple(data.values())).lastrowid
            db.execute(f'UPDATE {table} SET ' + ','.join(f'{key}=?' for key in data) + ' WHERE id=?', (*data.values(), id))
            return id
    except sqlite3.IntegrityError as exc:
        raise ValueError('content_invalid') from exc


def delete_content(section, id):
    db = get_db()
    with db:
        db.execute(f'DELETE FROM {SECTIONS[section]["table"]} WHERE id=?', (id,))


def save_photo(album_id, form, files, id=None):
    db = get_db()
    existing = db.execute('SELECT * FROM photos WHERE id=? AND album_id=?', (id, album_id)).fetchone() if id else None
    if id and not existing:
        raise ValueError('photo_missing')
    alt = form.get('alt', '').strip()
    if len(alt) > 2000:
        raise ValueError('description_too_long')
    position = order(form.get('sort_order', '0'))
    file = files.get('image_upload')
    src = store_image(file) if file and file.filename else image_url(form.get('src', existing['src'] if existing else ''))
    if not src:
        raise ValueError('photo_required')
    same = existing and src == existing['src']
    thumbnail = existing['thumbnail'] if same else src
    original = existing['original'] if same else src
    source = existing['source'] if same else 'upload' if src.startswith('/uploads/') else 'link'
    try:
        with db:
            if existing:
                db.execute('UPDATE photos SET src=?, thumbnail=?, original=?, alt=?, sort_order=?, source=? WHERE id=? AND album_id=?',
                           (src, thumbnail, original, alt, position, source, id, album_id))
                return id
            return db.execute('INSERT INTO photos(album_id,src,thumbnail,original,alt,sort_order,source) VALUES(?,?,?,?,?,?,?)',
                              (album_id, src, thumbnail, original, alt, position, source)).lastrowid
    except sqlite3.IntegrityError as exc:
        raise ValueError('photo_duplicate') from exc


def delete_photo(album_id, id):
    db = get_db()
    with db:
        db.execute('DELETE FROM photos WHERE id=? AND album_id=?', (id, album_id))


def sync_album(id):
    db = get_db()
    album = db.execute('SELECT * FROM albums WHERE id=?', (id,)).fetchone()
    if not album or not album['folder']:
        raise ValueError('drive_folder_required')
    folder_url(album['folder'])
    try:
        photos = read_drive_folder(
            album['folder'], cache_directory=Path(current_app.config['PROJECT_ROOT']) / '.cache/drive',
            api_key=os.environ.get('GOOGLE_DRIVE_API_KEY'), timeout=120,
        )
    except (OSError, DriveError) as exc:
        current_app.logger.warning('Drive sync failed for album %s: %s', id, type(exc).__name__)
        raise ValueError('drive_sync_failed') from exc
    # Reconcile only after a successful fetch; preserve existing captions/order,
    # and keep manually added photos independently of Drive's current listing.
    with db:
        current = {row['src']: row for row in db.execute("SELECT * FROM photos WHERE album_id=? AND source='drive'", (id,))}
        sources = {f'https://lh3.googleusercontent.com/d/{photo["id"]}=s1600' for photo in photos}
        db.executemany('DELETE FROM photos WHERE id=?', [(row['id'],) for src, row in current.items() if src not in sources])
        position = db.execute('SELECT coalesce(max(sort_order),-1)+1 FROM photos WHERE album_id=?', (id,)).fetchone()[0]
        for index, photo in enumerate(photos):
            pid = photo['id']
            src = f'https://lh3.googleusercontent.com/d/{pid}=s1600'
            query = dict(export='download', id=pid)
            if photo.get('resourceKey'):
                query['resourcekey'] = photo['resourceKey']
            original = 'https://drive.google.com/uc?' + urlencode(query)
            if src in current:
                db.execute('UPDATE photos SET original=? WHERE id=?', (original, current[src]['id']))
                continue
            db.execute('INSERT OR IGNORE INTO photos(album_id,src,thumbnail,original,alt,sort_order,source) VALUES(?,?,?,?,?,?,?)',
                (id, src, f'https://lh3.googleusercontent.com/d/{pid}=s640',
                 original, f'{album["title"]}: foto {index+1}', position, 'drive'))
            position += 1
    return len(photos)
