"""Exercise the public website and authenticated editing through real HTTP forms."""

import hashlib
import io
from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from PIL import Image
from werkzeug.security import generate_password_hash

from app import ROOT, create_app
from app.db import get_db
from app.drive import DriveError


TABLES = {"eventi": "events", "notizie": "news", "foto": "albums"}
PUBLIC_PAGES = {
    "eventi": "/prossimi-eventi",
    "notizie": "/notizie", "foto": "/foto",
}


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = "Password-di-prova-2026"
        cls.password_hash = generate_password_hash(cls.password)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="filarmonica-tests-")
        self.addCleanup(temporary.cleanup)
        self.instance = Path(temporary.name)
        self.config = {
            "INSTANCE_PATH": str(self.instance), "DATABASE": str(self.instance / "site.sqlite3"),
            "UPLOAD_FOLDER": str(self.instance / "uploads"), "SECRET_KEY": "test",
            "TESTING": True,
        }
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        with self.app.app_context():
            db = get_db()
            db.execute("INSERT INTO users(password_hash) VALUES(?)", (self.password_hash,))
            db.executescript("""
                INSERT INTO events(slug,title,date,location,description)
                VALUES('concerto-prova','Concerto di prova','2039-06-02','Lecco','Ingresso libero.');
                INSERT INTO news(slug,title,date,summary,body,image,image_alt,external_url) VALUES
                ('notizia-prova','Notizia di prova','2039-06-01','Novità dalla banda.',
                 '<p>Una notizia di prova.</p>','/assets/concert.jpg','Concerto',''),
                ('notizia-esterna','Notizia esterna','2039-05-01','Una notizia dalla stampa.',
                 '','','','https://example.com/notizia-esterna');
                INSERT INTO albums(slug,title,date,description,cover,cover_alt) VALUES
                ('album-prova','Album di prova','2039-06','Ricordi del concerto.',
                 '/assets/concert.jpg','Concerto'),
                ('album-vuoto','Album senza foto','2039-05','','','');
                INSERT INTO photos(album_id,src,alt,sort_order,source) VALUES
                (1,'/assets/concert.jpg','Il concerto',0,'link'),
                (1,'/assets/emanuela-milani.jpg','La flautista',1,'link');
            """)
            db.commit()

    @staticmethod
    def soup(response):
        return BeautifulSoup(response.get_data(as_text=True), "html.parser")

    def rows(self, sql, parameters=()):
        with self.app.app_context():
            return [dict(row) for row in get_db().execute(sql, parameters).fetchall()]

    def row(self, table, record_id):
        result = self.rows(f"SELECT * FROM {table} WHERE id=?", (record_id,))
        return result[0] if result else None

    def csrf(self, path="/admin"):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:500])
        token = self.soup(response).select_one('input[name="csrf_token"]')
        self.assertIsNotNone(token, path)
        return token["value"]

    def submit(self, path, data=None, *, token_page=None, expected=302):
        payload = dict(data or {})
        payload["csrf_token"] = self.csrf(token_page or path)
        response = self.client.post(path, data=payload)
        self.assertEqual(response.status_code, expected, response.get_data(as_text=True)[:1500])
        return response

    def login(self):
        response = self.submit("/admin", {"password": self.password})
        self.assertEqual(response.location.rstrip("/"), "/admin")
        return self.client.get("/admin")

    @staticmethod
    def content_data(section, suffix="uno"):
        common = {"published": "1"}
        common.update(title=f"Contenuto prova {section} {suffix}", slug=f"prova-{section}-{suffix}", date="2040-06-02")
        if section == "eventi":
            return dict(common, location="Lecco", description="Concerto alle ore 21:00.\nIngresso libero.")
        if section == "notizie":
            return dict(common, summary="Una nuova iniziativa della Filarmonica.",
                        body="<h2>Il programma</h2><p>Musica <strong>per tutti</strong>.</p>",
                        external_url="", image="/assets/concert.jpg", image_alt="Il concerto")
        return dict(common, date="2040-06", description="Ricordi del concerto", folder="",
                    cover="/assets/concert.jpg", cover_alt="Copertina album", cover_position="50% 30%")

    def create_content(self, section, suffix="uno"):
        data = self.content_data(section, suffix)
        response = self.submit(f"/admin/{section}/new", data)
        table = TABLES[section]
        record = self.rows(f"SELECT * FROM {table} WHERE slug=?", (data["slug"],))[0]
        self.assertEqual(response.location, f'/admin/{section}/{record["id"]}/edit')
        return record, data

    def assert_original_teachers(self, page):
        expected = [
            ("Emanuela Milani", "Flauto", "/assets/emanuela-milani.jpg", "Emanuela Milani", "894"),
            ("Francesco Chimienti", "Clarinetto", "/assets/francesco-chimienti.jpg", "Francesco Chimienti", "640"),
            ("Gabriele Rota", "Sassofono", "/assets/gabriele-rota.jpg", "Gabriele Rota", "2160"),
            ("Massimiliano Crotta", "Ottoni", "/assets/massimiliano-crotta.jpg", "Massimiliano Crotta", "743"),
            ("Tiziano Rusconi", "Percussioni", "/assets/tiziano-rusconi.jpg", "Tiziano Rusconi", "930"),
            ("Arianna Mandelli Giulia Longhi", "Propedeutica", "/assets/arianna-mandelli-giulia-longhi.jpg",
             "Arianna Mandelli e Giulia Longhi", "1414"),
        ]
        teachers = page.select(".teachers-grid .teacher-entry")
        self.assertEqual(len(teachers), 6)
        for entry, (names, instrument, src, alt, size) in zip(teachers, expected):
            self.assertEqual(entry.h3.get_text(" ", strip=True), names)
            self.assertEqual(entry.select_one(".eyebrow").get_text(strip=True), instrument)
            image = entry.select_one("img.teacher-photo")
            self.assertEqual((image["src"], image["alt"], image["width"], image["height"]), (src, alt, size, size))
            self.assertEqual(image["loading"], "lazy")
            link = entry.select_one('a.gallery-photo')
            self.assertEqual(link['href'], src)
            self.assertEqual(link['data-caption-name'].replace('\n', ' '), names)
            self.assertEqual(link['data-caption-instrument'], instrument)
        self.assertEqual(len(teachers[-1].select("h3.teacher-names br")), 1)

    def test_news_listing_uses_italian_url_and_redirects_old_listing(self):
        for path in ('/blog.html', '/blog', '/archivio-notizie'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 301)
            self.assertEqual(response.location, '/notizie')
        for path in ('/blog/notizia-prova.html', '/blog/notizia-prova'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 301)
            self.assertEqual(response.location, '/notizie/notizia-prova')
        for path in ('/', '/notizie', '/notizie/notizia-prova'):
            page = self.soup(self.client.get(path))
            self.assertIsNone(page.select_one('a[href="/blog"]'))
            self.assertIsNotNone(page.select_one('a[href="/notizie"]'))

    def test_extensionless_urls_and_legacy_redirects_preserve_queries(self):
        pages = ('la-filarmonica', 'scuola-allievi', 'prossimi-eventi', 'notizie', 'foto', 'sostienici', 'contatti')
        pairs = [('/index.html', '/'), *[(f'/{page}.html', f'/{page}') for page in pages],
                 ('/notizie/notizia-prova.html', '/notizie/notizia-prova'),
                 ('/foto/album-prova.html', '/foto/album-prova'),
                 ('/blog/notizia-prova.html', '/notizie/notizia-prova')]
        for old, new in pairs:
            with self.subTest(old=old):
                response = self.client.get(old + '?source=archive&label=a%20b')
                self.assertEqual(response.status_code, 301)
                self.assertEqual(response.location, new + '?source=archive&label=a%20b')
                self.assertEqual(self.client.get(response.location).status_code, 200)
        response = self.client.get('/chi-siamo-storia.html?source=archive')
        self.assertEqual(response.location, '/la-filarmonica?source=archive#storia')
        self.assertEqual(self.client.get('/unknown.html').status_code, 404)

    def test_saved_legacy_links_render_extensionless_without_changing_storage(self):
        body = ('<p><a href="/foto/album-prova.html?source=news#foto">Album</a>'
                '<a href="https://example.com/page.html">External</a></p>')
        with self.app.app_context():
            db = get_db()
            db.execute('UPDATE home_features SET url=? WHERE id=1', ('/scuola-allievi.html#maestri',))
            db.execute('UPDATE news SET body=? WHERE id=1', (body,))
            db.commit()
        page = self.soup(self.client.get('/'))
        self.assertEqual(page.select_one('.feature-card')['href'], '/scuola-allievi#maestri')
        page = self.soup(self.client.get('/notizie/notizia-prova'))
        self.assertEqual([link['href'] for link in page.select('.prose a')],
                         ['/foto/album-prova?source=news#foto', 'https://example.com/page.html'])
        self.assertEqual(self.row('news', 1)['body'], body)
        self.assertEqual(self.row('home_features', 1)['url'], '/scuola-allievi.html#maestri')
        normalise = self.app.jinja_env.filters['public_url']
        for unchanged in ('/assets/photo.jpg', '/uploads/photo.webp', 'https://example.com/page.html', '/admin', '#storia'):
            self.assertEqual(normalise(unchanged), unchanged)

    def test_public_pages_preserve_content_navigation_and_hide_admin(self):
        expected = {
            "/": "Filarmonica",
            "/la-filarmonica": "Una storia iniziata nel 1809",
            "/scuola-allievi": "Emanuela Milani",
            "/prossimi-eventi": "Concerto di prova",
            "/notizie": "Notizia di prova",
            "/foto": "Fotografie", "/sostienici": "IT53Z0306909606100000150858",
            "/contatti": "bandaverdilecco@libero.it",
        }
        for path, text in expected.items():
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                page = self.soup(response)
                self.assertIn(text, page.get_text(" ", strip=True))
                for selector in ("main", ".site-header", ".site-footer"):
                    self.assertEqual(len(page.select(selector)), 1)
                self.assertEqual(len(page.select(".main-nav a")), 8)
                self.assertTrue(page.select('.main-nav a[aria-current="page"]'))
                self.assertFalse(page.select('a[href^="/admin"]'))
                self.assertFalse(page.select('a[href^="/"][href*=".html"]'))
                for element in page.select("a[href], img[src], script[src], link[href]"):
                    value = element.get("href", element.get("src"))
                    self.assertTrue(value.startswith(("/", "#", "https:", "mailto:", "tel:")), value)
        self.assertEqual(self.client.get("/pagina-inesistente").status_code, 404)

    def test_existing_school_teachers_are_preserved_and_can_be_managed(self):
        self.assert_original_teachers(self.soup(self.client.get("/scuola-allievi")))
        self.assertEqual(len(self.rows("SELECT * FROM teachers")), 6)
        dashboard = self.soup(self.login())
        self.assertTrue(dashboard.select('a[href="/admin/insegnanti"]'))
        for suffix in ("", "/new", "/1/edit", "/1/delete"):
            with self.subTest(suffix=suffix):
                self.assertEqual(self.client.get("/admin/insegnanti" + suffix).status_code, 200)
        self.assert_original_teachers(self.soup(self.client.get("/scuola-allievi")))

    def test_news_and_album_urls_and_galleries_render_database_content(self):
        articles = self.rows("SELECT * FROM news ORDER BY id")
        current_news = self.soup(self.client.get("/notizie"))
        current_links = {link["href"] for link in current_news.select(".news-list a")}
        self.assertEqual(len(articles), 2)
        self.assertEqual(sum(bool(article["external_url"]) for article in articles), 1)
        for article in articles:
            expected = article["external_url"] or f"/notizie/{article['slug']}"
            self.assertIn(expected, current_links)
            if not article["external_url"]:
                response = self.client.get(expected)
                self.assertEqual(response.status_code, 200, expected)
                page = self.soup(response)
                self.assertEqual(page.h1.get_text(), article["title"])
                self.assertEqual(len(page.select("article.prose img.page-image")), 1)
                self.assertTrue(page.select('.main-nav a[href="/notizie"][aria-current="true"]'))
        albums = self.rows("SELECT * FROM albums ORDER BY id")
        total_photos = 0
        for album in albums:
            response = self.client.get(f"/foto/{album['slug']}")
            self.assertEqual(response.status_code, 200, album["slug"])
            page = self.soup(response)
            self.assertEqual(page.h1.get_text(), album["title"])
            self.assertTrue(page.select('script[src="/gallery.js"]'))
            self.assertTrue(page.select('.main-nav a[href="/foto"][aria-current="true"]'))
            images = page.select("a.gallery-photo")
            photos = self.rows("SELECT * FROM photos WHERE album_id=? ORDER BY sort_order,id", (album["id"],))
            self.assertEqual(len(images), len(photos), album["slug"])
            total_photos += len(images)
            for image, photo in zip(images, photos):
                self.assertEqual(image["data-original"], photo["original"] or photo["src"])
                self.assertEqual(image.img["src"], photo["thumbnail"] or photo["src"])
                self.assertEqual(image.img["alt"], photo["alt"])
            if not photos:
                self.assertTrue(page.select_one(".gallery-empty"))
        self.assertEqual(len(albums), 2)
        self.assertEqual(total_photos, 2)

    def test_news_cards_link_images_and_copy_and_album_cards_omit_open_label(self):
        for path in ('/notizie', '/'):
            page = self.soup(self.client.get(path))
            links = page.select('.news-list .news-link, .news-card .news-link')
            self.assertTrue(links)
            for link in links:
                self.assertTrue(link.select_one('h3'))
                self.assertTrue(link.select_one('.news-card-copy p'))
                self.assertFalse(link.select('a'))
                image = link.parent.select_one('img')
                if image:
                    self.assertEqual(image.find_parent('a'), link)
                if link['href'].startswith('https:'):
                    self.assertEqual(link['target'], '_blank')
                    self.assertIn('noopener', link['rel'])
                else:
                    self.assertTrue(link['href'].startswith('/notizie/'))
        archive = self.soup(self.client.get('/foto'))
        self.assertTrue(archive.select('.album-link'))
        self.assertFalse(archive.select('.album-open'))
        self.assertNotIn('Apri album', archive.get_text())

    def test_legacy_redirects_preserve_destinations(self):
        for line in (ROOT / "public/_redirects").read_text().splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            source, destination, *_ = line.split()
            with self.subTest(path=source):
                response = self.client.get(source)
                self.assertEqual(response.status_code, 301)
                self.assertEqual(response.location, destination)

    def test_homepage_keeps_current_month_events_to_month_end_and_updates_news(self):
        with self.app.app_context():
            db = get_db()
            db.execute("DELETE FROM events")
            entries = [
                ("past-day", "Evento passato", "2026-10-01", 1),
                ("past-month", "Mese passato", "2026-09", 1),
                ("month", "Ottobre da definire", "2026-10", 1),
                ("today", "Concerto di oggi", "2026-10-31", 1),
                ("next", "Prossimo concerto", "2026-11-01", 1),
                ("later", "Quarto appuntamento", "2026-12-01", 1),
                ("draft", "Evento in bozza", "2026-10-31", 0),
            ]
            db.executemany("INSERT INTO events(slug,title,date,published) VALUES(?,?,?,?)", entries)
            db.commit()
        with patch("app.datetime") as clock:
            clock.now.return_value = datetime(2026, 10, 31, 22, 0, tzinfo=ZoneInfo("Europe/Rome"))
            page = self.soup(self.client.get("/"))
            self.assertEqual([entry.h3.get_text() for entry in page.select(".event-row")],
                             ["Ottobre da definire", "Concerto di oggi", "Prossimo concerto"])
            clock.now.return_value = datetime(2026, 11, 1, 1, 0, tzinfo=ZoneInfo("Europe/Rome"))
            next_day = self.soup(self.client.get("/"))
            self.assertEqual([entry.h3.get_text() for entry in next_day.select(".event-row")],
                             ["Prossimo concerto", "Quarto appuntamento"])
        self.login()
        article, data = self.create_content("notizie")
        self.assertEqual(self.soup(self.client.get("/")).select_one(".news-card h3").get_text(), data["title"])
        data.pop("published")
        self.submit(f"/admin/notizie/{article['id']}/publication", {'hidden': '1'}, token_page='/admin/notizie')
        self.assertNotIn(data["title"], self.client.get("/").get_data(as_text=True))

    def test_anonymous_management_routes_require_login_and_cannot_modify_content(self):
        before = {table: self.rows(f"SELECT * FROM {table}") for table in (*TABLES.values(), "photos")}
        token = self.csrf()
        for section in TABLES:
            for suffix in ("", "/new", "/1/edit", "/1/delete"):
                path = f"/admin/{section}{suffix}"
                with self.subTest(path=path):
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(response.location.rstrip("/"), "/admin")
                    if suffix:
                        response = self.client.post(path, data={"csrf_token": token, **self.content_data(section)})
                        self.assertEqual(response.status_code, 302)
                        self.assertEqual(response.location.rstrip("/"), "/admin")
        photo = self.rows("SELECT * FROM photos LIMIT 1")[0]
        gallery = f"/admin/foto/{photo['album_id']}/photos"
        for path in (gallery, f"{gallery}/{photo['id']}/edit", f"{gallery}/{photo['id']}/delete"):
            self.assertEqual(self.client.get(path).status_code, 302)
            self.assertEqual(self.client.post(path, data={"csrf_token": token, "src": "/assets/concert.jpg"}).status_code, 302)
        self.assertEqual(self.client.post(f"/admin/foto/{photo['album_id']}/sync", data={"csrf_token": token}).status_code, 302)
        for table, original in before.items():
            self.assertEqual(self.rows(f"SELECT * FROM {table}"), original)

    def test_login_dashboard_session_and_logout(self):
        login_page = self.client.get("/admin")
        self.assertTrue(self.soup(login_page).select('input[type="password"]'))
        self.assertFalse(self.soup(login_page).select('input[name="username"]'))
        self.assertEqual(login_page.headers["Cache-Control"], "no-store")
        self.assertEqual(login_page.headers["X-Robots-Tag"], "noindex, nofollow")
        self.submit("/admin", {"password": "wrong-password"}, expected=401)
        self.assertEqual(self.rows("SELECT * FROM sessions"), [])
        page = self.soup(self.login())
        for section in TABLES:
            self.assertTrue(page.select(f'a[href="/admin/{section}"]'))
        self.assertCountEqual([link["href"] for link in page.select(".dashboard-card")],
                              [f"/admin/{section}" for section in (*TABLES, "home", "musica-insieme", "insegnanti")])
        self.assertEqual(len(page.select(".dashboard-card")), 6)
        self.assertFalse(page.select('input[type="password"]'))
        with self.client.session_transaction() as session:
            token = session["admin_token"]
        sessions = self.rows("SELECT * FROM sessions")
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["token_hash"], hashlib.sha256(token.encode()).hexdigest())
        self.assertEqual(self.client.get("/admin/eventi").status_code, 200)
        self.submit("/admin/logout", token_page="/admin")
        self.assertEqual(self.rows("SELECT * FROM sessions"), [])
        with self.client.session_transaction() as session:
            self.assertNotIn("admin_token", session)
        self.assertEqual(self.client.get("/admin/eventi").status_code, 302)

    def test_password_only_login_matches_other_admin_accounts(self):
        with self.app.app_context():
            db = get_db()
            other_id = db.execute(
                "INSERT INTO users(password_hash) VALUES(?)",
                (generate_password_hash("other-password"),),
            ).lastrowid
            db.commit()
        self.submit("/admin", {"password": "other-password"})
        self.assertEqual(self.rows("SELECT user_id FROM sessions")[0]["user_id"], other_id)

    def test_password_only_login_rejects_invalid_input_and_limits_attempts(self):
        for password in ("", "x" * 4097, "wrong-1", "wrong-2", "wrong-3"):
            self.submit("/admin", {"password": password}, expected=401)
        self.submit("/admin", {"password": self.password}, expected=429)
        self.assertEqual(self.rows("SELECT * FROM sessions"), [])

    def test_html_forms_match_backend_fields_and_keep_accessible_help(self):
        from app.content import SECTIONS

        self.login()
        for section, spec in SECTIONS.items():
            with self.subTest(section=section):
                page = self.soup(self.client.get(f'/admin/{section}/new'))
                form = page.select_one('.edit-form')
                fields = {field['name'] for field in form.select('input[name], textarea[name]')
                          if field['name'] != 'csrf_token' and field.get('type') != 'file'}
                self.assertEqual(fields, set(spec['fields']) - {'published'})
                self.assertEqual({field['name'] for field in form.select('[required]')}, set(spec['required']))
                for field in form.select('[aria-describedby]'):
                    self.assertIsNotNone(form.find(id=field['aria-describedby']))
        self.assertIn('50% 0% in alto', page.select_one('#cover_position-help').get_text())

    def test_template_messages_render_validation_details_and_not_codes(self):
        response = self.submit('/admin', {'password': 'incorrect'}, expected=401)
        self.assertIn('Password non corretta.', response.get_data(as_text=True))
        self.login()
        data = self.content_data('eventi')
        data['title'] = 'x' * 2001
        response = self.submit('/admin/eventi/new', data, expected=422)
        message = self.soup(response).select_one('.notice.error').get_text(' ', strip=True)
        self.assertIn('Titolo', message)
        self.assertIn('2000', message)
        self.assertNotIn('field_too_long', message)

    def test_expired_server_session_requires_fresh_login(self):
        self.login()
        with self.app.app_context():
            get_db().execute("UPDATE sessions SET expires_at=0")
            get_db().commit()
        self.assertEqual(self.client.get("/admin/eventi").status_code, 302)
        with self.client.session_transaction() as session:
            self.assertNotIn("admin_token", session)

    def test_every_write_requires_csrf_even_when_logged_in(self):
        self.assertEqual(self.client.post("/admin", data={"password": self.password}).status_code, 400)
        self.login()
        photo = self.rows("SELECT * FROM photos LIMIT 1")[0]
        gallery = f"/admin/foto/{photo['album_id']}/photos"
        paths = ["/admin/logout", gallery, f"{gallery}/{photo['id']}/edit", f"{gallery}/{photo['id']}/delete", f"/admin/foto/{photo['album_id']}/sync"]
        for section in TABLES:
            paths.extend((f"/admin/{section}/new", f"/admin/{section}/1/edit", f"/admin/{section}/1/delete"))
        before = {table: self.rows(f"SELECT * FROM {table}") for table in (*TABLES.values(), "photos", "sessions")}
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path, data={}).status_code, 400)
        for table, original in before.items():
            self.assertEqual(self.rows(f"SELECT * FROM {table}"), original)

    def test_all_three_sections_create_edit_publish_and_delete_through_forms(self):
        self.login()
        for section, table in TABLES.items():
            with self.subTest(section=section):
                record, data = self.create_content(section)
                title_key = "title"
                path = f"/admin/{section}/{record['id']}"
                public = PUBLIC_PAGES[section]
                self.assertIn(data[title_key], self.client.get(public).get_data(as_text=True))
                self.assertIn(data[title_key], self.client.get(f"/admin/{section}").get_data(as_text=True))
                original_title = data[title_key]
                data[title_key] += " aggiornato"
                response = self.submit(path + "/edit", data)
                self.assertEqual(response.location, path + '/edit')
                saved_page = self.soup(self.client.get(response.location))
                self.assertEqual(saved_page.select_one('[name="title"]')['value'], data[title_key])
                self.assertIn('Modifiche salvate.', saved_page.select_one('.notice.success').get_text())
                self.assertEqual(self.row(table, record["id"])[title_key], data[title_key])
                self.assertIn(data[title_key], self.client.get(public).get_data(as_text=True))
                data.pop("published")
                self.submit(path + '/publication', {'hidden': '1'}, token_page=f'/admin/{section}')
                self.submit(path + "/edit", data)
                self.assertEqual(self.row(table, record["id"])["published"], 0)
                self.assertNotIn(original_title, self.client.get(public).get_data(as_text=True))
                if section in ("notizie", "foto"):
                    detail = f"/{'notizie' if section == 'notizie' else 'foto'}/{data['slug']}"
                    self.assertEqual(self.client.get(detail).status_code, 404)
                data["published"] = "1"
                self.submit(path + '/publication', token_page=f'/admin/{section}')
                self.submit(path + "/edit", data)
                self.assertIn(data[title_key], self.client.get(public).get_data(as_text=True))
                if section in ("notizie", "foto"):
                    self.assertEqual(self.client.get(detail).status_code, 200)
                self.assertEqual(self.client.get(path + "/delete").status_code, 200)
                self.assertIsNotNone(self.row(table, record["id"]))
                self.submit(path + "/delete")
                self.assertIsNone(self.row(table, record["id"]))
                self.assertNotIn(original_title, self.client.get(public).get_data(as_text=True))
                self.assertEqual(self.client.get(path + "/edit").status_code, 404)

    def test_normal_rich_article_and_external_source_are_displayed(self):
        self.login()
        article, data = self.create_content("notizie")
        page = self.soup(self.client.get(f"/notizie/{article['slug']}"))
        self.assertEqual(page.select_one("article.prose h2").get_text(), "Il programma")
        self.assertEqual(page.select_one("article.prose strong").get_text(), "per tutti")
        data.update(external_url="https://example.com/notizia", body="")
        self.submit(f"/admin/notizie/{article['id']}/edit", data)
        for path in ("/", "/notizie"):
            self.assertTrue(self.soup(self.client.get(path)).select('a[href="https://example.com/notizia"]'))

    def test_invalid_dates_duplicate_slugs_and_incomplete_forms_leave_records_unchanged(self):
        self.login()
        for section in ("eventi", "notizie", "foto"):
            with self.subTest(section=section):
                record, data = self.create_content(section)
                before = self.rows(f"SELECT * FROM {TABLES[section]}")
                self.submit(f"/admin/{section}/new", data, expected=422)
                self.submit(f"/admin/{section}/{record['id']}/edit", dict(data, date="2040-02-31"), expected=422)
                self.assertEqual(self.rows(f"SELECT * FROM {TABLES[section]}"), before)
                response = self.submit(f"/admin/{section}/new", dict(data, title="", slug="missing-title"), expected=422)
                self.assertTrue(self.soup(response).select('[role="alert"]'))
                self.assertEqual(self.rows(f"SELECT * FROM {TABLES[section]}"), before)

    def test_album_dates_accept_month_days_and_multiple_dates_and_render_them(self):
        self.login()
        cases = [
            ('2040-06', '2040-06', 'Giugno 2040'),
            ('2040-02-29', '2040-02-29', '29 febbraio 2040'),
            ('2040-06-03, 2040-06-01,2040-06-03', '2040-06-01, 2040-06-03', '1 - 3 giugno 2040'),
            ('2041-01-02, 2040-12-31', '2040-12-31, 2041-01-02', '31 dicembre 2040 - 2 gennaio 2041'),
            ('2040-08-02, 2040-07', '2040-07, 2040-08-02', 'Luglio - 2 agosto 2040'),
        ]
        for index, (submitted, stored, label) in enumerate(cases):
            with self.subTest(date=submitted):
                data = dict(self.content_data('foto', str(index)), date=submitted)
                self.submit('/admin/foto/new', data)
                album = self.rows('SELECT * FROM albums WHERE slug=?', (data['slug'],))[0]
                self.assertEqual(album['date'], stored)
                public = self.soup(self.client.get(f"/foto/{album['slug']}"))
                self.assertEqual(public.select_one('.gallery-hero .eyebrow').get_text(), label)
                self.assertIn(label, public.title.get_text())
                archive = self.soup(self.client.get('/foto'))
                card = archive.select_one(f'a[href="/foto/{album["slug"]}"]')
                self.assertEqual(card.select_one('.eyebrow').get_text(), label)
                self.assertEqual(card.find_parent('section')['id'], 'foto-' + stored[:4])
                edit = self.soup(self.client.get(f'/admin/foto/{album["id"]}/edit'))
                self.assertEqual(edit.select_one('[name="date"]')['value'], stored)
        restarted = create_app(self.config).test_client()
        self.assertIn('Luglio - 2 agosto 2040', restarted.get(f"/foto/{album['slug']}").get_data(as_text=True))

    def test_invalid_album_date_lists_leave_saved_album_unchanged(self):
        self.login()
        album, data = self.create_content('foto')
        for invalid in ('2040-06-01,', ',2040-06', '2040-06,,2040-07',
                        '2041-02-29', '2040-06-01, 2040-13-01', '2040-06-01;2040-06-02',
                        '2040-06-01, testo', '2040-06-01/2040-06-03'):
            with self.subTest(date=invalid):
                response = self.submit(f'/admin/foto/{album["id"]}/edit', dict(data, date=invalid), expected=422)
                page = self.soup(response)
                self.assertIn('separate da virgole', page.select_one('.notice.error').get_text())
                self.assertEqual(page.select_one('[name="date"]')['value'], invalid)
                self.assertEqual(self.row('albums', album['id']), album)
        self.submit(f'/admin/foto/{album["id"]}/edit', dict(data, date='2040-06-02,2040-06-01'))
        self.assertEqual(self.row('albums', album['id'])['date'], '2040-06-01, 2040-06-02')
        for section in ('eventi', 'notizie'):
            self.submit(f'/admin/{section}/new', dict(self.content_data(section), date='2040-06-01, 2040-06-02'), expected=422)

    def test_album_archive_sorts_by_first_date_not_list_length(self):
        self.login()
        for suffix, dates in (('single', '2040-06-01'), ('multiple', '2040-06-01, 2041-01-01'), ('later', '2040-07')):
            self.submit('/admin/foto/new', dict(self.content_data('foto', suffix), date=dates))
        archive = self.soup(self.client.get('/foto'))
        links = [card['href'] for card in archive.select('#foto-2040 .album-link')]
        self.assertEqual(links, ['/foto/prova-foto-later', '/foto/prova-foto-single', '/foto/prova-foto-multiple'])

    def test_single_album_photo_can_be_hidden_and_restored_without_deletion(self):
        self.login()
        album, _ = self.create_content('foto', 'visibility')
        gallery = f'/admin/foto/{album["id"]}/photos'
        public = f'/foto/{album["slug"]}'
        self.submit(gallery, {'src': '/assets/concert.jpg', 'alt': 'Foto da nascondere'})
        self.submit(gallery, {'src': '/assets/varenna.jpg', 'alt': 'Foto visibile'})
        photo = self.rows('SELECT * FROM photos WHERE album_id=? ORDER BY id', (album['id'],))[0]
        edit = f'{gallery}/{photo["id"]}/edit'
        values = dict(src=photo['src'], alt=photo['alt'], sort_order='0', hidden='1')
        response = self.submit(edit, values)
        self.assertEqual(response.location, edit)
        self.assertEqual(self.row('photos', photo['id'])['published'], 0)
        self.assertEqual(len(self.rows('SELECT * FROM photos WHERE album_id=?', (album['id'],))), 2)
        self.assertEqual([img['alt'] for img in self.soup(self.client.get(public)).select('.gallery-photo img')], ['Foto visibile'])
        self.assertTrue(self.soup(self.client.get(edit)).select_one('[name="hidden"]').has_attr('checked'))
        self.assertNotIn('Nascosta', self.client.get(gallery).get_data(as_text=True))
        restarted = create_app(self.config).test_client()
        self.assertEqual(len(self.soup(restarted.get(public)).select('.gallery-photo')), 1)
        values.pop('hidden')
        self.submit(edit, values)
        self.assertEqual(self.row('photos', photo['id'])['published'], 1)
        self.assertEqual(len(self.soup(self.client.get(public)).select('.gallery-photo')), 2)
        self.assertFalse(self.soup(self.client.get(edit)).select_one('[name="hidden"]').has_attr('checked'))

    def test_all_image_fields_accept_external_links(self):
        self.login()
        for index, (url, expected) in enumerate((
            ('https://example.com/photo.jpg?size=large', 'https://example.com/photo.jpg?size=large'),
            ('https://drive.google.com/file/d/example-photo/view', 'https://lh3.googleusercontent.com/d/example-photo=s1600'),
        )):
            for section, table, field in (('notizie', 'news', 'image'), ('foto', 'albums', 'cover')):
                with self.subTest(section=section, url=url):
                    data = self.content_data(section, f'link-{index}')
                    data[field] = url
                    self.submit(f'/admin/{section}/new', data)
                    record = self.rows(f'SELECT * FROM {table} WHERE slug=?', (data['slug'],))[0]
                    self.assertEqual(record[field], expected)
                    page = self.soup(self.client.get(PUBLIC_PAGES[section]))
                    self.assertIsNotNone(page.find('img', src=expected))
            self.submit('/admin/foto/1/photos', {'src': url, 'alt': 'Foto via link', 'sort_order': '3'})
            self.assertTrue(self.rows('SELECT * FROM photos WHERE src=?', (expected,)))
            self.submit('/admin/insegnanti/new', {
                'name': f'Insegnante link {index}', 'instrument': 'Flauto',
                'image': url, 'image_alt': 'Ritratto', 'sort_order': '0', 'published': '1',
            })
            self.assertTrue(self.rows('SELECT * FROM teachers WHERE image=?', (expected,)))
            self.assertIsNotNone(self.soup(self.client.get('/scuola-allievi')).find('img', src=expected))

    def test_inline_photo_visibility_saves_only_visibility_and_stays_in_album(self):
        self.login()
        photo = self.rows('SELECT * FROM photos ORDER BY id')[0]
        gallery = f'/admin/foto/{photo["album_id"]}/photos'
        endpoint = f'{gallery}/{photo["id"]}/visibility'
        response = self.client.post(endpoint, data={'csrf_token': self.csrf(gallery), 'hidden': '1', 'alt': 'Must not overwrite'}, headers={'Accept': 'application/json'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {'published': False})
        self.assertEqual(self.row('photos', photo['id']), dict(photo, published=0))
        card = self.soup(self.client.get(gallery)).select_one(f'#photo-{photo["id"]}')
        self.assertIn('is-hidden', card['class'])
        self.assertTrue(card.select_one('input[name="hidden"]').has_attr('checked'))
        self.assertIsNotNone(card.select_one('.row-actions input[name="hidden"]'))
        self.assertEqual(len(card.select('.row-actions a')), 2)
        for value in ('invalid', ['1', '0']):
            response = self.client.post(endpoint, data={'csrf_token': self.csrf(gallery), 'hidden': value})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(self.row('photos', photo['id'])['published'], 0)
        response = self.submit(endpoint, token_page=gallery)
        self.assertEqual(response.location, gallery + f'#photo-{photo["id"]}')
        self.assertEqual(self.row('photos', photo['id']), photo)

    def test_inline_photo_visibility_requires_authentication_csrf_and_correct_album(self):
        photo = self.rows('SELECT * FROM photos ORDER BY id')[0]
        gallery = f'/admin/foto/{photo["album_id"]}/photos'
        endpoint = f'{gallery}/{photo["id"]}/visibility'
        response = self.submit(endpoint, {'hidden': '1'}, token_page='/admin')
        self.assertEqual(response.location.rstrip('/'), '/admin')
        self.login()
        self.assertEqual(self.client.post(endpoint, data={'hidden': '1'}).status_code, 400)
        other_album = self.rows('SELECT id FROM albums WHERE id!=?', (photo['album_id'],))[0]['id']
        response = self.client.post(f'/admin/foto/{other_album}/photos/{photo["id"]}/visibility', data={'csrf_token': self.csrf(gallery), 'hidden': '1'})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.row('photos', photo['id']), photo)

    def test_new_photo_can_start_hidden_and_empty_gallery_renders(self):
        self.login()
        album, _ = self.create_content('foto', 'hidden')
        gallery = f'/admin/foto/{album["id"]}/photos'
        self.submit(gallery, {'src': '/assets/concert.jpg', 'hidden': '1'})
        self.assertEqual(self.rows('SELECT published FROM photos WHERE album_id=?', (album['id'],)), [{'published': 0}])
        page = self.soup(self.client.get(f'/foto/{album["slug"]}'))
        self.assertFalse(page.select('.gallery-photo'))
        self.assertTrue(page.select('.gallery-empty'))

    def test_gallery_upload_edit_order_delete_and_album_cascade(self):
        self.login()
        album, data = self.create_content("foto")
        gallery = f"/admin/foto/{album['id']}/photos"
        image = io.BytesIO()
        Image.new("RGB", (16, 12), color="red").save(image, format="JPEG")
        image.seek(0)
        self.submit(gallery, {"image_upload": (image, "concerto.jpg"), "alt": "Foto caricata", "sort_order": "10"})
        photo = self.rows("SELECT * FROM photos WHERE album_id=?", (album["id"],))[0]
        self.assertRegex(photo["src"], r"^/uploads/[0-9a-f]{40}\.webp$")
        response = self.client.get(photo["src"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/webp")
        with Image.open(io.BytesIO(response.data)) as uploaded:
            self.assertEqual(uploaded.format, "WEBP")
            self.assertEqual(uploaded.size, (16, 12))
        response.close()
        self.submit(gallery, {"src": "/assets/concert.jpg", "alt": "Prima foto", "sort_order": "-1"})
        public = f"/foto/{album['slug']}"
        page = self.soup(self.client.get(public))
        self.assertEqual([p.img["alt"] for p in page.select(".gallery-photo")], ["Foto caricata", "Prima foto"])
        response = self.submit(f"{gallery}/{photo['id']}/edit", {"src": photo["src"], "alt": "Descrizione aggiornata", "sort_order": "-2"})
        self.assertEqual(response.location, f"{gallery}/{photo['id']}/edit")
        page = self.soup(self.client.get(public))
        self.assertEqual(page.select_one(".gallery-photo img")["alt"], "Descrizione aggiornata")
        self.assertEqual(page.select_one(".gallery-photo")["data-original"], photo["src"])
        self.submit(f"{gallery}/{photo['id']}/delete")
        self.assertIsNone(self.row("photos", photo["id"]))
        self.assertEqual(len(self.soup(self.client.get(public)).select(".gallery-photo")), 1)
        self.submit(f"/admin/foto/{album['id']}/delete")
        self.assertEqual(self.rows("SELECT * FROM photos WHERE album_id=?", (album["id"],)), [])
        self.assertEqual(self.client.get(public).status_code, 404)
        with self.app.app_context():
            self.assertEqual(get_db().execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_invalid_image_and_duplicate_photo_leave_gallery_unchanged(self):
        self.login()
        album, data = self.create_content("foto")
        gallery = f"/admin/foto/{album['id']}/photos"
        self.submit(gallery, {"image_upload": (io.BytesIO(b"This is a plain text document."), "notes.txt")}, expected=422)
        self.assertEqual(self.rows("SELECT * FROM photos WHERE album_id=?", (album["id"],)), [])
        self.assertEqual(list((self.instance / "uploads").iterdir()), [])
        self.submit(gallery, {"src": "/assets/concert.jpg", "alt": "Concerto", "sort_order": "0"})
        before = self.rows("SELECT * FROM photos WHERE album_id=?", (album["id"],))
        self.submit(gallery, {"src": "/assets/concert.jpg", "alt": "Seconda copia"}, expected=422)
        self.assertEqual(self.rows("SELECT * FROM photos WHERE album_id=?", (album["id"],)), before)
        self.submit(f"{gallery}/{before[0]['id']}/edit", {"src": "http://example.com/photo.jpg"}, expected=422)
        self.assertEqual(self.rows("SELECT * FROM photos WHERE album_id=?", (album["id"],)), before)
        article, values = self.create_content("notizie")
        values["image_upload"] = (io.BytesIO(b"plain document"), "document.txt")
        self.submit(f"/admin/notizie/{article['id']}/edit", values, expected=422)
        self.assertEqual(self.row("news", article["id"]), article)
        image = io.BytesIO()
        Image.new("RGB", (16, 12), color="blue").save(image, format="JPEG")
        image.seek(0)
        values["image_upload"] = (image, "notizia.jpg")
        self.submit(f"/admin/notizie/{article['id']}/edit", values)
        saved = self.row("news", article["id"])
        self.assertRegex(saved["image"], r"^/uploads/[0-9a-f]{40}\.webp$")
        public = self.soup(self.client.get(f"/notizie/{article['slug']}"))
        self.assertEqual(public.select_one("img.page-image")["src"], saved["image"])

    def test_photo_position_is_automatic_and_edit_does_not_reorder(self):
        self.login()
        gallery = '/admin/foto/1/photos'
        before = self.rows('SELECT * FROM photos WHERE album_id=1 ORDER BY sort_order,id')
        self.assertIsNone(self.soup(self.client.get(gallery)).select_one('[name="sort_order"]'))
        self.submit(gallery, {'src': 'https://example.com/new.jpg', 'sort_order': '-999'})
        after = self.rows('SELECT * FROM photos WHERE album_id=1 ORDER BY sort_order,id')
        self.assertEqual(after[:-1], before)
        photo = after[-1]
        path = f'{gallery}/{photo["id"]}/edit'
        self.assertIsNone(self.soup(self.client.get(path)).select_one('[name="sort_order"]'))
        self.submit(path, {'src': photo['src'], 'alt': 'Aggiornata', 'sort_order': '-1000'})
        self.assertEqual(self.row('photos', photo['id'])['sort_order'], photo['sort_order'])

    def test_album_photo_manager_link_is_in_heading_instead_of_separate_panel(self):
        self.login()
        page = self.soup(self.client.get('/admin/foto/1/edit'))
        link = page.select_one('.page-heading.with-actions a.button')
        self.assertEqual(link['href'], '/admin/foto/1/photos')
        self.assertIn('Gestisci le foto', link.get_text())
        self.assertIsNone(page.select_one('.next-step'))
        for path in ('/admin/foto/new', '/admin/eventi/1/edit', '/admin/notizie/1/edit'):
            self.assertIsNone(self.soup(self.client.get(path)).select_one('.page-heading a.button'))

    def test_publication_checkboxes_live_on_lists_and_save_only_publication(self):
        self.login()
        for section, table in (*TABLES.items(), ('musica-insieme', 'home_features'), ('insegnanti', 'teachers')):
            listing = f'/admin/{section}'
            endpoint = f'{listing}/1/publication'
            original = self.row(table, 1)
            page = self.soup(self.client.get(listing))
            self.assertFalse(page.select_one('#entry-1 input[name="hidden"]').has_attr('checked'))
            control = page.select_one('#entry-1 .row-actions form[data-publication]')
            self.assertIsNotNone(control)
            self.assertIn('Modifica', control.find_next_sibling('a').get_text())
            for path in (f'{listing}/1/edit', f'{listing}/new'):
                self.assertIsNone(self.soup(self.client.get(path)).select_one('input[name="published"]'))
            response = self.client.post(endpoint, data={'csrf_token': self.csrf(listing), 'hidden': '1', 'title': 'Ignored'},
                                        headers={'Accept': 'application/json'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json(), {'published': False})
            self.assertEqual(self.row(table, 1), dict(original, published=0))
            self.assertIn('is-unpublished', self.soup(self.client.get(listing)).select_one('#entry-1')['class'])
            self.assertTrue(self.soup(self.client.get(listing)).select_one('#entry-1 input[name="hidden"]').has_attr('checked'))
            response = self.submit(endpoint, token_page=listing)
            self.assertEqual(response.location, listing + '#entry-1')
            self.assertEqual(self.row(table, 1), original)
            self.assertNotIn('is-unpublished', self.soup(self.client.get(listing)).select_one('#entry-1')['class'])
            self.assertEqual(self.client.post(endpoint, data={'hidden': '1'}).status_code, 400)
            self.submit(endpoint, {'hidden': 'invalid'}, token_page=listing, expected=400)
            self.submit(endpoint, {'hidden': ['1', '1']}, token_page=listing, expected=400)
            self.submit(f'{listing}/999999/publication', token_page=listing, expected=404)
        self.submit('/admin/unknown/1/publication', token_page='/admin', expected=404)

    def test_publication_requires_login(self):
        token = self.csrf()
        for section, table in (*TABLES.items(), ('musica-insieme', 'home_features'), ('insegnanti', 'teachers')):
            before = self.row(table, 1)
            response = self.client.post(f'/admin/{section}/1/publication', data={'csrf_token': token})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(self.row(table, 1), before)

    def test_saved_changes_and_deletions_survive_app_restart(self):
        self.login()
        records = {}
        for section in TABLES:
            record, data = self.create_content(section, "persistente")
            records[section] = record
        self.submit("/admin/eventi/1/delete")
        before = {table: self.rows(f"SELECT * FROM {table}") for table in (*TABLES.values(), "photos", "users")}
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        for table, original in before.items():
            self.assertEqual(self.rows(f"SELECT * FROM {table}"), original)
        self.assertIsNone(self.row("events", 1))
        self.login()
        for section, record in records.items():
            title = record["title"]
            self.assertIn(title, self.client.get(PUBLIC_PAGES[section]).get_data(as_text=True))
            self.assertEqual(self.client.get(f"/admin/{section}/{record['id']}/edit").status_code, 200)

    def test_drive_sync_preserves_uploads_and_existing_gallery_on_unavailable_source(self):
        self.login()
        album, data = self.create_content("foto")
        data["folder"] = "https://drive.google.com/drive/folders/example-folder"
        self.submit(f"/admin/foto/{album['id']}/edit", data)
        gallery = f"/admin/foto/{album['id']}/photos"
        self.submit(gallery, {"src": "/assets/concert.jpg", "alt": "Foto locale"})
        result = [{"id": "photo-one", "resourceKey": "key-one"}]
        with patch("app.content.read_drive_folder", return_value=result) as sync:
            self.submit(f"/admin/foto/{album['id']}/sync", token_page=gallery)
            sync.assert_called_once()
        self.assertIn('Sincronizzazione completata: 1 foto importate o aggiornate.', self.client.get(gallery).get_data(as_text=True))
        before = self.rows("SELECT * FROM photos WHERE album_id=? ORDER BY id", (album["id"],))
        self.assertEqual(len(before), 2)
        self.assertEqual({photo["source"] for photo in before}, {"drive", "link"})
        self.assertTrue(any("resourcekey=key-one" in photo["original"] for photo in before))
        with patch("app.content.read_drive_folder", side_effect=DriveError("Tempo di sincronizzazione scaduto.")):
            with self.assertLogs(self.app.logger, level="WARNING"):
                self.submit(f"/admin/foto/{album['id']}/sync", token_page=gallery)
        self.assertEqual(self.rows("SELECT * FROM photos WHERE album_id=? ORDER BY id", (album["id"],)), before)
        self.assertEqual(len(self.soup(self.client.get(f"/foto/{album['slug']}")).select(".gallery-photo")), 2)

    def test_empty_sections_still_render_public_pages(self):
        with self.app.app_context():
            db = get_db()
            for table in TABLES.values():
                db.execute(f"DELETE FROM {table}")
            db.commit()
        for path in ("/", "/scuola-allievi", *PUBLIC_PAGES.values()):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(self.soup(response).select_one("main").get_text(strip=True))
        self.assert_original_teachers(self.soup(self.client.get("/scuola-allievi")))


if __name__ == "__main__":
    unittest.main()
