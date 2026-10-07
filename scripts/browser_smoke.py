"""Real-browser editorial journey, isolated from the user's database.

Run .venv/bin/python scripts/browser_smoke.py after installing requirements-dev.txt.
Uses installed Chromium, or Playwright's Chromium when BROWSER_PATH is supplied.
"""
import io
import os
import re
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


def assert_caption_over_photo(viewer):
    expect(viewer.locator('.photo-viewer-image')).to_be_visible()
    expect(viewer.locator('.photo-viewer-caption')).to_be_visible()
    expect(viewer.locator('.photo-viewer-caption')).to_have_css('background-color', 'rgba(25, 20, 24, 0.75)')
    expect(viewer.locator('.photo-viewer-name')).to_have_css('text-align', 'left')
    expect(viewer.locator('.photo-viewer-instrument')).to_have_css('text-align', 'left')
    assert viewer.evaluate('''(el) => {
        const img = el.querySelector('.photo-viewer-image');
        const image = img.getBoundingClientRect();
        const caption = el.querySelector('.photo-viewer-caption').getBoundingClientRect();
        const name = el.querySelector('.photo-viewer-name').getBoundingClientRect();
        const scale = Math.min(image.width / img.naturalWidth, image.height / img.naturalHeight);
        const width = img.naturalWidth * scale;
        const bottom = image.y + (image.height + img.naturalHeight * scale) / 2;
        return Math.abs(caption.width - width) < 1 &&
            Math.abs(caption.y + caption.height - bottom) < 1 &&
            Math.abs(caption.x + caption.width / 2 - image.x - image.width / 2) < 1 &&
            Math.abs(name.x + name.width / 2 - caption.x - caption.width / 2) < 1;
    }'''), 'Caption band must align with the rendered photo, with equal text padding'



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
                expect(page).to_have_url(re.compile(re.escape(origin) + r'/admin/eventi/\d+/edit$'))
                expect(page.get_by_label('Titolo', exact=False)).to_have_value('Evento prova browser')
                saved_event_url = page.url
                page.get_by_role('button', name='Salva modifiche').click()
                expect(page).to_have_url(saved_event_url)
                page.reload()
                expect(page).to_have_url(saved_event_url)
                page.goto(origin + '/prossimi-eventi')
                expect(page.locator('main')).to_contain_text('Evento prova browser')

                page.goto(origin + '/admin/notizie/new')
                page.get_by_label('Titolo', exact=False).fill('Notizia prova browser')
                page.get_by_label('Indirizzo breve').fill('notizia-prova-browser')
                page.get_by_label('Data', exact=False).fill('2026-10-06')
                page.get_by_label('Sommario').fill('Una notizia scritta dal browser.')
                page.locator('[name="image"]').fill('/assets/concert.jpg')
                page.locator('.editor-content').fill('Testo dal nuovo editor visuale.')
                page.get_by_role('button', name='Salva contenuto').click()
                expect(page).to_have_url(re.compile(re.escape(origin) + r'/admin/notizie/\d+/edit$'))
                page.goto(origin + '/notizie/notizia-prova-browser')
                expect(page.locator('article')).to_contain_text('Testo dal nuovo editor visuale.')
                page.goto(origin + '/notizie')
                news_card = page.locator('a.news-link[href="/notizie/notizia-prova-browser"]')
                image_frame = news_card.locator('.card-image')
                page.mouse.move(0, 0)
                expect(image_frame).to_have_css('transform', 'none')
                frame_before = image_frame.bounding_box()
                news_card.locator('h3').hover()
                expect(image_frame).to_have_css('transform', 'matrix(1.035, 0, 0, 1.035, 0, 0)')
                expect(news_card.locator('img')).to_have_css('transform', 'none')
                frame_after = image_frame.bounding_box()
                assert abs(frame_after['width'] - frame_before['width'] * 1.035) < 1
                assert abs(frame_after['height'] - frame_before['height'] * 1.035) < 1
                expect(image_frame).to_have_css('overflow', 'hidden')
                page.emulate_media(reduced_motion='reduce')
                expect(image_frame).to_have_css('transform', 'none')
                page.emulate_media(reduced_motion='no-preference')
                for selector in ('img', 'h3', '.news-card-copy p'):
                    page.goto(origin + '/notizie')
                    page.locator('a.news-link[href="/notizie/notizia-prova-browser"]').locator(selector).click()
                    expect(page).to_have_url(origin + '/notizie/notizia-prova-browser')

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
                page.locator('[name="url"]').fill('/contatti')
                page.get_by_label('Testo del collegamento', exact=False).fill('Contattaci')
                page.get_by_role('button', name='Salva scheda').click()
                expect(page).to_have_url(re.compile(re.escape(origin) + r'/admin/musica-insieme/\d+/edit$'))
                expect(page.locator('[name="title"]')).to_have_value('Scheda prova browser')
                page.goto(origin + '/admin/musica-insieme')
                move_up = page.get_by_role('button', name='Sposta su: Scheda prova browser', exact=True)
                page.evaluate('window.orderPageMarker = true')
                while move_up.is_enabled():
                    move_up.click()
                    expect(page.locator('.content-list')).to_have_attribute('aria-busy', 'false')
                    assert page.evaluate('window.orderPageMarker === true'), 'Ordering reloaded the page'
                expect(page.locator('.content-row').first).to_contain_text('Scheda prova browser')
                move_down = page.get_by_role('button', name='Sposta giù: Scheda prova browser', exact=True)
                page.route('**/move', lambda route: route.abort())
                move_down.click()
                expect(page.locator('[data-order-error]:visible')).to_have_count(1)
                expect(move_down).to_be_enabled()
                expect(page.locator('.content-row').first).to_contain_text('Scheda prova browser')
                page.unroute('**/move')
                move_down.click()
                expect(page.locator('.content-list')).to_have_attribute('aria-busy', 'false')
                expect(page.locator('.content-row').nth(1)).to_contain_text('Scheda prova browser')
                move_up.click()
                expect(page.locator('.content-list')).to_have_attribute('aria-busy', 'false')
                expect(page.locator('[data-order-error]:visible')).to_have_count(0)
                page.goto(origin)
                expect(page.get_by_role('heading', name='Musica insieme, dalla home')).to_be_visible()
                expect(page.locator('.feature-card').first).to_contain_text('Scheda prova browser')
                expect(page.locator('.feature-card').first).to_have_attribute('href', '/contatti')

                page.goto(origin + '/admin/foto/new')
                page.get_by_label('Titolo', exact=False).fill('Album prova browser')
                page.get_by_label('Indirizzo breve').fill('album-prova-browser')
                page.get_by_label('Date dell’album').fill('2026-10-06, 2026-10-07')
                page.locator('[name="cover"]').fill('/assets/concert.jpg')
                page.get_by_role('button', name='Salva contenuto').click()
                expect(page).to_have_url(re.compile(re.escape(origin) + r'/admin/foto/\d+/edit$'))
                page.get_by_role('link', name='Gestisci le foto').click()
                photo_page = page.url
                image = io.BytesIO()
                Image.new('RGB', (80, 60), '#762038').save(image, 'JPEG')
                page.get_by_label('Carica un’immagine', exact=True).set_input_files(dict(name='prova.jpg', mimeType='image/jpeg', buffer=image.getvalue()))
                page.get_by_label('Descrizione dell’immagine', exact=True).fill('Fotografia caricata dal browser')
                page.get_by_role('button', name='Aggiungi foto').click()
                expect(page.locator('.photo-card')).to_have_count(1)
                photo_card = page.locator('.photo-card').first
                inline_visibility = photo_card.get_by_role('checkbox', name='Nascondi', exact=False)
                expect(photo_card.locator('.row-actions input[type="checkbox"]')).to_have_count(1)
                expect(photo_card.get_by_text('Nascosta', exact=True)).to_have_count(0)
                expect(photo_card.get_by_role('button', name='Salva visibilità')).not_to_be_visible()
                edit_box = photo_card.get_by_role('link', name='Modifica', exact=True).bounding_box()
                checkbox_box = inline_visibility.bounding_box()
                assert abs((edit_box['y'] + edit_box['height'] / 2) - (checkbox_box['y'] + checkbox_box['height'] / 2)) < 3
                inline_visibility.check()
                expect(inline_visibility).to_be_enabled()
                expect(photo_card.get_by_text('Salvato.', exact=True)).to_have_count(0)
                expect(photo_card).to_have_class(re.compile(r'is-hidden'))
                expect(photo_card.locator('img')).to_have_css('opacity', '0.35')
                expect(photo_card.get_by_text('Nascosta', exact=True)).to_have_count(0)
                expect(page).to_have_url(photo_page)
                page.reload()
                expect(inline_visibility).to_be_checked()
                inline_visibility.uncheck()
                expect(inline_visibility).to_be_enabled()
                expect(photo_card.locator('img')).to_have_css('opacity', '1')
                page.route('**/visibility', lambda route: route.abort())
                inline_visibility.check()
                expect(photo_card.locator('[data-visibility-error]')).to_be_visible()
                expect(inline_visibility).not_to_be_checked()
                expect(photo_card.locator('img')).to_have_css('opacity', '1')
                page.unroute('**/visibility')
                page.get_by_role('link', name='Modifica', exact=True).click()
                photo_edit_url = page.url
                page.get_by_label('Nascondi questa foto', exact=True).check()
                page.get_by_role('button', name='Salva modifiche').click()
                expect(page).to_have_url(photo_edit_url)
                expect(page.get_by_label('Nascondi questa foto', exact=True)).to_be_checked()
                page.goto(origin + '/foto/album-prova-browser')
                expect(page.locator('.gallery-photo')).to_have_count(0)
                expect(page.locator('.gallery-empty')).to_be_visible()
                page.goto(photo_edit_url)
                page.get_by_label('Nascondi questa foto', exact=True).uncheck()
                page.get_by_role('button', name='Salva modifiche').click()
                page.goto(origin + '/foto')
                album_card = page.locator('a.album-link[href="/foto/album-prova-browser"]')
                image_frame = album_card.locator('.card-image')
                page.mouse.move(0, 0)
                expect(image_frame).to_have_css('transform', 'none')
                frame_before = image_frame.bounding_box()
                album_card.locator('h3').hover()
                expect(image_frame).to_have_css('transform', 'matrix(1.035, 0, 0, 1.035, 0, 0)')
                expect(album_card.locator('img')).to_have_css('transform', 'none')
                frame_after = image_frame.bounding_box()
                assert abs(frame_after['width'] - frame_before['width'] * 1.035) < 1
                assert abs(frame_after['height'] - frame_before['height'] * 1.035) < 1
                expect(image_frame).to_have_css('overflow', 'hidden')
                album_card.click()
                expect(page.locator('.gallery-hero .eyebrow')).to_have_text('6 - 7 ottobre 2026')
                expect(page.locator('.gallery-photo img')).to_be_visible()
                page.locator('.gallery-photo').hover()
                expect(page.locator('.gallery-photo')).to_have_css('transform', 'matrix(1.035, 0, 0, 1.035, 0, 0)')
                expect(page.locator('.gallery-photo img')).to_have_css('transform', 'none')
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
                page.get_by_role('button', name='Salva insegnante').click()
                expect(page).to_have_url(re.compile(re.escape(origin) + r'/admin/insegnanti/\d+/edit$'))
                expect(page.get_by_label('Nome', exact=False)).to_have_value('Maestra browser Uno\nMaestro browser Due')
                page.goto(origin + '/admin/insegnanti')
                move_up = page.get_by_role('button', name=re.compile('Sposta su: Maestra browser Uno'))
                page.evaluate('window.orderPageMarker = true')
                while move_up.is_enabled():
                    move_up.click()
                    expect(page.locator('.content-list')).to_have_attribute('aria-busy', 'false')
                    assert page.evaluate('window.orderPageMarker === true'), 'Ordering reloaded the page'
                expect(page.locator('.content-row').first).to_contain_text('Maestra browser Uno')
                page.goto(origin + '/scuola-allievi')
                expect(page.locator('.teacher-entry').first).to_contain_text('Maestra browser Uno')
                expect(page.locator('.teacher-entry').first).to_contain_text('Maestro browser Due')
                expect(page.locator('.teacher-entry').first.locator('h3 br')).to_have_count(1)
                expect(page.locator('.teacher-entry').first.locator('img')).to_be_visible()
                teacher_photos = page.locator('.teacher-photo-link')
                teacher_photos.first.hover()
                expect(teacher_photos.first).to_have_css('transform', 'matrix(1.15, 0, 0, 1.15, 0, 0)')
                teacher_photos.first.click()
                teacher_viewer = page.get_by_role('dialog', name='Galleria fotografica')
                expect(teacher_viewer).to_be_visible()
                expect(teacher_viewer.locator('.photo-viewer-name')).to_have_text('Maestra browser Uno\nMaestro browser Due')
                expect(teacher_viewer.locator('.photo-viewer-instrument')).to_have_text('Violino')
                expect(teacher_viewer.locator('.photo-viewer-image')).to_have_css('object-fit', 'contain')
                assert_caption_over_photo(teacher_viewer)
                page.screenshot(path=output / 'teacher-gallery-desktop.png')
                page.get_by_role('button', name='Foto successiva', exact=True).click()
                expect(teacher_viewer.locator('.photo-viewer-name')).to_have_text(teacher_photos.nth(1).get_attribute('data-caption-name'))
                expect(teacher_viewer.locator('.photo-viewer-instrument')).to_have_text(teacher_photos.nth(1).get_attribute('data-caption-instrument'))
                page.keyboard.press('ArrowLeft')
                expect(teacher_viewer.locator('.photo-viewer-instrument')).to_have_text('Violino')
                page.keyboard.press('Escape')
                expect(teacher_viewer).not_to_be_visible()
                expect(teacher_photos.first).to_be_focused()

                touch_context = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
                touch_page = touch_context.new_page()
                touch_page.goto(origin + '/scuola-allievi')
                touch_photo = touch_page.locator('.teacher-photo-link').first
                touch_photo.scroll_into_view_if_needed()
                touch_viewer = touch_page.get_by_role('dialog', name='Galleria fotografica')
                expect(touch_photo).to_have_css('transform', 'none')
                expect(touch_viewer).not_to_be_visible()
                touch_photo.tap()
                expect(touch_viewer).to_be_visible()
                expect(touch_viewer.locator('.photo-viewer-name')).to_have_text('Maestra browser Uno\nMaestro browser Due')
                expect(touch_viewer.locator('.photo-viewer-instrument')).to_have_text('Violino')
                assert_caption_over_photo(touch_viewer)
                touch_page.screenshot(path=output / 'teacher-gallery-mobile.png')
                touch_page.get_by_role('button', name='Foto successiva', exact=True).tap()
                expect(touch_viewer.locator('.photo-viewer-counter')).to_have_text(f'Foto 2 di {teacher_photos.count()}')
                assert_caption_over_photo(touch_viewer)
                for viewport in ({'width': 320, 'height': 568}, {'width': 844, 'height': 390}):
                    touch_page.set_viewport_size(viewport)
                    margin = 4 if viewport['width'] <= 700 else 8
                    touch_page.wait_for_function('(margin) => document.querySelector(".photo-viewer").clientWidth === innerWidth - 2 * margin', arg=margin)
                    assert_caption_over_photo(touch_viewer)
                touch_page.get_by_role('button', name='Chiudi galleria', exact=True).tap()
                expect(touch_viewer).not_to_be_visible()
                assert touch_page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                touch_context.close()

                for section in ('eventi', 'notizie', 'foto', 'musica-insieme', 'insegnanti'):
                    page.goto(origin + '/admin/' + section)
                    row = page.locator('.content-row').first
                    publication = row.locator('[data-publication]')
                    checkbox = publication.get_by_role('checkbox', name=re.compile('^Nascosto'))
                    control_box = publication.bounding_box()
                    edit_box = row.get_by_role('link', name=re.compile('^Modifica')).bounding_box()
                    assert control_box['x'] + control_box['width'] <= edit_box['x']
                    assert abs((control_box['y'] + control_box['height'] / 2) - (edit_box['y'] + edit_box['height'] / 2)) < 3
                    expect(checkbox).not_to_be_checked()
                    page.evaluate('window.publicationPageMarker = true')
                    checkbox.check()
                    expect(checkbox).to_be_enabled()
                    expect(row).to_have_css('opacity', '0.4')
                    expect(publication.locator('[data-publication-error]')).not_to_be_visible()
                    assert page.evaluate('window.publicationPageMarker === true')
                    page.reload()
                    expect(checkbox).to_be_checked()
                    expect(row).to_have_css('opacity', '0.4')
                    checkbox.uncheck()
                    expect(checkbox).to_be_enabled()
                    expect(row).to_have_css('opacity', '1')
                    page.route('**/publication', lambda route: route.abort())
                    checkbox.check()
                    expect(publication.locator('[data-publication-error]')).to_be_visible()
                    expect(checkbox).not_to_be_checked()
                    expect(row).to_have_css('opacity', '1')
                    page.unroute('**/publication')
                    page.reload()
                    expect(checkbox).not_to_be_checked()

                for width in (1440, 390, 320):
                    page.set_viewport_size({'width': width, 'height': 900})
                    page.goto(origin + '/la-filarmonica', wait_until='domcontentloaded')
                    history = page.locator('.history-photos')
                    pictures = history.locator('.gallery-photo')
                    expect(pictures).to_have_count(3)
                    assert history.evaluate('el => el.scrollWidth <= el.clientWidth')
                    columns = history.evaluate('el => getComputedStyle(el).gridTemplateColumns.split(" ").length')
                    assert columns == (3 if width == 1440 else 1)
                    sizes = pictures.evaluate_all('(items) => items.map(el => ({width: el.clientWidth, height: el.clientHeight}))')
                    assert max(size['height'] for size in sizes) - min(size['height'] for size in sizes) <= 1
                    for picture in pictures.all():
                        picture.scroll_into_view_if_needed()
                        picture.locator('img').evaluate('(img) => img.decode()')
                        assert picture.evaluate('''(el) => {
                            const img = el.querySelector('img');
                            const frame = el.getBoundingClientRect();
                            const image = img.getBoundingClientRect();
                            return Math.abs(frame.width - image.width) < 1 &&
                                Math.abs(image.height - image.width * img.naturalHeight / img.naturalWidth) < 1 &&
                                Math.abs(frame.y + frame.height / 2 - image.y - image.height / 2) < 1;
                        }'''), 'History thumbnail must retain full width and crop vertically from the center'
                    pictures.nth(1).hover()
                    expect(pictures.nth(1)).to_have_css('transform', 'matrix(1.035, 0, 0, 1.035, 0, 0)')
                    assert pictures.nth(1).evaluate('(el) => Math.abs(el.getBoundingClientRect().width - el.querySelector("img").getBoundingClientRect().width) < 1')
                    expect(pictures.nth(1)).to_have_css('overflow', 'hidden')
                    page.emulate_media(reduced_motion='reduce')
                    expect(pictures.nth(1)).to_have_css('transform', 'none')
                    page.emulate_media(reduced_motion='no-preference')
                    pictures.nth(1).click()
                    viewer = page.get_by_role('dialog', name='Galleria fotografica')
                    expect(viewer).to_be_visible()
                    expect(viewer.locator('.photo-viewer-counter')).to_have_text('Foto 2 di 3')
                    expect(viewer.locator('img')).to_be_visible()
                    page.get_by_role('button', name='Foto successiva', exact=True).click()
                    expect(viewer.locator('.photo-viewer-counter')).to_have_text('Foto 3 di 3')
                    expect(viewer.locator('img')).to_have_attribute('src', origin + '/assets/storia-gruppo.jpg')
                    page.keyboard.press('ArrowLeft')
                    expect(viewer.locator('.photo-viewer-counter')).to_have_text('Foto 2 di 3')
                    page.get_by_role('button', name='Foto precedente', exact=True).click()
                    expect(viewer.locator('.photo-viewer-counter')).to_have_text('Foto 1 di 3')
                    page.get_by_role('button', name='Chiudi galleria', exact=True).click()
                    expect(viewer).not_to_be_visible()
                    expect(pictures.nth(1)).to_be_focused()
                    pictures.last.click()
                    expect(viewer.locator('.photo-viewer-counter')).to_have_text('Foto 3 di 3')
                    page.keyboard.press('Escape')
                    expect(viewer).not_to_be_visible()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    history.screenshot(path=output / f'history-gallery-{width}.png')

                page.set_viewport_size({'width': 390, 'height': 844})
                for path in ('/', '/scuola-allievi', '/admin', '/admin/notizie/new',
                             '/admin/home', '/admin/musica-insieme', '/admin/musica-insieme/new',
                             '/admin/insegnanti', '/admin/insegnanti/new', photo_page.removeprefix(origin)):
                    page.goto(origin + path, wait_until='domcontentloaded')
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Horizontal overflow: {path}'
                    if path == photo_page.removeprefix(origin):
                        actions = page.locator('.photo-card .row-actions').first
                        assert actions.evaluate('(element) => element.scrollWidth <= element.clientWidth'), 'Photo actions clipped on mobile'
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
