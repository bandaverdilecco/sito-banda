"""Authenticated editorial workspace for the Filarmonica website."""

from functools import wraps
import hashlib
import secrets
import time

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from . import content
from .db import get_db


bp = Blueprint("admin", __name__, url_prefix="/admin")
_DUMMY_PASSWORD = generate_password_hash(secrets.token_urlsafe(32), method="scrypt")
_SESSION_SECONDS = 8 * 60 * 60
_LOGIN_WINDOW = 15 * 60
_LOGIN_LIMIT = 5


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@bp.before_request
def load_user():
    g.current_user = None
    token = session.get("admin_token")
    if not isinstance(token, str):
        return
    g.current_user = get_db().execute(
        "SELECT users.id FROM users JOIN sessions "
        "ON sessions.user_id = users.id WHERE sessions.token_hash = ? "
        "AND sessions.expires_at > ?",
        (_digest(token), int(time.time())),
    ).fetchone()
    if g.current_user is None:
        session.pop("admin_token", None)


def login_required(view):
    @wraps(view)
    def decorated(*args, **kwargs):
        if g.current_user is None:
            flash("login_required", "info")
            return redirect(url_for("admin.index"))
        return view(*args, **kwargs)

    return decorated


def _section(section):
    if section not in content.SECTIONS:
        abort(404)
    return content.SECTIONS[section]


def _record(section, item_id):
    config = _section(section)
    record = get_db().execute(
        f"SELECT * FROM {config['table']} WHERE id = ?", (item_id,)
    ).fetchone()
    if record is None:
        abort(404)
    return dict(record)


@bp.route("/", methods=["GET", "POST"])
@bp.route("", methods=["GET", "POST"])
def index():
    if g.current_user is not None:
        counts = {
            slug: get_db().execute(f"SELECT COUNT(*) FROM {config['table']}").fetchone()[0]
            for slug, config in content.SECTIONS.items()
        }
        return render_template("admin/pannello.html", counts=counts)
    error = None
    status = 200
    if request.method == "POST":
        password = request.form.get("password", "")
        keys = [_digest("ip:" + (request.remote_addr or "unknown"))]
        now = int(time.time())
        db = get_db()
        limited = False
        for key in keys:
            attempt = db.execute("SELECT count, window_start FROM login_attempts WHERE key = ?", (key,)).fetchone()
            if attempt and attempt["window_start"] > now - _LOGIN_WINDOW and attempt["count"] >= _LOGIN_LIMIT:
                limited = True
        user = None
        if not limited and password and len(password) <= 4096:
            users = db.execute("SELECT id, password_hash FROM users ORDER BY id").fetchall()
            for candidate in users:
                if check_password_hash(candidate["password_hash"], password) and user is None:
                    user = candidate
            if not users:
                check_password_hash(_DUMMY_PASSWORD, password)
        if limited:
            error = "login_limited"
            status = 429
        elif user is not None:
            old_token = session.get("admin_token")
            if isinstance(old_token, str):
                db.execute("DELETE FROM sessions WHERE token_hash = ?", (_digest(old_token),))
            token = secrets.token_urlsafe(32)
            db.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
            db.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (_digest(token), user["id"], now + _SESSION_SECONDS),
            )
            db.execute("DELETE FROM login_attempts WHERE key = ?", (keys[0],))
            db.commit()
            session.clear()
            session["admin_token"] = token
            return redirect(url_for("admin.index"))
        else:
            for key in keys:
                db.execute(
                    "INSERT INTO login_attempts (key, count, window_start) VALUES (?, 1, ?) "
                    "ON CONFLICT(key) DO UPDATE SET "
                    "count = CASE WHEN window_start <= ? THEN 1 ELSE count + 1 END, "
                    "window_start = CASE WHEN window_start <= ? THEN excluded.window_start ELSE window_start END",
                    (key, now, now - _LOGIN_WINDOW, now - _LOGIN_WINDOW),
                )
            db.commit()
            error = "password_invalid"
            status = 401
    return render_template("admin/accesso.html", error=error), status


@bp.post("/logout")
@login_required
def logout():
    token = session.get("admin_token")
    if isinstance(token, str):
        db = get_db()
        db.execute("DELETE FROM sessions WHERE token_hash = ?", (_digest(token),))
        db.commit()
    session.clear()
    flash("logged_out", "success")
    return redirect(url_for("admin.index"))


@bp.get("/<section>")
@login_required
def listing(section):
    config = _section(section)
    date_order = "substr(date,1,instr(date || ',',',')-1)" if section == 'foto' else 'date'
    records = [dict(row) for row in get_db().execute(f"SELECT * FROM {config['table']} ORDER BY {date_order} DESC, id DESC").fetchall()]
    return render_template("admin/elenco.html", section=section, records=records)


