"""Filarmonica website: Jinja pages, SQLite content and private administration."""
import os
import re
import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import click
from bs4 import BeautifulSoup
from flask import Flask, abort, redirect, render_template, request, send_from_directory
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.security import generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

from .db import close_db, get_db, init_db

ROOT = Path(__file__).resolve().parent.parent
MONTHS = ('Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno', 'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre')


def date_label(value):
    dates = [item.strip().split('-') for item in str(value).split(',')]
    labels = []
    for index, parts in enumerate(dates):
        following = dates[index + 1] if index + 1 < len(dates) else None
        same_year = following is not None and parts[0] == following[0]
        same_month = same_year and parts[1] == following[1] and len(parts) == len(following) == 3
        month = MONTHS[int(parts[1]) - 1].lower()
        if len(parts) == 3:
            label = str(int(parts[2]))
            if not same_month:
                label += ' ' + month
        else:
            label = month.capitalize() if index == 0 else month
        if not same_year:
            label += ' ' + parts[0]
        labels.append(label)
    return ' - '.join(labels)


def create_app(test_config=None):
    instance = Path(os.environ.get('APP_INSTANCE_PATH', ROOT / 'instance')).resolve()
    if test_config and test_config.get('INSTANCE_PATH'):
        instance = Path(test_config['INSTANCE_PATH']).resolve()
    app = Flask(__name__, static_folder=None, instance_path=str(instance))
    trust_proxy = os.environ.get('APP_TRUST_PROXY') == '1'
    if trust_proxy:
        # Enable only behind one controlled proxy; the bundled nginx overwrites
        # both headers, and Waitress listens exclusively on the loopback address.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
    app.config.from_mapping(
        PROJECT_ROOT=ROOT, DATABASE=str(instance / 'site.sqlite3'), UPLOAD_FOLDER=str(instance / 'uploads'),
        SECRET_KEY=os.environ.get('SECRET_KEY'),
        TEMPLATES_AUTO_RELOAD=True,
        SESSION_COOKIE_NAME='filarmonica_admin', SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.environ.get('APP_HTTPS') == '1',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8), MAX_CONTENT_LENGTH=16 * 1024 * 1024,
        MAX_FORM_MEMORY_SIZE=256 * 1024, MAX_FORM_PARTS=100,
    )
    if test_config:
        app.config.update(test_config)
    instance.mkdir(parents=True, exist_ok=True, mode=0o700)
    Path(app.config['DATABASE']).parent.mkdir(parents=True, exist_ok=True)
    Path(app.config['UPLOAD_FOLDER']).mkdir(parents=True, exist_ok=True)
    if not app.config['SECRET_KEY']:
        # Exclusive creation makes one persistent key shared by workers/restarts.
        keyfile = instance / 'secret.key'
        try:
            fd = os.open(keyfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, 'w') as stream:
                stream.write(secrets.token_hex(32))
        app.config['SECRET_KEY'] = keyfile.read_text().strip()
        if not app.config['SECRET_KEY']:
            raise RuntimeError('Chiave sessione non disponibile. Riprova l’avvio.')
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()

    CSRFProtect(app)
    from .admin import bp
    app.register_blueprint(bp)
    from .editorial import bp as editorial_bp, home_content
    app.register_blueprint(editorial_bp)
    app.jinja_env.filters.update(
        date_label=date_label,
        event_number=lambda value: value[8:10] if len(value) == 10 else MONTHS[int(value[5:7]) - 1][:3],
        event_month=lambda value: MONTHS[int(value[5:7]) - 1] if len(value) == 10 else value[:4],
    )

    @app.get('/')
    def home():
        today = datetime.now(ZoneInfo('Europe/Rome')).date().isoformat()
        db = get_db()
        events, latest = home_content(db, today)
        intro = db.execute('SELECT * FROM home_intro WHERE id=1').fetchone()
        features = db.execute('SELECT * FROM home_features WHERE published=1 ORDER BY sort_order,id').fetchall()
        return render_template('public/index.html', events=events, latest_news=latest,
                               home_intro=intro, home_features=features)

    @app.get('/scuola-allievi')
    def school():
        teachers = get_db().execute('SELECT * FROM teachers WHERE published=1 ORDER BY sort_order,id').fetchall()
        return render_template('public/scuola-allievi.html', teachers=teachers)

    @app.get('/prossimi-eventi')
    def events():
        return render_template('public/eventi.html', events=get_db().execute('SELECT * FROM events WHERE published=1 ORDER BY date,id').fetchall())

    @app.get('/notizie')
    def news():
        return render_template('public/notizie.html', news=get_db().execute('SELECT * FROM news WHERE published=1 ORDER BY date DESC,id').fetchall())

    @app.get('/notizie/<slug>')
    def article(slug):
        row = get_db().execute('SELECT * FROM news WHERE slug=? AND published=1', (slug,)).fetchone()
        if row is None:
            abort(404)
        return render_template('public/articolo.html', article=row)

    @app.get('/foto')
    def photos():
        return render_template('public/foto.html', albums=get_db().execute(
            "SELECT * FROM albums WHERE published=1 ORDER BY substr(date,1,instr(date || ',',',')-1) DESC,id"
        ).fetchall())

    @app.get('/foto/<slug>')
    def album(slug):
        row = get_db().execute('SELECT * FROM albums WHERE slug=? AND published=1', (slug,)).fetchone()
        if row is None:
            abort(404)
        images = get_db().execute('SELECT * FROM photos WHERE album_id=? AND published=1 ORDER BY sort_order,id', (row['id'],)).fetchall()
        return render_template('public/album.html', album=row, photos=images)

    for page in ('contatti', 'sostienici', 'la-filarmonica'):
        app.add_url_rule(f'/{page}', page, lambda page=page: render_template(f'public/{page}.html'))

    @app.get('/assets/<path:filename>')
    def asset(filename):
        return send_from_directory(ROOT / 'public/assets', filename)

    @app.get('/uploads/<filename>')
    def upload(filename):
        if not re.fullmatch(r'[0-9a-f]{40}\.webp', filename):
            abort(404)
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename, mimetype='image/webp', max_age=86400)

    @app.get('/<filename>')
    def static_file(filename):
        if filename not in {'styles.css', 'gallery.js', 'back-to-top.js', 'section-index.js', 'admin.css', 'admin.js'}:
            abort(404)
        return send_from_directory(ROOT / 'public', filename)

    # Retain every previous incoming URL without serving legacy HTML sources.
    redirects = {}
    for line in (ROOT / 'public/_redirects').read_text().splitlines():
        if line.strip() and not line.startswith('#'):
            source, target, *_ = line.split()
            redirects[source] = target

    def public_url(value):
        """Normalize local public links, leaving external URLs and assets untouched."""
        try:
            parts = urlsplit(value)
        except ValueError:
            return value
        if parts.scheme or parts.netloc:
            return value
        path = parts.path.rstrip('/')
        target = redirects.get(path)
        if not target and path.startswith('/blog/'):
            target = '/notizie/' + path.removeprefix('/blog/').removesuffix('.html')
        if not target and path.startswith(('/notizie/', '/foto/')) and path.endswith('.html'):
            target = path[:-5]
        if not target:
            return value
        destination = urlsplit(target)
        return urlunsplit(('', '', destination.path, parts.query, parts.fragment or destination.fragment))

    def public_body(value):
        body = BeautifulSoup(value, 'html.parser')
        for link in body.find_all('a', href=True):
            link['href'] = public_url(link['href'])
        return str(body)

    app.jinja_env.filters.update(public_url=public_url, public_body=public_body)

    @app.before_request
    def legacy_redirect():
        target = public_url(request.path)
        if target != request.path:
            if request.query_string:
                parts = urlsplit(target)
                target = urlunsplit(parts._replace(query=request.query_string.decode('latin-1')))
            return redirect(target, code=301)

    @app.after_request
    def response_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; img-src 'self' https: data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self' https:; font-src 'self'; object-src 'none'; "
            "base-uri 'self'; form-action 'self'; frame-ancestors 'self'"
        )
        if request.path == '/admin' or request.path.startswith('/admin/'):
            response.headers['Cache-Control'] = 'no-store'
            response.headers['X-Robots-Tag'] = 'noindex, nofollow'
        elif response.mimetype == 'text/html':
            response.headers['Cache-Control'] = 'no-cache'
        return response

    @app.errorhandler(404)
    def not_found(error):
        return render_template('public/404.html'), 404

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        return render_template('errore.html', reason='csrf'), 400

    @app.errorhandler(413)
    def too_large(error):
        return render_template('errore.html', reason='upload_too_large'), 413

    @app.cli.command('serve')
    @click.option('--host', default='127.0.0.1', show_default=True, help='Indirizzo di ascolto.')
    @click.option('--port', type=click.IntRange(1, 65535), default=8080, show_default=True)
    def serve(host, port):
        """Avvia il server di produzione Waitress, senza strumenti esterni."""
        from waitress import serve as waitress_serve

        options = dict(host=host, port=port, max_request_body_size=app.config['MAX_CONTENT_LENGTH'])
        if trust_proxy:
            options.update(trusted_proxy='127.0.0.1', trusted_proxy_count=1,
                           trusted_proxy_headers={'x-forwarded-for', 'x-forwarded-proto'})
        waitress_serve(app, **options)

    @app.cli.command('create-admin')
    @click.option('--admin-id', type=int, help='Identificativo dell’account da reimpostare, se ne esiste più di uno.')
    @click.option('--reset-password', is_flag=True, help='Aggiorna la password di un utente esistente e revoca le sessioni.')
    def create_admin(admin_id, reset_password):
        """Create an administrator interactively; no default password."""
        db = get_db()
        user = None
        if admin_id is not None and not reset_password:
            raise click.ClickException('Usa --admin-id insieme a --reset-password.')
        if reset_password:
            users = db.execute('SELECT id FROM users ORDER BY id').fetchall()
            if admin_id is None and len(users) > 1:
                raise click.ClickException('Più account presenti. Usa --admin-id con uno di questi ID: ' + ', '.join(str(row['id']) for row in users))
            user = next((row for row in users if admin_id is None or row['id'] == admin_id), None)
            if user is None:
                raise click.ClickException('Amministratore non trovato.')
        password = click.prompt('Password', hide_input=True, confirmation_prompt=True)
        with db:
            if user:
                db.execute('UPDATE users SET password_hash=? WHERE id=?', (generate_password_hash(password), user['id']))
                db.execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
            else:
                db.execute('INSERT INTO users(password_hash) VALUES(?)', (generate_password_hash(password),))
        click.echo('Amministratore pronto. Accedi da /admin.')

    @app.cli.command('backup-db')
    @click.argument('destination', type=click.Path(path_type=Path))
    def backup_db(destination):
        """Consistent SQLite backup, including committed WAL data."""
        if destination.exists():
            raise click.ClickException('La destinazione esiste già. Scegli un nuovo file.')
        with closing(sqlite3.connect(destination)) as backup:
            get_db().backup(backup)
        click.echo(f'Backup salvato in {destination}. Copia anche instance/uploads per le immagini.')

    @app.cli.command('check-templates')
    def check_templates():
        for template in app.jinja_env.list_templates():
            app.jinja_env.get_template(template)
        click.echo('Template compilati. Il sito rende le pagine a ogni richiesta.')

    return app
