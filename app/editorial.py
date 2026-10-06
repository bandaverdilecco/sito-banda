"""Editable homepage selections, introductory cards and music-school teachers."""

from datetime import datetime
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from PIL import Image

from . import content
from .admin import load_user, login_required
from .db import get_db


bp = Blueprint('editorial', __name__, url_prefix='/admin')
bp.before_request(load_user)


def home_content(db, today):
    """Use the old automatic selection until the homepage is first saved."""
    selection = db.execute('SELECT * FROM home_selection WHERE id=1').fetchone()
    if selection is not None and selection['configured']:
        events = db.execute('SELECT events.* FROM events JOIN home_events '
            'ON home_events.event_id=events.id WHERE events.published=1 '
            'ORDER BY events.date,events.id').fetchall()
        latest = db.execute('SELECT * FROM news WHERE id=? AND published=1',
                            (selection['news_id'],)).fetchone()
    else:
        events = db.execute('SELECT * FROM events WHERE published=1 AND '
            '((length(date)=7 AND date>=?) OR (length(date)=10 AND date>=?)) '
            'ORDER BY date,id LIMIT 3', (today[:7], today)).fetchall()
        latest = db.execute('SELECT * FROM news WHERE published=1 ORDER BY date DESC,id LIMIT 1').fetchone()
    return events, latest


def _identifier(value):
    if not re.fullmatch(r'[1-9][0-9]{0,18}', value):
        raise ValueError('selection_invalid')
    number = int(value)
    if number > 9_223_372_036_854_775_807:
        raise ValueError('selection_invalid')
    return number


def _save_selection(form):
    event_ids = {_identifier(value) for value in form.getlist('event_ids')}
    news_values = form.getlist('news_id')
    if len(news_values) > 1:
        raise ValueError('selection_invalid')
    news_id = _identifier(news_values[0]) if news_values and news_values[0] else None
    db = get_db()
    try:
        with db:
            # Keep validation and replacement atomic with concurrent editorial changes.
            db.execute('BEGIN IMMEDIATE')
            published_ids = {row['id'] for row in db.execute('SELECT id FROM events WHERE published=1')}
            if not event_ids <= published_ids:
                raise ValueError('selection_invalid')
            if news_id is not None and db.execute(
                'SELECT id FROM news WHERE id=? AND published=1', (news_id,)
            ).fetchone() is None:
                raise ValueError('selection_invalid')
            db.execute('DELETE FROM home_events')
            db.executemany('INSERT INTO home_events (event_id) VALUES (?)', [(item_id,) for item_id in event_ids])
            db.execute('INSERT INTO home_selection (id,configured,news_id) VALUES (1,1,?) '
                'ON CONFLICT(id) DO UPDATE SET configured=1,news_id=excluded.news_id', (news_id,))
    except sqlite3.IntegrityError as exc:
        raise ValueError('selection_invalid') from exc


@bp.route('/home', methods=['GET', 'POST'])
@login_required
def home():
    db = get_db()
    today = datetime.now(ZoneInfo('Europe/Rome')).date().isoformat()
    selected_events, selected_news = home_content(db, today)
    selected_event_ids = {row['id'] for row in selected_events}
    selected_news_id = selected_news['id'] if selected_news else None
    error = None
    if request.method == 'POST':
        try:
            _save_selection(request.form)
        except ValueError as exc:
            error = exc.args[0]
            # Retain valid submitted choices when another choice was rejected.
            selected_event_ids = set()
            for value in request.form.getlist('event_ids'):
                try:
                    selected_event_ids.add(_identifier(value))
                except ValueError:
                    pass
            try:
                selected_news_id = _identifier(request.form.get('news_id', ''))
            except ValueError:
                selected_news_id = None
        else:
            flash('home_saved', 'success')
            return redirect(url_for('editorial.home'))
    events = db.execute('SELECT * FROM events WHERE published=1 ORDER BY date,id').fetchall()
    news = db.execute('SELECT * FROM news WHERE published=1 ORDER BY date DESC,id').fetchall()
    return render_template('admin/home.html', section='home', events=events, news=news,
        selected_event_ids=selected_event_ids, selected_news_id=selected_news_id,
        error=error), (422 if error else 200)


