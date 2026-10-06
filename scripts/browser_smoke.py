"""Real-browser editorial journey, isolated from the user's database.

Run .venv/bin/python scripts/browser_smoke.py after installing requirements-dev.txt.
Uses installed Chromium, or Playwright's Chromium when BROWSER_PATH is supplied.
"""
import io
import os
from pathlib import Path
import secrets
import shutil
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image
from playwright.sync_api import sync_playwright, expect
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server, WSGIRequestHandler

from app import create_app
from app.db import get_db


class QuietHandler(WSGIRequestHandler):
    def log_request(self, *args, **kwargs):
        pass


def run():
    output = Path('test-results')
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='filarmonica-browser-') as directory:
        app = create_app(dict(TESTING=True, INSTANCE_PATH=directory, SECRET_KEY=secrets.token_hex(32)))
        password = secrets.token_urlsafe(24)
        with app.app_context():
            db = get_db()
            db.execute('INSERT INTO users(password_hash) VALUES(?)', (generate_password_hash(password),))
            db.commit()
        server = make_server('127.0.0.1', 0, app, threaded=True, request_handler=QuietHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        origin = f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as playwright:
                executable = os.environ.get('BROWSER_PATH') or shutil.which('chromium')
                browser = playwright.chromium.launch(executable_path=executable, headless=True)
                context = browser.new_context(viewport={'width': 1440, 'height': 1000})
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                # Only local assets affect layout assertions; external photo availability
                # is independent of this test and is not required for an offline run.
                context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(origin) else route.abort())
                page.goto(origin, wait_until='domcontentloaded')
                expect(page.locator('main h1')).to_contain_text('Giuseppe Verdi')
                assert page.locator('a[href^="/admin"]').count() == 0
                page.screenshot(path=output / 'home-desktop.png', full_page=True)
                page.goto(origin + '/admin', wait_until='domcontentloaded')
                page.screenshot(path=output / 'admin-login.png', full_page=True)
                expect(page.locator('input[name="username"]')).to_have_count(0)
                page.get_by_label('Password', exact=True).fill(password)
                page.get_by_role('button', name='Accedi').click()
                expect(page.locator('.dashboard-card')).to_have_count(6)
                page.screenshot(path=output / 'admin-desktop.png', full_page=True)
                page.locator('.dashboard-card[href="/admin/eventi"]').click()
                page.get_by_role('link', name='Aggiungi evento').first.click()
                page.get_by_label('Titolo', exact=False).fill('Evento prova browser')
                page.get_by_label('Indirizzo breve').fill('evento-prova-browser')
                page.get_by_label('Data', exact=False).fill('2026-12-20')
                page.get_by_label('Luogo', exact=False).fill('Lecco')
                page.get_by_role('button', name='Salva contenuto').click()
                expect(page.locator('.content-row').filter(has_text='Evento prova browser')).to_have_count(1)
                page.goto(origin + '/prossimi-eventi.html')
                expect(page.locator('main')).to_contain_text('Evento prova browser')

                page.goto(origin + '/admin/notizie/new')
                page.get_by_label('Titolo', exact=False).fill('Notizia prova browser')
                page.get_by_label('Indirizzo breve').fill('notizia-prova-browser')
                page.get_by_label('Data', exact=False).fill('2026-10-06')
                page.get_by_label('Sommario').fill('Una notizia scritta dal browser.')
                page.locator('.editor-content').fill('Testo dal nuovo editor visuale.')
                page.get_by_role('button', name='Salva contenuto').click()
                expect(page).to_have_url(origin + '/admin/notizie')
                page.goto(origin + '/blog/notizia-prova-browser.html')
                expect(page.locator('article')).to_contain_text('Testo dal nuovo editor visuale.')

                page.goto(origin + '/admin/notizie/new')
                page.get_by_label('Titolo', exact=False).fill('Notizia archivio browser')
                page.get_by_label('Indirizzo breve').fill('notizia-archivio-browser')
                page.get_by_label('Data', exact=False).fill('2000-01-01')
                page.get_by_label('Sommario').fill('Una notizia da scegliere per la home.')
                page.locator('.editor-content').fill('Una notizia precedente, scelta manualmente.')
                page.get_by_role('button', name='Salva contenuto').click()
                page.goto(origin + '/admin/home')
                page.get_by_label('Evento prova browser', exact=False).check()
                page.get_by_label('Notizia archivio browser', exact=False).check()
                page.get_by_role('button', name='Salva selezione').click()
                page.goto(origin)
                expect(page.locator('.event-row')).to_have_count(1)
                expect(page.locator('.event-row')).to_contain_text('Evento prova browser')
                expect(page.locator('.news-card')).to_have_count(1)
                expect(page.locator('.news-card')).to_contain_text('Notizia archivio browser')

                page.goto(origin + '/admin/musica-insieme')
                page.locator('[name="title"]').fill('Musica insieme, dalla home')
                page.get_by_role('button', name='Salva intestazione').click()
                page.get_by_role('link', name='Aggiungi scheda', exact=False).first.click()
                page.get_by_label('Sopratitolo', exact=True).fill('La comunità')
                page.locator('[name="title"]').fill('Scheda prova browser')
                page.get_by_label('Descrizione', exact=False).fill('Una nuova scheda gestita dal browser.')
                page.locator('[name="url"]').fill('/contatti.html')
                page.get_by_label('Testo del collegamento', exact=False).fill('Contattaci')
                page.get_by_label('Ordine', exact=True).fill('-1')
                page.get_by_role('button', name='Salva scheda').click()
                expect(page.locator('.content-row').filter(has_text='Scheda prova browser')).to_have_count(1)
                page.goto(origin)
                expect(page.get_by_role('heading', name='Musica insieme, dalla home')).to_be_visible()
                expect(page.locator('.feature-card').first).to_contain_text('Scheda prova browser')
                expect(page.locator('.feature-card').first).to_have_attribute('href', '/contatti.html')

                page.goto(origin + '/admin/foto/new')
                page.get_by_label('Titolo', exact=False).fill('Album prova browser')
                page.get_by_label('Indirizzo breve').fill('album-prova-browser')
                page.get_by_label('Mese e anno').fill('2026-10')
                page.get_by_role('button', name='Salva contenuto').click()
                photo_page = page.url
                image = io.BytesIO()
                Image.new('RGB', (80, 60), '#762038').save(image, 'JPEG')
                page.get_by_label('Carica un’immagine', exact=True).set_input_files(dict(name='prova.jpg', mimeType='image/jpeg', buffer=image.getvalue()))
                page.get_by_label('Descrizione dell’immagine', exact=True).fill('Fotografia caricata dal browser')
                page.get_by_role('button', name='Aggiungi foto').click()
                expect(page.locator('.photo-card')).to_have_count(1)
                page.goto(origin + '/foto/album-prova-browser.html')
                expect(page.locator('.gallery-photo img')).to_be_visible()
                page.locator('.gallery-photo').click()
                expect(page.locator('dialog')).to_be_visible()
                expect(page.locator('.photo-viewer-image')).to_be_visible()
                page.get_by_role('button', name='Chiudi galleria').click()

                page.goto(origin + '/admin/insegnanti/new')
                page.get_by_label('Nome', exact=False).fill('Maestra browser Uno\nMaestro browser Due')
                page.get_by_label('Strumento o corso', exact=False).fill('Violino')
                page.get_by_label('Oppure carica una fotografia', exact=True).set_input_files(
                    dict(name='insegnante.jpg', mimeType='image/jpeg', buffer=image.getvalue()))
                page.get_by_label('Descrizione della fotografia', exact=True).fill('La nostra nuova insegnante')
                page.get_by_label('Ordine', exact=True).fill('-1')
                page.get_by_role('button', name='Salva insegnante').click()
                expect(page.locator('.content-row').filter(has_text='Maestra browser Uno')).to_have_count(1)
                page.goto(origin + '/scuola-allievi.html')
                expect(page.locator('.teacher-entry').first).to_contain_text('Maestra browser Uno')
                expect(page.locator('.teacher-entry').first).to_contain_text('Maestro browser Due')
                expect(page.locator('.teacher-entry').first.locator('h3 br')).to_have_count(1)
                expect(page.locator('.teacher-entry').first.locator('img')).to_be_visible()

                page.set_viewport_size({'width': 390, 'height': 844})
                for path in ('/', '/scuola-allievi.html', '/admin', '/admin/notizie/new',
                             '/admin/home', '/admin/musica-insieme', '/admin/musica-insieme/new',
                             '/admin/insegnanti', '/admin/insegnanti/new', photo_page.removeprefix(origin)):
                    page.goto(origin + path, wait_until='domcontentloaded')
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Horizontal overflow: {path}'
                    if path == '/admin':
                        expect(page.locator('.dashboard-card')).to_have_count(6)
                        page.screenshot(path=output / 'admin-mobile.png', full_page=True)
                    if path == '/':
                        page.screenshot(path=output / 'home-mobile.png', full_page=True)
                page.goto(origin + '/admin')
                page.get_by_role('button', name='Esci', exact=True).click()
                expect(page.get_by_label('Password', exact=True)).to_be_visible()
                page.goto(origin + '/admin/notizie')
                expect(page.get_by_label('Password', exact=True)).to_be_visible()
                assert not errors, errors
                browser.close()
                print('Browser smoke passed: login, dashboard, event/news/album editing, home selections and cards, teachers, image uploads, gallery, mobile layout, logout. Screenshots: test-results/.')
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)


if __name__ == '__main__':
    run()
