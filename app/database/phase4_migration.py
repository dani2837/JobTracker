import logging
import sqlite3
from app.database.schema import SCHEMA

JOB_COLUMNS = {key: 'TEXT' for key in ('category','employment_type','professional_profile','service_line','study_area')}
JOB_COLUMNS['general_application'] = 'INTEGER NOT NULL DEFAULT 0'
COMPANY_COLUMNS = {'accepts_spontaneous_application': 'INTEGER NOT NULL DEFAULT 0',
    'spontaneous_application_url': 'TEXT', 'spontaneous_application_status': "TEXT NOT NULL DEFAULT 'No enviada'",
    'spontaneous_application_date': 'TEXT', 'notes': "TEXT NOT NULL DEFAULT ''"}


def migrate_phase4(connection, path):
    columns = {r['name'] for r in connection.execute('PRAGMA table_info(jobs)')}
    companies = {r['name'] for r in connection.execute('PRAGMA table_info(companies)')}
    rebuild = any([r['name'] for r in connection.execute(f'PRAGMA index_info("{index["name"]}")')] == ['external_id']
                  for index in connection.execute('PRAGMA index_list(jobs)') if index['unique'])
    changed = rebuild or not set(JOB_COLUMNS) <= columns or not set(COMPANY_COLUMNS) <= companies
    if changed:
        backup = path.with_name(path.name + '.pre-phase4.bak')
        if not backup.exists():
            with sqlite3.connect(backup) as target:
                connection.backup(target)
    connection.execute('BEGIN IMMEDIATE')
    if rebuild:
        statement = next(sql for sql in SCHEMA.split(';') if 'CREATE TABLE IF NOT EXISTS jobs (' in sql)
        connection.execute(statement.replace('IF NOT EXISTS jobs (', 'jobs_phase4 ('))
        names = ','.join('"'+name+'"' for name in sorted(columns))
        connection.execute(f'INSERT INTO jobs_phase4 ({names}) SELECT {names} FROM jobs')
        connection.execute('DROP TABLE jobs')
        connection.execute('ALTER TABLE jobs_phase4 RENAME TO jobs')
    else:
        for key, definition in JOB_COLUMNS.items():
            if key not in columns:
                connection.execute(f'ALTER TABLE jobs ADD COLUMN {key} {definition}')
    for key, definition in COMPANY_COLUMNS.items():
        if key not in companies:
            connection.execute(f'ALTER TABLE companies ADD COLUMN {key} {definition}')
    connection.execute('CREATE INDEX IF NOT EXISTS jobs_company_idx ON jobs(company_id)')
    connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS jobs_source_reference_idx ON jobs(COALESCE(source_name,''),external_id)")
    connection.execute("INSERT OR REPLACE INTO metadata VALUES ('sources_schema_version','4')")
    if changed:
        logging.getLogger(__name__).info('Migración Fase 4: campos de fuentes y candidaturas manuales; IDs y estados preservados')
