
CREATE TABLE IF NOT EXISTS companies (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, careers_url TEXT NOT NULL DEFAULT '',
 source_type TEXT NOT NULL DEFAULT 'Prueba', enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
 last_checked TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS jobs (
 id INTEGER PRIMARY KEY, external_id TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
 company_id INTEGER NOT NULL REFERENCES companies(id), location TEXT, modality TEXT,
 description TEXT DEFAULT '', url TEXT NOT NULL DEFAULT '', published_date TEXT,
 discovered_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, last_seen TEXT,
 score INTEGER CHECK(score BETWEEN 0 AND 100),
 status TEXT NOT NULL DEFAULT 'Nueva' CHECK(status IN
 ('Nueva','Pendiente de revisar','Me interesa','CV enviado','Inscrito','Descartada')),
 is_new INTEGER NOT NULL DEFAULT 1 CHECK(is_new IN (0,1)),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 source_name TEXT, source_url TEXT, remote INTEGER CHECK(remote IN (0,1)),
 experience_level TEXT, department TEXT, brand TEXT,
 is_test_data INTEGER NOT NULL DEFAULT 0 CHECK(is_test_data IN (0,1)),
 is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)));
CREATE INDEX IF NOT EXISTS jobs_company_idx ON jobs(company_id);
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS source_runs (
 id INTEGER PRIMARY KEY, source TEXT NOT NULL, started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 finished_at TEXT, success INTEGER CHECK(success IN (0,1)), total_found INTEGER NOT NULL DEFAULT 0,
 new_jobs INTEGER NOT NULL DEFAULT 0, updated_jobs INTEGER NOT NULL DEFAULT 0,
 excluded_jobs INTEGER NOT NULL DEFAULT 0, error_message TEXT);
