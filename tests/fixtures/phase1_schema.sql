
CREATE TABLE IF NOT EXISTS companies (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, careers_url TEXT NOT NULL DEFAULT '',
 source_type TEXT NOT NULL DEFAULT 'Prueba', enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
 last_checked TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS jobs (
 id INTEGER PRIMARY KEY, external_id TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
 company_id INTEGER NOT NULL REFERENCES companies(id), location TEXT NOT NULL, modality TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '', url TEXT NOT NULL DEFAULT '', published_date TEXT,
 discovered_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, last_seen TEXT,
 score INTEGER NOT NULL CHECK(score BETWEEN 0 AND 100),
 status TEXT NOT NULL DEFAULT 'Nueva' CHECK(status IN
 ('Nueva','Pendiente de revisar','Me interesa','CV enviado','Inscrito','Descartada')),
 is_new INTEGER NOT NULL DEFAULT 1 CHECK(is_new IN (0,1)),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS jobs_company_idx ON jobs(company_id);
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
