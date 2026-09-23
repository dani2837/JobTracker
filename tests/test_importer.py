from dataclasses import replace
from datetime import date, timedelta
from threading import Event
import httpx
import pytest

from app.database.repositories import CompanyRepository, JobRepository, SourceRunRepository
from app.services.job_importer import JobImporter
from app.services.seed_data import seed_database
from app.sources.base import BaseSource, ScanCancelled, ScanResult, SourceError
from app.sources.sopra_steria import SopraSteriaSource, parse_detail, parse_listing
from tests.test_sources import DETAIL, LISTING, OPTIONS, fixture_page


class MemorySource(BaseSource):
    name = company = 'Sopra Steria'
    url = 'https://careers.soprasteria.es/jobs'

    def __init__(self, jobs, complete=True):
        self.jobs, self.complete = tuple(jobs), complete

    def fetch_jobs(self):
        return ScanResult(self.jobs, 1, len(self.jobs), self.complete)


@pytest.fixture
def real_job():
    return replace(parse_detail(DETAIL, parse_listing(LISTING)[1][0]), published_date=None)


def importer(db, jobs, **kwargs):
    return JobImporter(db, MemorySource(jobs), today=date(2026, 9, 7), **kwargs)


def test_insert_real_job_and_company(db, real_job):
    seed_database(db)
    result = importer(db, [real_job]).run()
    assert result == dict(total_found=1, new_jobs=1, updated_jobs=0, excluded_jobs=0)
    jobs = JobRepository(db).get_all_jobs()
    imported = next(job for job in jobs if not job['is_test_data'])
    assert imported['score'] is None
    assert imported['status'] == 'Nueva' and imported['is_new'] == 1
    assert imported['discovered_date'] == imported['last_seen']
    assert imported['company'] == 'Sopra Steria'
    assert sum(job['is_test_data'] for job in jobs) == 18
    assert len(CompanyRepository(db).get_companies()) == 15


@pytest.mark.parametrize('status', ['Nueva', 'Pendiente de revisar', 'Me interesa', 'CV enviado', 'Inscrito', 'Descartada'])
def test_reimport_preserves_manual_state(db, real_job, status):
    seed_database(db)
    importer(db, [real_job]).run()
    repo = JobRepository(db)
    original = next(job for job in repo.get_all_jobs() if not job['is_test_data'])
    repo.update_job_status(original['id'], status)
    result = importer(db, [replace(real_job, description='Descripción actualizada', location='Sevilla')]).run()
    saved = repo.get_job_by_id(original['id'])
    assert result['new_jobs'] == 0 and result['updated_jobs'] == 1
    assert len(repo.get_all_jobs()) == 19
    assert saved['status'] == status and saved['is_new'] == (status == 'Nueva')
    assert saved['discovered_date'] == original['discovered_date']
    assert saved['last_seen'] >= original['last_seen']
    assert saved['location'] == 'Sevilla' and saved['description'] == 'Descripción actualizada'
    assert SourceRunRepository(db).get_runs()[0]['success'] == 1


def test_date_window_unknown_and_boundary(db, real_job):
    seed_database(db)
    today = date(2026, 9, 7)
    jobs = [replace(real_job, external_id=str(i), published_date=day)
            for i, day in enumerate([None, today-timedelta(days=60), today-timedelta(days=61)])]
    result = importer(db, jobs).run()
    assert result['new_jobs'] == 2 and result['excluded_jobs'] == 1


def test_disappearance_only_after_complete_scan(db, real_job):
    seed_database(db)
    other = replace(real_job, external_id='other')
    importer(db, [real_job, other]).run()
    with pytest.raises(SourceError):
        JobImporter(db, MemorySource([real_job], complete=False)).run()
    assert all(job['is_active'] for job in JobRepository(db).get_all_jobs())
    importer(db, [real_job]).run()
    saved = {job['external_id']: job for job in JobRepository(db).get_all_jobs()}
    assert saved['other']['is_active'] == 0
    assert saved[real_job.external_id]['is_active'] == 1
    assert len(saved) == 20
    assert all(job['is_active'] for job in saved.values() if job['is_test_data'])


def test_http_failure_preserves_all_jobs(db, real_job):
    seed_database(db)
    importer(db, [real_job]).run()
    before = JobRepository(db).get_all_jobs()
    def handler(request):
        if request.url.params.get('page') == '1':
            return httpx.Response(200, text=fixture_page([0, 1]))
        return httpx.Response(503)
    source = SopraSteriaSource(OPTIONS, transport=httpx.MockTransport(handler))
    with pytest.raises(SourceError):
        JobImporter(db, source).run()
    assert JobRepository(db).get_all_jobs() == before
    run = SourceRunRepository(db).get_runs()[0]
    assert run['success'] == 0 and '503' in run['error_message']
    assert run['finished_at']


def test_import_rollback_and_cancel(db, real_job):
    seed_database(db)
    before = JobRepository(db).get_all_jobs()
    with pytest.raises(ValueError, match='procedencia'):
        importer(db, [real_job, replace(real_job, external_id='demo-001')]).run()
    assert JobRepository(db).get_all_jobs() == before
    cancel = Event()
    cancel.set()
    with pytest.raises(ScanCancelled):
        importer(db, [real_job], cancel=cancel).run()
    assert JobRepository(db).get_all_jobs() == before


def test_disabled_company_does_not_fetch(db, real_job, monkeypatch):
    seed_database(db)
    companies = CompanyRepository(db)
    company = next(c for c in companies.get_companies() if c['name'] == 'Sopra Steria')
    companies.set_enabled(company['id'], False)
    source = MemorySource([real_job])
    monkeypatch.setattr(source, 'fetch_jobs', lambda: pytest.fail('No debe consultar la red'))
    with pytest.raises(SourceError, match='Activa'):
        JobImporter(db, source).run()