def _text(form, name, *, required=False, maximum=2000):
    value = form.get(name, '').strip()
    if required and not value:
        raise ValueError('required_fields')
    if len(value) > maximum:
        raise ValueError({'code': 'field_too_long', 'field': name, 'maximum': maximum})
    return value


def _feature_url(value):
    if '\\' in value or any(ord(character) < 32 for character in value):
        raise ValueError('feature_url_invalid')
    if value.startswith('/') and not value.startswith('//'):
        return value
    try:
        parsed = urlsplit(value)
        if parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password:
            return value
    except ValueError:
        pass
    raise ValueError('feature_url_invalid')


def _feature_data(form):
    data = {name: _text(form, name, required=name != 'eyebrow',
                      maximum=10_000 if name == 'description' else 2000)
            for name in ('eyebrow', 'title', 'description', 'url', 'link_label')}
    data['url'] = _feature_url(data['url'])
    return data


def _image_size(source):
    """Read dimensions only for local files; external URLs are never fetched."""
    if source.startswith('/uploads/'):
        path = Path(current_app.config['UPLOAD_FOLDER']) / source.removeprefix('/uploads/')
    elif source.startswith('/assets/'):
        path = Path(current_app.config['PROJECT_ROOT']) / 'public' / source.removeprefix('/')
    else:
        return None, None
    try:
        with Image.open(path) as image:
            return image.size
    except (OSError, ValueError, Image.DecompressionBombError):
        return None, None


def _teacher_data(form, files, existing):
    data = {name: _text(form, name, required=name in ('name', 'instrument'))
            for name in ('name', 'instrument', 'image', 'image_alt')}
    upload = files.get('image_upload')
    # Image writes happen only after every non-file field has passed validation.
    data['image'] = content.store_image(upload) if upload and upload.filename else content.image_url(data['image'])
    if existing and data['image'] == existing['image']:
        data['image_width'], data['image_height'] = existing['image_width'], existing['image_height']
    else:
        data['image_width'], data['image_height'] = _image_size(data['image'])
    return data


def _record(table, item_id):
    row = get_db().execute(f'SELECT * FROM {table} WHERE id=?', (item_id,)).fetchone()
    if row is None:
        abort(404)
    return dict(row)


def _save(table, data, item_id):
    db = get_db()
    with db:
        if item_id is None:
            db.execute('BEGIN IMMEDIATE')
            data['sort_order'] = db.execute(f'SELECT coalesce(max(sort_order),-1)+1 FROM {table}').fetchone()[0]
            columns = ','.join(data)
            placeholders = ','.join('?' for _ in data)
            return db.execute(f'INSERT INTO {table} ({columns}) VALUES ({placeholders})', tuple(data.values())).lastrowid
        db.execute(f'UPDATE {table} SET ' + ','.join(f'{key}=?' for key in data) + ' WHERE id=?', (*data.values(), item_id))
        return item_id


@bp.post('/<section>/<int:item_id>/move')
@login_required
def move_entry(section, item_id):
    sections = {'musica-insieme': ('home_features', 'editorial.features'),
                'insegnanti': ('teachers', 'editorial.teachers')}
    if section not in sections:
        abort(404)
    directions = request.form.getlist('direction')
    if len(directions) != 1 or directions[0] not in ('up', 'down'):
        abort(400)
    table, endpoint = sections[section]
    db = get_db()
    with db:
        db.execute('BEGIN IMMEDIATE')
        ids = [row['id'] for row in db.execute(f'SELECT id FROM {table} ORDER BY sort_order,id')]
        if item_id not in ids:
            abort(404)
        index = ids.index(item_id)
        target = index + (-1 if directions[0] == 'up' else 1)
        if 0 <= target < len(ids):
            ids[index], ids[target] = ids[target], ids[index]
            # Normalize tied and sparse legacy positions while retaining all other entries.
            db.executemany(f'UPDATE {table} SET sort_order=? WHERE id=?', enumerate(ids))
    if request.accept_mimetypes.best == 'application/json':
        return jsonify(ids=ids)
    return redirect(url_for(endpoint, _anchor=f'entry-{item_id}'))


