-- Additive, versioned initialization: never drop existing content.
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT OR IGNORE INTO metadata VALUES ('schema_version', '1');
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  password_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at);
CREATE TABLE IF NOT EXISTS login_attempts (
  key TEXT PRIMARY KEY, count INTEGER NOT NULL, window_start INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY, slug TEXT NOT NULL UNIQUE, title TEXT NOT NULL, date TEXT NOT NULL,
  location TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
  published INTEGER NOT NULL DEFAULT 1 CHECK(published IN (0,1))
);
CREATE TABLE IF NOT EXISTS news (
  id INTEGER PRIMARY KEY, slug TEXT NOT NULL UNIQUE, title TEXT NOT NULL, date TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '', body TEXT NOT NULL DEFAULT '',
  image TEXT NOT NULL DEFAULT '', image_alt TEXT NOT NULL DEFAULT '', external_url TEXT NOT NULL DEFAULT '',
  published INTEGER NOT NULL DEFAULT 1 CHECK(published IN (0,1))
);
CREATE TABLE IF NOT EXISTS albums (
  id INTEGER PRIMARY KEY, slug TEXT NOT NULL UNIQUE, title TEXT NOT NULL, date TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '', folder TEXT NOT NULL DEFAULT '', cover TEXT NOT NULL DEFAULT '',
  cover_alt TEXT NOT NULL DEFAULT '', cover_position TEXT NOT NULL DEFAULT '',
  published INTEGER NOT NULL DEFAULT 1 CHECK(published IN (0,1))
);
CREATE TABLE IF NOT EXISTS photos (
  id INTEGER PRIMARY KEY, album_id INTEGER NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
  src TEXT NOT NULL, thumbnail TEXT NOT NULL DEFAULT '', original TEXT NOT NULL DEFAULT '',
  alt TEXT NOT NULL DEFAULT '', sort_order INTEGER NOT NULL DEFAULT 0,
  source TEXT NOT NULL DEFAULT 'upload',
  published INTEGER NOT NULL DEFAULT 1 CHECK(published IN (0,1)), UNIQUE(album_id, src)
);
CREATE INDEX IF NOT EXISTS photos_album ON photos(album_id, sort_order);
CREATE INDEX IF NOT EXISTS events_date ON events(published, date);
CREATE INDEX IF NOT EXISTS news_date ON news(published, date);
CREATE INDEX IF NOT EXISTS albums_date ON albums(published, date);