@bp.route("/<section>/new", methods=["GET", "POST"])
@bp.route("/<section>/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def edit(section, item_id=None):
    _section(section)
    existing = _record(section, item_id) if item_id is not None else None
    values = dict(existing) if existing else {"published": 1}
    error = None
    if request.method == "POST":
        values.update(request.form.to_dict())
        try:
            data = content.validate_content(section, request.form, request.files, existing=existing)
            saved_id = content.save_content(section, data, item_id)
        except ValueError as exc:
            error = exc.args[0]
        else:
            flash("content_saved" if existing else "content_added", "success")
            if section == "foto" and existing is None and data.get("folder"):
                try:
                    count = content.sync_album(saved_id)
                except ValueError:
                    flash("album_created_sync_failed", "error")
                else:
                    flash({"code": "sync_complete", "count": count}, "success")
            return redirect(url_for("admin.edit", section=section, item_id=saved_id))
    return render_template("admin/modifica.html", section=section, record=existing,
                           values=values, error=error), (422 if error else 200)


@bp.post('/<section>/<int:item_id>/publication')
@login_required
def publication(section, item_id):
    sections = {name: (config['table'], 'admin.listing') for name, config in content.SECTIONS.items()}
    sections.update({'musica-insieme': ('home_features', 'editorial.features'),
                     'insegnanti': ('teachers', 'editorial.teachers')})
    if section not in sections:
        abort(404)
    values = request.form.getlist('hidden')
    if len(values) > 1 or (values and values[0] != '1'):
        abort(400)
    published = int(not values)
    table, endpoint = sections[section]
    db = get_db()
    with db:
        result = db.execute(f'UPDATE {table} SET published=? WHERE id=?', (published, item_id))
        if result.rowcount != 1:
            abort(404)
    if request.accept_mimetypes.best == 'application/json':
        return jsonify(published=bool(published))
    return redirect(url_for(endpoint, **({'section': section} if endpoint == 'admin.listing' else {}),
                            _anchor=f'entry-{item_id}'))


@bp.route("/<section>/<int:item_id>/delete", methods=["GET", "POST"])
@login_required
def delete(section, item_id):
    _section(section)
    record = _record(section, item_id)
    if request.method == "POST":
        content.delete_content(section, item_id)
        flash("content_deleted", "success")
        return redirect(url_for("admin.listing", section=section))
    return render_template("admin/elimina.html", section=section, record=record)


@bp.route("/foto/<int:album_id>/photos", methods=["GET", "POST"])
@login_required
def photos(album_id):
    album = _record("foto", album_id)
    error = None
    values = {}
    if request.method == "POST":
        values = request.form.to_dict()
        try:
            content.save_photo(album_id, request.form, request.files)
        except ValueError as exc:
            error = exc.args[0]
        else:
            flash("photo_added", "success")
            return redirect(url_for("admin.photos", album_id=album_id))
    records = get_db().execute("SELECT * FROM photos WHERE album_id = ? ORDER BY sort_order, id", (album_id,)).fetchall()
    return render_template("admin/foto.html", section="foto", album=album, photos=records, values=values, error=error), (422 if error else 200)


def _photo(album_id, photo_id):
    photo = get_db().execute("SELECT * FROM photos WHERE album_id = ? AND id = ?", (album_id, photo_id)).fetchone()
    if photo is None:
        abort(404)
    return dict(photo)


@bp.route("/foto/<int:album_id>/photos/<int:photo_id>/edit", methods=["GET", "POST"])
@login_required
def edit_photo(album_id, photo_id):
    album = _record("foto", album_id)
    photo = _photo(album_id, photo_id)
    values = dict(photo)
    error = None
    if request.method == "POST":
        values.update(request.form.to_dict())
        values['hidden'] = 'hidden' in request.form
        try:
            content.save_photo(album_id, request.form, request.files, photo_id)
        except ValueError as exc:
            error = exc.args[0]
        else:
            flash("photo_saved", "success")
            return redirect(url_for("admin.edit_photo", album_id=album_id, photo_id=photo_id))
    return render_template("admin/modifica-foto.html", section="foto", album=album, photo=photo, values=values, error=error), (422 if error else 200)


@bp.post("/foto/<int:album_id>/photos/<int:photo_id>/visibility")
@login_required
def photo_visibility(album_id, photo_id):
    _photo(album_id, photo_id)
    values = request.form.getlist('hidden')
    if len(values) > 1 or (values and values[0] not in ('', '1')):
        abort(400)
    published = int(not values or values[0] != '1')
    db = get_db()
    with db:
        db.execute('UPDATE photos SET published=? WHERE id=? AND album_id=?', (published, photo_id, album_id))
    if request.accept_mimetypes.best == 'application/json':
        return jsonify(published=bool(published))
    flash('photo_saved', 'success')
    return redirect(url_for('admin.photos', album_id=album_id, _anchor=f'photo-{photo_id}'))


@bp.route("/foto/<int:album_id>/photos/<int:photo_id>/delete", methods=["GET", "POST"])
@login_required
def delete_photo(album_id, photo_id):
    album = _record("foto", album_id)
    photo = _photo(album_id, photo_id)
    if request.method == "POST":
        content.delete_photo(album_id, photo_id)
        flash("photo_deleted", "success")
        return redirect(url_for("admin.photos", album_id=album_id))
    return render_template("admin/elimina-foto.html", section="foto", album=album, photo=photo)


@bp.post("/foto/<int:album_id>/sync")
@login_required
def sync_photos(album_id):
    _record("foto", album_id)
    try:
        count = content.sync_album(album_id)
    except ValueError as exc:
        flash(exc.args[0], "error")
    else:
        flash({"code": "sync_complete", "count": count}, "success")
    return redirect(url_for("admin.photos", album_id=album_id))
