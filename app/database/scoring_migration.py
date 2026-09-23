"""Extensión aditiva del esquema; conserva la versión base de Fase 2."""
import logging
import sqlite3
from pathlib import Path

COLUMNS = {
    'classification': 'TEXT', 'excluded': 'INTEGER NOT NULL DEFAULT 0 CHECK(excluded IN (0,1))',
    'exclusion_reason': 'TEXT', 'score_details': 'TEXT', 'scored_at': 'TEXT',
}


def migrate_scoring(connection: sqlite3.Connection, path: Path):
    existing = {row['name'] for row in connection.execute('PRAGMA table_info(jobs)')}
    missing = set(COLUMNS) - existing
    if missing:
        backup_path = path.with_name(path.name + '.pre-phase3.bak')
        if not backup_path.exists():
            with sqlite3.connect(backup_path) as backup:
                connection.backup(backup)
        with connection:
            connection.execute('BEGIN IMMEDIATE')
            for name in sorted(missing):
                connection.execute(f'ALTER TABLE jobs ADD COLUMN {name} {COLUMNS[name]}')
        logging.getLogger(__name__).info('Migración scoring aplicada; copia: %s', backup_path)
    with connection:
        connection.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES ('scoring_schema_version','3')")
