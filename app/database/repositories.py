import logging
from datetime import date, datetime, timedelta, timezone
from app.database.db import Database
from app.database.schema import STATUSES
from app.database.scoring_repository import write_score


class CompanyRepository:
    def __init__(self, db: Database):
        self.db = db

    def add(self, name: str, careers_url: str = '') -> int:
        with self.db.connect() as connection:
            cursor = connection.execute('INSERT INTO companies(name,careers_url) VALUES (?,?)', (name, careers_url))
            return int(cursor.lastrowid)

    def get_companies(self) -> list[dict]:
        with self.db.connect() as connection:
            return [dict(row) for row in connection.execute('''SELECT c.*, COUNT(j.id) AS job_count
                FROM companies c LEFT JOIN jobs j ON j.company_id=c.id GROUP BY c.id ORDER BY c.name''')]

    def set_enabled(self, company_id: int, enabled: bool) -> None:
        with self.db.connect() as connection:
            connection.execute('UPDATE companies SET enabled=? WHERE id=?', (enabled, company_id))
        logging.getLogger(__name__).info('Empresa %s activa=%s', company_id, enabled)

    def save_spontaneous_application(self, company_id, status, notes):
        if status not in ('No enviada', 'CV enviado'):
            raise ValueError('Estado de candidatura no válido')
        with self.db.connect() as connection:
            previous = connection.execute('SELECT * FROM companies WHERE id=?', (company_id,)).fetchone()
            if previous is None or not previous['accepts_spontaneous_application']:
                raise ValueError('La empresa no tiene candidatura espontánea configurada')
            sent = (previous['spontaneous_application_date'] or datetime.now(timezone.utc).isoformat()) if status == 'CV enviado' else None
            connection.execute('UPDATE companies SET spontaneous_application_status=?,spontaneous_application_date=?,notes=? WHERE id=?',
                               (status, sent, notes, company_id))


