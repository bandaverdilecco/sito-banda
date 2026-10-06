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
    "eventi": "/prossimi-eventi.html",
    "notizie": "/blog.html", "foto": "/foto.html",
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
        self.submit(f"/admin/{section}/new", data)
        table = TABLES[section]
        record = self.rows(f"SELECT * FROM {table} WHERE slug=?", (data["slug"],))[0]
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
        self.assertEqual(len(teachers[-1].select("h3.teacher-names br")), 1)

    def test_public_pages_preserve_content_navigation_and_hide_admin(self):
        expected = {
            "/": "Filarmonica", "/index.html": "Filarmonica",
            "/la-filarmonica.html": "Una storia iniziata nel 1809",
            "/scuola-allievi.html": "Emanuela Milani",
            "/prossimi-eventi.html": "Concerto di prova",
            "/blog.html": "Notizia di prova",
            "/foto.html": "Fotografie", "/sostienici.html": "IT53Z0306909606100000150858",
            "/contatti.html": "bandaverdilecco@libero.it",
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
                for element in page.select("a[href], img[src], script[src], link[href]"):
                    value = element.get("href", element.get("src"))
                    self.assertTrue(value.startswith(("/", "#", "https:", "mailto:", "tel:")), value)
        self.assertEqual(self.client.get("/pagina-inesistente").status_code, 404)

    def test_existing_school_teachers_are_preserved_and_can_be_managed(self):
        self.assert_original_teachers(self.soup(self.client.get("/scuola-allievi.html")))
        self.assertEqual(len(self.rows("SELECT * FROM teachers")), 6)
        dashboard = self.soup(self.login())
        self.assertTrue(dashboard.select('a[href="/admin/insegnanti"]'))
        for suffix in ("", "/new", "/1/edit", "/1/delete"):
            with self.subTest(suffix=suffix):
                self.assertEqual(self.client.get("/admin/insegnanti" + suffix).status_code, 200)
        self.assert_original_teachers(self.soup(self.client.get("/scuola-allievi.html")))

    def test_news_and_album_urls_and_galleries_render_database_content(self):
        articles = self.rows("SELECT * FROM news ORDER BY id")
        current_news = self.soup(self.client.get("/blog.html"))
        current_links = {link["href"] for link in current_news.select(".news-list a")}
        self.assertEqual(len(articles), 2)
        self.assertEqual(sum(bool(article["external_url"]) for article in articles), 1)
        for article in articles:
            expected = article["external_url"] or f"/blog/{article['slug']}.html"
            self.assertIn(expected, current_links)
            if not article["external_url"]:
                response = self.client.get(expected)
                self.assertEqual(response.status_code, 200, expected)
                page = self.soup(response)
                self.assertEqual(page.h1.get_text(), article["title"])
                self.assertEqual(len(page.select("article.prose img.page-image")), 1)
                self.assertTrue(page.select('.main-nav a[href="/blog.html"][aria-current="true"]'))
        albums = self.rows("SELECT * FROM albums ORDER BY id")
        total_photos = 0
        for album in albums:
            response = self.client.get(f"/foto/{album['slug']}.html")
            self.assertEqual(response.status_code, 200, album["slug"])
            page = self.soup(response)
            self.assertEqual(page.h1.get_text(), album["title"])
            self.assertTrue(page.select('script[src="/gallery.js"]'))
            self.assertTrue(page.select('.main-nav a[href="/foto.html"][aria-current="true"]'))
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
        self.submit(f"/admin/notizie/{article['id']}/edit", data)
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
                self.assertEqual(fields, set(spec['fields']))
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
                self.submit(path + "/edit", data)
                self.assertEqual(self.row(table, record["id"])[title_key], data[title_key])
                self.assertIn(data[title_key], self.client.get(public).get_data(as_text=True))
                data.pop("published")
                self.submit(path + "/edit", data)
                self.assertEqual(self.row(table, record["id"])["published"], 0)
                self.assertNotIn(original_title, self.client.get(public).get_data(as_text=True))
                if section in ("notizie", "foto"):
                    detail = f"/{'blog' if section == 'notizie' else 'foto'}/{data['slug']}.html"
                    self.assertEqual(self.client.get(detail).status_code, 404)
                data["published"] = "1"
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
        page = self.soup(self.client.get(f"/blog/{article['slug']}.html"))
        self.assertEqual(page.select_one("article.prose h2").get_text(), "Il programma")
        self.assertEqual(page.select_one("article.prose strong").get_text(), "per tutti")
        data.update(external_url="https://example.com/notizia", body="")
        self.submit(f"/admin/notizie/{article['id']}/edit", data)
        for path in ("/", "/blog.html"):
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
        public = f"/foto/{album['slug']}.html"
        page = self.soup(self.client.get(public))
        self.assertEqual([p.img["alt"] for p in page.select(".gallery-photo")], ["Prima foto", "Foto caricata"])
        self.submit(f"{gallery}/{photo['id']}/edit", {"src": photo["src"], "alt": "Descrizione aggiornata", "sort_order": "-2"})
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
        self.submit(f"{gallery}/{before[0]['id']}/edit", {"src": "/assets/concert.jpg", "sort_order": "first"}, expected=422)
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
        public = self.soup(self.client.get(f"/blog/{article['slug']}.html"))
        self.assertEqual(public.select_one("img.page-image")["src"], saved["image"])

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
        self.assertEqual(len(self.soup(self.client.get(f"/foto/{album['slug']}.html")).select(".gallery-photo")), 2)

    def test_empty_sections_still_render_public_pages(self):
        with self.app.app_context():
            db = get_db()
            for table in TABLES.values():
                db.execute(f"DELETE FROM {table}")
            db.commit()
        for path in ("/", "/scuola-allievi.html", *PUBLIC_PAGES.values()):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(self.soup(response).select_one("main").get_text(strip=True))
        self.assert_original_teachers(self.soup(self.client.get("/scuola-allievi.html")))


if __name__ == "__main__":
    unittest.main()