CREATE TABLE IF NOT EXISTS home_intro (
  id INTEGER PRIMARY KEY CHECK(id=1), eyebrow TEXT NOT NULL DEFAULT '', title TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS home_features (
  id INTEGER PRIMARY KEY, eyebrow TEXT NOT NULL DEFAULT '', title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '', url TEXT NOT NULL, link_label TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  published INTEGER NOT NULL DEFAULT 1 CHECK(published IN (0,1))
);
CREATE TABLE IF NOT EXISTS teachers (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, instrument TEXT NOT NULL,
  image TEXT NOT NULL DEFAULT '', image_alt TEXT NOT NULL DEFAULT '',
  image_width INTEGER, image_height INTEGER, sort_order INTEGER NOT NULL DEFAULT 0,
  published INTEGER NOT NULL DEFAULT 1 CHECK(published IN (0,1))
);
CREATE TABLE IF NOT EXISTS home_selection (
  id INTEGER PRIMARY KEY CHECK(id=1),
  configured INTEGER NOT NULL DEFAULT 0 CHECK(configured IN (0,1)),
  news_id INTEGER REFERENCES news(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS home_events (
  event_id INTEGER PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE
);

-- Move the previously hard-coded public sections into editable storage once.
-- The marker survives content deletion, so startup never restores removed cards.
BEGIN IMMEDIATE;
INSERT OR IGNORE INTO home_selection (id) VALUES (1);
INSERT OR IGNORE INTO home_intro (id, eyebrow, title)
  SELECT 1, 'Scopri la Filarmonica', 'La musica si vive insieme.'
  WHERE NOT EXISTS (SELECT 1 FROM metadata WHERE key='editable_sections_initialized');
INSERT INTO home_features (eyebrow, title, description, url, link_label, sort_order)
  SELECT 'La Filarmonica', 'Una storia, una città',
    'Dal 1809, generazioni di musicisti hanno dato voce a Lecco.',
    '/la-filarmonica#storia', 'Scopri di più', 0
  WHERE NOT EXISTS (SELECT 1 FROM metadata WHERE key='editable_sections_initialized');
INSERT INTO home_features (eyebrow, title, description, url, link_label, sort_order)
  SELECT 'Scuola allievi', 'La musica comincia qui',
    'Lezioni di strumento, propedeutica e Junior Band per crescere insieme.',
    '/scuola-allievi#info-e-costi', 'Scopri di più', 1
  WHERE NOT EXISTS (SELECT 1 FROM metadata WHERE key='editable_sections_initialized');
INSERT INTO home_features (eyebrow, title, description, url, link_label, sort_order)
  SELECT 'Partecipa', 'Sostieni la musica',
    'Aiutaci a portare avanti concerti, scuola e vita associativa.',
    '/sostienici', 'Scopri di più', 2
  WHERE NOT EXISTS (SELECT 1 FROM metadata WHERE key='editable_sections_initialized');
INSERT INTO teachers (name, instrument, image, image_alt, image_width, image_height, sort_order)
  SELECT 'Emanuela Milani', 'Flauto', '/assets/emanuela-milani.jpg', 'Emanuela Milani', 894, 894, 0
  WHERE NOT EXISTS (SELECT 1 FROM metadata WHERE key='editable_sections_initialized');
INSERT INTO teachers (name, instrument, image, image_alt, image_width, image_height, sort_order)
  SELECT 'Francesco Chimienti', 'Clarinetto', '/assets/francesco-chimienti.jpg', 'Francesco Chimienti', 640, 640, 1
  WHERE NOT EXISTS (SELECT 1 FROM metadata WHERE key='editable_sections_initialized');
INSERT INTO teachers (name, instrument, image, image_alt, image_width, image_height, sort_order)
  SELECT 'Gabriele Rota', 'Sassofono', '/assets/gabriele-rota.jpg', 'Gabriele Rota', 2160, 2160, 2
  WHERE NOT EXISTS (SELECT 1 FROM metadata WHERE key='editable_sections_initialized');
INSERT INTO teachers (name, instrument, image, image_alt, image_width, image_height, sort_order)
  SELECT 'Massimiliano Crotta', 'Ottoni', '/assets/massimiliano-crotta.jpg', 'Massimiliano Crotta', 743, 743, 3
  WHERE NOT EXISTS (SELECT 1 FROM metadata WHERE key='editable_sections_initialized');
INSERT INTO teachers (name, instrument, image, image_alt, image_width, image_height, sort_order)
  SELECT 'Tiziano Rusconi', 'Percussioni', '/assets/tiziano-rusconi.jpg', 'Tiziano Rusconi', 930, 930, 4
  WHERE NOT EXISTS (SELECT 1 FROM metadata WHERE key='editable_sections_initialized');
INSERT INTO teachers (name, instrument, image, image_alt, image_width, image_height, sort_order)
  SELECT 'Arianna Mandelli' || char(10) || 'Giulia Longhi', 'Propedeutica',
    '/assets/arianna-mandelli-giulia-longhi.jpg', 'Arianna Mandelli e Giulia Longhi', 1414, 1414, 5
  WHERE NOT EXISTS (SELECT 1 FROM metadata WHERE key='editable_sections_initialized');
INSERT OR IGNORE INTO metadata (key, value) VALUES ('editable_sections_initialized', '1');
COMMIT;