class JobRepository:
    def __init__(self, db: Database):
        self.db = db

    def add(self, *, external_id: str, title: str, company_id: int, location: str | None,
            modality: str | None, score: int | None, description: str | None = '', url: str = '',
            published_date: str | None = None) -> int:
        with self.db.connect() as connection:
            cursor = connection.execute('''INSERT INTO jobs
                (external_id,title,company_id,location,modality,score,description,url,published_date)
                VALUES (?,?,?,?,?,?,?,?,?)''',
                (external_id, title, company_id, location, modality, score, description, url, published_date))
            return int(cursor.lastrowid)

    def get_all_jobs(self, *, show_discarded: bool = True) -> list[dict]:
        with self.db.connect() as connection:
            return [dict(row) for row in connection.execute('''SELECT j.*, c.name AS company
                FROM jobs j JOIN companies c ON c.id=j.company_id
                WHERE (? OR j.status != 'Descartada') ORDER BY j.score DESC,j.id''', (show_discarded,))]

    def get_job_by_id(self, job_id: int) -> dict | None:
        with self.db.connect() as connection:
            row = connection.execute('''SELECT j.*,c.name AS company FROM jobs j
                JOIN companies c ON c.id=j.company_id WHERE j.id=?''', (job_id,)).fetchone()
            return dict(row) if row else None

    def update_job_status(self, job_id: int, status: str) -> None:
        if status not in STATUSES:
            raise ValueError('Estado no permitido')
        with self.db.connect() as connection:
            cursor = connection.execute('''UPDATE jobs SET status=?,is_new=?,
                updated_at=strftime('%Y-%m-%d %H:%M:%f','now') WHERE id=?''',
                (status, status == 'Nueva', job_id))
            if cursor.rowcount != 1:
                raise ValueError('Oferta inexistente')
        logging.getLogger(__name__).info('Cambio de estado oferta %s: %s', job_id, status)

    def get_jobs_by_company(self, company_id: int) -> list[dict]:
        return [job for job in self.get_all_jobs() if job['company_id'] == company_id]

    def mark_seen(self, job_id: int) -> None:
        with self.db.connect() as connection:
            cursor = connection.execute("UPDATE jobs SET is_new=0,updated_at=strftime('%Y-%m-%d %H:%M:%f','now') WHERE id=?", (job_id,))
            if cursor.rowcount != 1:
                raise ValueError('Oferta inexistente')

    def daily_summary(self) -> str:
        with self.db.connect() as connection:
            row = connection.execute('''SELECT
                COALESCE(SUM(date(discovered_date,'localtime')=date('now','localtime')),0) AS today,
                COALESCE(SUM(date(discovered_date,'localtime')=date('now','localtime') AND NOT excluded),0) AS compatible,
                COALESCE(SUM(is_new AND NOT excluded AND status!='Descartada'),0) AS pending
                FROM jobs WHERE is_test_data=0''').fetchone()
        return f"Hoy: {row['today']} descubiertas · {row['compatible']} no excluidas · {row['pending']} nuevas por revisar"

    def get_top_jobs(self, show_discarded: bool = True) -> list[dict]:
        return [job for job in self.get_all_jobs(show_discarded=show_discarded)
                if job['score'] is not None and not job['excluded']][:5]

    def get_source_counts(self, show_discarded: bool = True) -> dict:
        with self.db.connect() as connection:
            return dict(connection.execute('''SELECT COALESCE(SUM(is_test_data),0) AS test,
                COALESCE(SUM(NOT is_test_data),0) AS real,
                COALESCE(SUM(score IS NULL),0) AS unscored FROM jobs
                WHERE (? OR status != 'Descartada')''', (show_discarded,)).fetchone())

    def get_new_by_source(self, show_discarded=True):
        with self.db.connect() as connection:
            return {row['source_name']: row['total'] for row in connection.execute('''SELECT source_name,COUNT(*) AS total
                FROM jobs WHERE is_test_data=0 AND is_new=1 AND (? OR status!='Descartada') GROUP BY source_name''',
                (show_discarded,))}

    def import_scan(self, source, scan, run_id: int, *, today: date, check_cancel, scorer=None) -> dict:
        multi_company = getattr(source, 'multi_company', False)
        now = datetime.now(timezone.utc).isoformat(timespec='microseconds')
        cutoff = today - timedelta(days=60)
        scan_ids = {job.external_id for job in scan.jobs}
        from collections import Counter
        scan_urls = Counter(job.url for job in scan.jobs)
        new = updated = excluded = 0
        with self.db.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            companies = connection.execute('SELECT * FROM companies').fetchall()
            matches = [c for c in companies if c['name'].strip().casefold() == source.company.strip().casefold()]
            if not multi_company and (len(matches) != 1 or not matches[0]['enabled']):
                raise ValueError(f'{source.company} debe existir y estar activa en Empresas')
            company_id = matches[0]['id'] if not multi_company else None
            by_name = {}
            for company in companies:
                by_name.setdefault(company['name'].strip().casefold(), []).append(company)
            # Solo se llega aquí después de descargar y validar el escaneo completo.
            if multi_company:
                connection.execute('''UPDATE jobs SET is_active=0 WHERE source_name=? AND is_test_data=0
                    AND company_id IN (SELECT id FROM companies WHERE enabled=1)''', (source.name,))
            else:
                connection.execute('''UPDATE jobs SET is_active=0
                    WHERE company_id=? AND source_name=? AND is_test_data=0''', (company_id, source.name))
            for job in scan.jobs:
                check_cancel()
                if multi_company:
                    key = job.company.strip().casefold()
                    employers = by_name.get(key, [])
                    if len(employers) > 1:
                        raise ValueError('Nombre de empresa ambiguo en el portal')
                    if not employers:
                        cursor = connection.execute("INSERT INTO companies(name,source_type) VALUES (?,'Portal público')",
                                                    (job.company.strip(),))
                        employers = [{'id': cursor.lastrowid, 'enabled': True}]
                        by_name[key] = employers
                    if not employers[0]['enabled']:
                        continue
                    company_id = employers[0]['id']
                existing = connection.execute('SELECT * FROM jobs WHERE source_name=? AND external_id=?', (source.name, job.external_id)).fetchone()
                if connection.execute('SELECT 1 FROM jobs WHERE external_id=? AND is_test_data=1', (job.external_id,)).fetchone():
                    raise ValueError('La referencia coincide con una oferta de otra procedencia')
                if existing is None and job.url and scan_urls[job.url] == 1:
                    matches_url = connection.execute('SELECT * FROM jobs WHERE company_id=? AND source_name=? AND url=? AND is_test_data=0',
                                                     (company_id, source.name, job.url)).fetchall()
                    if len(matches_url) == 1 and matches_url[0]['external_id'] not in scan_ids:
                        existing = matches_url[0]
                if existing and (existing['company_id'] != company_id or existing['is_test_data']
                                 or existing['source_name'] != source.name):
                    raise ValueError('La referencia coincide con una oferta de otra procedencia')
                if not existing and job.published_date and job.published_date < cutoff:
                    excluded += 1
                    continue
                fields = (job.title, job.location, job.modality, job.description, job.url,
                          job.published_date.isoformat() if job.published_date else None,
                          job.source_url, job.remote, job.experience_level, job.department, job.brand)
                if existing:
                    connection.execute('''UPDATE jobs SET title=?,location=?,modality=?,description=?,url=?,
                        published_date=?,source_url=?,remote=?,experience_level=?,department=?,brand=?,
                        last_seen=?,updated_at=?,is_active=1 WHERE id=?''', (*fields, now, now, existing['id']))
                    updated += 1
                else:
                    connection.execute('''INSERT INTO jobs
                        (title,location,modality,description,url,published_date,source_url,remote,
                         experience_level,department,brand,external_id,company_id,source_name,score,
                         is_test_data,is_active,is_new,status,discovered_date,last_seen,created_at,updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,0,1,1,'Nueva',?,?,?,?)''',
                        (*fields, job.external_id, company_id, source.name, now, now, now, now))
                    new += 1
                saved = connection.execute('SELECT * FROM jobs WHERE id=?', (existing['id'],)).fetchone() if existing else connection.execute(
                    'SELECT * FROM jobs WHERE source_name=? AND external_id=?', (source.name, job.external_id)).fetchone()
                connection.execute('''UPDATE jobs SET external_id=?,category=?,employment_type=?,professional_profile=?,service_line=?,
                    study_area=?,general_application=? WHERE id=?''', (job.external_id, job.category, job.employment_type,
                    job.professional_profile, job.service_line, job.study_area, job.general_application, saved['id']))
                if scorer is not None:
                    saved = connection.execute('SELECT * FROM jobs WHERE id=?', (saved['id'],)).fetchone()
                    write_score(connection, saved['id'], scorer.evaluate(dict(saved)))
            check_cancel()
            if not multi_company:
                connection.execute('''UPDATE companies SET careers_url=?,source_type='Portal público',last_checked=?
                    WHERE id=?''', (source.url, now, company_id))
            connection.execute('''UPDATE source_runs SET finished_at=?,success=1,total_found=?,
                new_jobs=?,updated_jobs=?,excluded_jobs=? WHERE id=?''',
                (now, scan.total_found, new, updated, excluded, run_id))
        return dict(total_found=scan.total_found, new_jobs=new, updated_jobs=updated, excluded_jobs=excluded)

    def get_dashboard_stats(self, show_discarded: bool = True) -> dict[str, int]:
        with self.db.connect() as connection:
            return dict(connection.execute('''SELECT COUNT(*) AS total,
                COALESCE(SUM(is_new),0) AS nuevas, COALESCE(SUM(score>=90 AND NOT excluded),0) AS prioritarias,
                COALESCE(SUM(score BETWEEN 75 AND 89 AND NOT excluded),0) AS interesantes,
                COALESCE(SUM(score BETWEEN 60 AND 74 AND NOT excluded),0) AS revisar,
                COALESCE(SUM(score BETWEEN 40 AND 59 AND NOT excluded),0) AS baja
                FROM jobs WHERE (? OR status != 'Descartada')''', (show_discarded,)).fetchone())


class SourceRunRepository:
    def __init__(self, db: Database):
        self.db = db

    def start(self, source: str) -> int:
        with self.db.connect() as connection:
            return int(connection.execute('INSERT INTO source_runs(source) VALUES (?)', (source,)).lastrowid)

    def fail(self, run_id: int, message: str) -> None:
        with self.db.connect() as connection:
            connection.execute('''UPDATE source_runs SET finished_at=CURRENT_TIMESTAMP,success=0,error_message=?
                WHERE id=?''', (message[:1000], run_id))

    def get_runs(self) -> list[dict]:
        with self.db.connect() as connection:
            return [dict(row) for row in connection.execute('SELECT * FROM source_runs ORDER BY id DESC')]
