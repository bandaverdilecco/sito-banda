"""Editable home/school sections and explicit homepage content selections."""

import io
from pathlib import Path
import tempfile
import unittest

from bs4 import BeautifulSoup
from PIL import Image
from werkzeug.security import generate_password_hash

from app import create_app
from app.db import get_db


class EditorialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = "editorial-test"
        cls.password_hash = generate_password_hash(cls.password)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="filarmonica-editorial-")
        self.addCleanup(temporary.cleanup)
        self.instance = Path(temporary.name)
        self.config = dict(TESTING=True, INSTANCE_PATH=str(self.instance), SECRET_KEY="test")
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        with self.app.app_context():
            db = get_db()
            db.execute("INSERT INTO users(password_hash) VALUES(?)", (self.password_hash,))
            db.executemany("INSERT INTO events(slug,title,date) VALUES(?,?,?)", [
                (f"evento-{number}", f"Appuntamento {number}", f"2039-06-{number:02}")
                for number in range(1, 7)
            ])
            db.execute("INSERT INTO events(slug,title,date) VALUES('passato','Concerto passato','2000-01-01')")
            db.execute("INSERT INTO events(slug,title,date,published) VALUES('bozza','Evento in bozza','2040-01-01',0)")
            db.executescript("""
                INSERT INTO news(slug,title,date,summary,body,published) VALUES
                ('recente','La notizia recente','2039-06-02','Notizia recente.','<p>Recente.</p>',1),
                ('archivio','La notizia scelta','2000-01-01','Dal nostro archivio.','<p>Archivio.</p>',1),
                ('bozza','La notizia in bozza','2040-01-01','Bozza.','<p>Bozza.</p>',0);
            """)
            db.commit()

    @staticmethod
    def soup(response):
        return BeautifulSoup(response.get_data(as_text=True), "html.parser")

    def rows(self, sql, parameters=()):
        with self.app.app_context():
            return [dict(row) for row in get_db().execute(sql, parameters).fetchall()]

    def csrf(self, path="/admin"):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:500])
        return self.soup(response).select_one('input[name="csrf_token"]')["value"]

    def submit(self, path, data=None, *, expected=302):
        response = self.client.post(path, data={**(data or {}), "csrf_token": self.csrf(path)})
        self.assertEqual(response.status_code, expected, response.get_data(as_text=True)[:1500])
        return response

    def login(self):
        self.submit("/admin", {"password": self.password})

    def homepage_titles(self):
        page = self.soup(self.client.get("/"))
        return ([row.h3.get_text() for row in page.select(".event-row")],
                [card.h3.get_text() for card in page.select(".news-card")])

    @staticmethod
    def feature_data():
        return dict(eyebrow="Partecipa", title="Musica per tutti", description="Una nuova iniziativa.",
                    url="/contatti.html", link_label="Scrivici", sort_order="-1", published="1")

    @staticmethod
    def teacher_data():
        return dict(name="Maestra di prova", instrument="Violino", image="/assets/emanuela-milani.jpg",
                    image_alt="La maestra", sort_order="-1", published="1")

    def test_new_management_routes_require_login_and_csrf(self):
        paths = ["/admin/home", "/admin/musica-insieme", "/admin/musica-insieme/new",
                 "/admin/musica-insieme/1/edit", "/admin/musica-insieme/1/delete",
                 "/admin/insegnanti/new", "/admin/insegnanti/1/edit", "/admin/insegnanti/1/delete"]
        tables = ("home_intro", "home_features", "teachers", "home_selection", "home_events")
        before = {table: self.rows(f"SELECT * FROM {table}") for table in tables}
        token = self.csrf()
        for path in [*paths, "/admin/insegnanti"]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.location.rstrip("/"), "/admin")
        for path in paths:
            with self.subTest(path=path):
                response = self.client.post(path, data={"csrf_token": token, "title": "Non salvare"})
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.location.rstrip("/"), "/admin")
        self.login()
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path, data={}).status_code, 400)
        for table, original in before.items():
            self.assertEqual(self.rows(f"SELECT * FROM {table}"), original)

    def test_manual_home_selection_has_no_three_event_limit_and_can_choose_older_news(self):
        self.login()
        self.submit("/admin/home", {"event_ids": ["6", "2", "4", "1", "5"], "news_id": "2"})
        self.assertEqual(self.homepage_titles(),
                         (["Appuntamento 1", "Appuntamento 2", "Appuntamento 4", "Appuntamento 5", "Appuntamento 6"],
                          ["La notizia scelta"]))
        page = self.soup(self.client.get("/admin/home"))
        self.assertEqual({field["value"] for field in page.select('input[name="event_ids"][checked]')},
                         {"1", "2", "4", "5", "6"})
        self.assertEqual([field["value"] for field in page.select('input[name="news_id"][checked]')], ["2"])

    def test_manual_home_selection_accepts_past_events_and_explicitly_empty_sections(self):
        self.login()
        self.submit("/admin/home", {"event_ids": ["7"], "news_id": "2"})
        self.assertEqual(self.homepage_titles(), (["Concerto passato"], ["La notizia scelta"]))
        self.submit("/admin/home", {"news_id": ""})
        self.assertEqual(self.homepage_titles(), ([], []))
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.assertEqual(self.homepage_titles(), ([], []))

    def test_unpublished_or_deleted_home_selections_do_not_trigger_automatic_replacement(self):
        self.login()
        self.submit("/admin/home", {"event_ids": ["2", "3"], "news_id": "2"})
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE events SET published=0 WHERE id=2")
            db.execute("DELETE FROM events WHERE id=3")
            db.execute("UPDATE news SET published=0 WHERE id=2")
            db.commit()
        self.assertEqual(self.homepage_titles(), ([], []))
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE events SET published=1 WHERE id=2")
            db.execute("UPDATE news SET published=1 WHERE id=2")
            db.commit()
        self.assertEqual(self.homepage_titles(), (["Appuntamento 2"], ["La notizia scelta"]))
        with self.app.app_context():
            db = get_db()
            db.execute("DELETE FROM events WHERE id=2")
            db.execute("DELETE FROM news WHERE id=2")
            db.commit()
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(self.homepage_titles(), ([], []))

    def test_home_selection_validation_is_atomic_and_rejects_multiple_news(self):
        self.login()
        self.submit("/admin/home", {"event_ids": ["1"], "news_id": "2"})
        before = {table: self.rows(f"SELECT * FROM {table}") for table in ("home_selection", "home_events")}
        invalid = [
            {"event_ids": ["1", "99999"], "news_id": "1"},
            {"event_ids": ["not-a-number"], "news_id": "1"},
            {"event_ids": ["8"], "news_id": "1"},
            {"event_ids": ["2"], "news_id": "99999"},
            {"event_ids": ["2"], "news_id": "not-a-number"},
            {"event_ids": ["2"], "news_id": "3"},
            {"event_ids": ["2"], "news_id": ["1", "2"]},
        ]
        for values in invalid:
            with self.subTest(values=values):
                response = self.submit("/admin/home", values, expected=422)
                self.assertTrue(self.soup(response).select('[role="alert"]'))
                for table, original in before.items():
                    self.assertEqual(self.rows(f"SELECT * FROM {table}"), original)
                self.assertEqual(self.homepage_titles(), (["Appuntamento 1"], ["La notizia scelta"]))

    def test_existing_home_section_is_preserved_and_heading_is_editable(self):
        page = self.soup(self.client.get("/"))
        self.assertEqual([card.h3.get_text() for card in page.select(".feature-card")],
                         ["Una storia, una città", "La musica comincia qui", "Sostieni la musica"])
        self.assertIn("La musica si vive insieme.", page.get_text())
        self.login()
        dashboard = self.soup(self.client.get("/admin"))
        self.assertEqual(dashboard.select_one('.dashboard-card[href="/admin/musica-insieme"] h2').get_text(),
                         "Scopri la Filarmonica")
        editor = self.soup(self.client.get("/admin/musica-insieme"))
        self.assertEqual(editor.h1.get_text(), "Scopri la Filarmonica")
        self.assertEqual(editor.select_one('.admin-nav a[href="/admin/musica-insieme"]').get_text(),
                         "Scopri la Filarmonica")
        self.assertEqual(editor.select_one('input[name="title"]')["value"], "La musica si vive insieme.")
        self.submit("/admin/musica-insieme", {"title": "Suoniamo insieme", "eyebrow": "La nostra comunità"})
        page = self.soup(self.client.get("/"))
        self.assertTrue(page.find("h2", string="Suoniamo insieme"))
        self.assertIn("La nostra comunità", page.get_text())
        editor = self.soup(self.client.get("/admin/musica-insieme"))
        self.assertEqual(editor.h1.get_text(), "Scopri la Filarmonica")
        self.assertEqual(editor.select_one('.admin-nav a[href="/admin/musica-insieme"]').get_text(),
                         "Scopri la Filarmonica")
        self.assertEqual(editor.select_one('input[name="title"]')["value"], "Suoniamo insieme")
        dashboard = self.soup(self.client.get("/admin"))
        self.assertEqual(dashboard.select_one('.dashboard-card[href="/admin/musica-insieme"] h2').get_text(),
                         "Scopri la Filarmonica")
        before = self.rows("SELECT * FROM home_intro")
        self.submit("/admin/musica-insieme", {"title": "", "eyebrow": "Non salvare"}, expected=422)
        self.assertEqual(self.rows("SELECT * FROM home_intro"), before)

    def test_home_cards_create_reorder_publish_edit_and_delete(self):
        self.login()
        values = self.feature_data()
        self.submit("/admin/musica-insieme/new", values)
        record = self.rows("SELECT * FROM home_features WHERE title=?", (values["title"],))[0]
        path = f"/admin/musica-insieme/{record['id']}"
        page = self.soup(self.client.get("/"))
        card = page.select_one(".feature-card")
        self.assertEqual(card.h3.get_text(), values["title"])
        self.assertEqual(card["href"], values["url"])
        self.assertEqual(card.select_one(".text-link").get_text(), values["link_label"])
        values.update(title="Musica per tutti aggiornata", sort_order="99", url="https://example.com/musica")
        self.submit(path + "/edit", values)
        self.assertEqual(self.soup(self.client.get("/")).select(".feature-card")[-1].h3.get_text(), values["title"])
        values.pop("published")
        self.submit(path + "/edit", values)
        self.assertNotIn(values["title"], self.client.get("/").get_data(as_text=True))
        values["published"] = "1"
        self.submit(path + "/edit", values)
        self.assertIn(values["title"], self.client.get("/").get_data(as_text=True))
        self.assertEqual(self.client.get(path + "/delete").status_code, 200)
        self.assertTrue(self.rows("SELECT * FROM home_features WHERE id=?", (record["id"],)))
        self.submit(path + "/delete")
        self.assertEqual(self.rows("SELECT * FROM home_features WHERE id=?", (record["id"],)), [])
        self.assertNotIn(values["title"], self.client.get("/").get_data(as_text=True))
        self.assertEqual(self.client.get(path + "/edit").status_code, 404)

    def test_teacher_cards_create_reorder_publish_edit_and_delete(self):
        self.login()
        values = self.teacher_data()
        values["name"] = "Maestra Uno\nMaestro Due"
        self.submit("/admin/insegnanti/new", values)
        record = self.rows("SELECT * FROM teachers WHERE name=?", (values["name"],))[0]
        path = f"/admin/insegnanti/{record['id']}"
        card = self.soup(self.client.get("/scuola-allievi.html")).select_one(".teacher-entry")
        self.assertEqual(card.h3.get_text(" ", strip=True), "Maestra Uno Maestro Due")
        self.assertEqual(len(card.h3.select("br")), 1)
        self.assertEqual(card.select_one(".eyebrow").get_text(), "Violino")
        self.assertEqual(card.img["src"], values["image"])
        values.update(name="Maestra aggiornata", instrument="Pianoforte", sort_order="99")
        self.submit(path + "/edit", values)
        self.assertEqual(self.soup(self.client.get("/scuola-allievi.html")).select(".teacher-entry")[-1].h3.get_text(), values["name"])
        values.pop("published")
        self.submit(path + "/edit", values)
        self.assertNotIn(values["name"], self.client.get("/scuola-allievi.html").get_data(as_text=True))
        values["published"] = "1"
        self.submit(path + "/edit", values)
        self.assertIn(values["name"], self.client.get("/scuola-allievi.html").get_data(as_text=True))
        self.assertEqual(self.client.get(path + "/delete").status_code, 200)
        self.assertTrue(self.rows("SELECT * FROM teachers WHERE id=?", (record["id"],)))
        self.submit(path + "/delete")
        self.assertEqual(self.rows("SELECT * FROM teachers WHERE id=?", (record["id"],)), [])
        self.assertNotIn(values["name"], self.client.get("/scuola-allievi.html").get_data(as_text=True))
        self.assertEqual(self.client.get(path + "/edit").status_code, 404)

    def test_new_section_fields_validate_before_saving_and_escape_plain_text(self):
        self.login()
        for section, table, values, invalid in (
            ("musica-insieme", "home_features", self.feature_data(), [
                {"title": ""}, {"description": ""}, {"url": "//example.com/link"},
                {"url": "not-a-link"}, {"sort_order": "first"}, {"sort_order": "1000001"},
            ]),
            ("insegnanti", "teachers", self.teacher_data(), [
                {"name": ""}, {"instrument": ""}, {"image": "http://example.com/photo.jpg"},
                {"image": "relative-photo.jpg"}, {"sort_order": "first"}, {"sort_order": "-1000001"},
            ]),
        ):
            before = self.rows(f"SELECT * FROM {table}")
            for changes in invalid:
                with self.subTest(section=section, changes=changes):
                    self.submit(f"/admin/{section}/new", dict(values, **changes), expected=422)
                    self.assertEqual(self.rows(f"SELECT * FROM {table}"), before)
        feature = self.feature_data()
        feature.update(title="<strong>Titolo</strong>", description="<em>Testo</em>")
        self.submit("/admin/musica-insieme/new", feature)
        card = self.soup(self.client.get("/")).select_one(".feature-card")
        self.assertEqual(card.h3.get_text(), feature["title"])
        self.assertEqual(card.p.get_text(), feature["description"])
        self.assertIsNone(card.select_one("strong, em"))
        teacher = self.teacher_data()
        teacher.update(name="<strong>Maestra</strong>", image_alt='La maestra "in concerto"')
        self.submit("/admin/insegnanti/new", teacher)
        card = self.soup(self.client.get("/scuola-allievi.html")).select_one(".teacher-entry")
        self.assertEqual(card.h3.get_text(), teacher["name"])
        self.assertIsNone(card.h3.strong)
        self.assertEqual(card.img["alt"], teacher["image_alt"])

    def test_teacher_image_upload_and_invalid_file_leave_existing_record_unchanged(self):
        self.login()
        values = self.teacher_data()
        stream = io.BytesIO()
        Image.new("RGB", (32, 24), "blue").save(stream, "PNG")
        stream.seek(0)
        self.submit("/admin/insegnanti/new", dict(values, image_upload=(stream, "maestra.png")))
        record = self.rows("SELECT * FROM teachers WHERE name=?", (values["name"],))[0]
        self.assertRegex(record["image"], r"^/uploads/[0-9a-f]{40}\.webp$")
        response = self.client.get(record["image"])
        self.assertEqual(response.status_code, 200)
        with Image.open(io.BytesIO(response.data)) as uploaded:
            self.assertEqual(uploaded.size, (32, 24))
        response.close()
        self.submit(f"/admin/insegnanti/{record['id']}/edit",
                    dict(values, image_upload=(io.BytesIO(b"Not a photograph."), "notes.txt")), expected=422)
        self.assertEqual(self.rows("SELECT * FROM teachers WHERE id=?", (record["id"],))[0], record)
        values.update(name="Insegnante senza foto", image="")
        self.submit("/admin/insegnanti/new", values)
        card = next(card for card in self.soup(self.client.get("/scuola-allievi.html")).select(".teacher-entry")
                    if card.h3.get_text() == values["name"])
        self.assertIsNone(card.img)

    def test_removed_initial_cards_and_teachers_do_not_return_after_restart(self):
        self.login()
        self.submit("/admin/musica-insieme", {"title": "Una nuova storia", "eyebrow": "Insieme"})
        for section, table in (("musica-insieme", "home_features"), ("insegnanti", "teachers")):
            for row in self.rows(f"SELECT id FROM {table}"):
                self.submit(f"/admin/{section}/{row['id']}/delete")
        original_events = self.rows("SELECT * FROM events")
        for _ in range(2):
            self.app = create_app(self.config)
            self.client = self.app.test_client()
            self.assertEqual(self.rows("SELECT * FROM home_features"), [])
            self.assertEqual(self.rows("SELECT * FROM teachers"), [])
            self.assertEqual(self.rows("SELECT * FROM events"), original_events)
            self.assertEqual(self.rows("SELECT title,eyebrow FROM home_intro"), [{"title": "Una nuova storia", "eyebrow": "Insieme"}])
            self.assertFalse(self.soup(self.client.get("/")).select(".feature-card"))
            self.assertFalse(self.soup(self.client.get("/scuola-allievi.html")).select(".teacher-entry"))


if __name__ == "__main__":
    unittest.main()