@bp.route('/musica-insieme', methods=['GET', 'POST'])
@login_required
def features():
    db = get_db()
    row = db.execute('SELECT * FROM home_intro WHERE id=1').fetchone()
    intro = dict(row) if row else {'title': '', 'eyebrow': ''}
    values = dict(intro)
    error = None
    if request.method == 'POST':
        values.update(request.form.to_dict())
        try:
            title = _text(request.form, 'title', required=True)
            eyebrow = _text(request.form, 'eyebrow')
        except ValueError as exc:
            error = exc.args[0]
        else:
            with db:
                db.execute('INSERT INTO home_intro (id,title,eyebrow) VALUES (1,?,?) '
                    'ON CONFLICT(id) DO UPDATE SET title=excluded.title,eyebrow=excluded.eyebrow', (title, eyebrow))
            flash('intro_saved', 'success')
            return redirect(url_for('editorial.features'))
    records = db.execute('SELECT * FROM home_features ORDER BY sort_order,id').fetchall()
    return render_template('admin/musica-insieme.html', section='musica-insieme',
        intro=intro, values=values, records=records, error=error), (422 if error else 200)


@bp.route('/musica-insieme/new', methods=['GET', 'POST'])
@bp.route('/musica-insieme/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
def feature_edit(item_id=None):
    record = _record('home_features', item_id) if item_id is not None else None
    values = dict(record) if record else {'published': 1}
    error = None
    if request.method == 'POST':
        values.update(request.form.to_dict())
        try:
            saved_id = _save('home_features', _feature_data(request.form), item_id)
        except ValueError as exc:
            error = exc.args[0]
        else:
            flash('content_saved' if record else 'content_added', 'success')
            return redirect(url_for('editorial.feature_edit', item_id=saved_id))
    return render_template('admin/modifica-scheda.html', section='musica-insieme',
        record=record, values=values, error=error), (422 if error else 200)


@bp.get('/insegnanti')
@login_required
def teachers():
    records = get_db().execute('SELECT * FROM teachers ORDER BY sort_order,id').fetchall()
    return render_template('admin/insegnanti.html', section='insegnanti', records=records)


@bp.route('/insegnanti/new', methods=['GET', 'POST'])
@bp.route('/insegnanti/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
def teacher_edit(item_id=None):
    record = _record('teachers', item_id) if item_id is not None else None
    values = dict(record) if record else {'published': 1}
    error = None
    if request.method == 'POST':
        values.update(request.form.to_dict())
        try:
            saved_id = _save('teachers', _teacher_data(request.form, request.files, record), item_id)
        except ValueError as exc:
            error = exc.args[0]
        else:
            flash('content_saved' if record else 'content_added', 'success')
            return redirect(url_for('editorial.teacher_edit', item_id=saved_id))
    return render_template('admin/modifica-insegnante.html', section='insegnanti',
        record=record, values=values, error=error), (422 if error else 200)


def _delete(table, item_id, section, kind, endpoint):
    record = _record(table, item_id)
    if request.method == 'POST':
        db = get_db()
        with db:
            db.execute(f'DELETE FROM {table} WHERE id=?', (item_id,))
        flash('content_deleted', 'success')
        return redirect(url_for(endpoint))
    return render_template('admin/elimina-elemento.html', section=section, kind=kind, record=record)


@bp.route('/musica-insieme/<int:item_id>/delete', methods=['GET', 'POST'])
@login_required
def feature_delete(item_id):
    return _delete('home_features', item_id, 'musica-insieme', 'feature', 'editorial.features')


@bp.route('/insegnanti/<int:item_id>/delete', methods=['GET', 'POST'])
@login_required
def teacher_delete(item_id):
    return _delete('teachers', item_id, 'insegnanti', 'teacher', 'editorial.teachers')
