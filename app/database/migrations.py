"""Migración transaccional que conserva IDs, estados y fechas de la Fase 1."""
import logging
import sqlite3
from pathlib import Path
from app.database.schema import SCHEMA

NEW_COLUMNS = {
    'source_name': 'TEXT', 'source_url': 'TEXT', 'remote': 'INTEGER CHECK(remote IN (0,1))',
    'experience_level': 'TEXT', 'department': 'TEXT', 'brand': 'TEXT',
    'is_test_data': 'INTEGER NOT NULL DEFAULT 0 CHECK(is_test_data IN (0,1))',
    'is_active': 'INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1))',
}


def migrate(connection: sqlite3.Connection, path: Path) -> None:
    columns = {row['name']: row for row in connection.execute('PRAGMA table_info(jobs)')}
    rebuild = any(columns[name]['notnull'] for name in ('score', 'location', 'modality', 'description'))
    missing = set(NEW_COLUMNS) - columns.keys()
    if rebuild or missing:
        # SQLite no permite quitar NOT NULL con ALTER COLUMN. Copia local previa,
        # y reconstrucción solo de jobs dentro de una transacción con rollback.
        backup_path = path.with_name(path.name + '.pre-phase2.bak')
        if not backup_path.exists():
            with sqlite3.connect(backup_path) as backup:
                connection.backup(backup)
        connection.execute('BEGIN IMMEDIATE')
        if rebuild:
            statement = next(sql for sql in SCHEMA.split(';') if 'CREATE TABLE IF NOT EXISTS jobs (' in sql)
            connection.execute(statement.replace('IF NOT EXISTS jobs (', 'jobs_phase2 ('))
            names = ','.join('"' + name + '"' for name in columns)
            connection.execute(f'INSERT INTO jobs_phase2 ({names}) SELECT {names} FROM jobs')
            connection.execute('DROP TABLE jobs')
            connection.execute('ALTER TABLE jobs_phase2 RENAME TO jobs')
            connection.execute('CREATE INDEX jobs_company_idx ON jobs(company_id)')
        else:
            for name in sorted(missing):
                connection.execute(f'ALTER TABLE jobs ADD COLUMN {name} {NEW_COLUMNS[name]}')
        logging.getLogger(__name__).info('Migración Fase 2 aplicada; copia: %s', backup_path)
    # Solo el patrón exacto del seed conocido; no etiquetar todas las filas antiguas.
    connection.execute("""UPDATE jobs SET is_test_data=1, source_name='Datos de prueba'
        WHERE external_id GLOB 'demo-[0-9][0-9][0-9]' AND description LIKE 'DATOS DE PRUEBA%'
        AND source_name IS NULL""")
    connection.execute('PRAGMA user_version=2')
