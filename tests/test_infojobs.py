import json
from dataclasses import replace
from datetime import date
from pathlib import Path
from threading import Event

import httpx
import pytest

from app.database.repositories import CompanyRepository, JobRepository
from app.services.job_importer import JobImporter
from app.services.source_update import update_all_jobs
from app.sources.base import ScanResult, SourceError
from app.sources.infojobs import InfoJobsSource
from app.sources.infojobs import initial_props
from app.sources.public_http import HttpOptions

FIX = Path(__file__).parent / 'fixtures/phase7'


def test_browser_protection_is_reported_instead_of_invalid_json():
    with pytest.raises(SourceError, match='bloquea el acceso automatizado'):
        initial_props('<h1>No podemos identificar tu navegador</h1><script>window.onProtectionInitialized = function() {}</script>')


def fixture(name):
    return json.loads((FIX / (name + '.json')).read_text(encoding='utf-8'))


def html(data):
    return '<script>window.__INITIAL_PROPS__ = JSON.parse(' + json.dumps(json.dumps(data)) + ');</script>'


def sample():
    source = InfoJobsSource()
    rows, _, _ = source.parse_listing(html(fixture('infojobs_listing')), 1)
    return source.parse_detail(html(fixture('infojobs_detail')), rows[0])


def test_real_public_fields_and_promoted_duplicates():
    source = InfoJobsSource()
    rows, total, pages = source.parse_listing(html(fixture('infojobs_listing')), 1)
    assert len(rows) == len({r['code'] for r in rows}) == 20
    assert (total, pages) == (65, 4)
    job = sample()
    assert job.company == 'abde business consulting' and job.source_name == 'InfoJobs'
    assert job.published_date == date(2026, 9, 7)
    assert job.location == 'Sevilla' and job.modality == 'Híbrido' and job.remote is False
    assert job.experience_level == 'Más de 5 años'
    assert 'Inglés: Avanzado' in job.description and 'Ingeniería Técnica' in job.description
    assert 'Brussels' in job.description and '?' not in job.url


def test_paginated_scan_keeps_filters_and_downloads_details_once():
    listing, detail = fixture('infojobs_listing'), fixture('infojobs_detail')
    base = next(r for r in listing['offers'] if 'PROMOTED' not in r['upsellings'])
    calls = []
    def handler(request):
        calls.append(str(request.url))
        if request.url.params:
            assert request.url.params['provinceIds'] == '43'
            assert request.url.params['categoryIds'] == '150'
            page = int(request.url.params['page'])
            row = {**base, 'code': str(page), 'link': '/sevilla/job/of-i' + str(page)}
            return httpx.Response(200, text=html({**listing, 'offers': [row, {**row, 'upsellings': ['PROMOTED']}],
                'navigation': {'self': page, 'totalElements': 2, 'totalPages': 2}}))
        return httpx.Response(200, text=html({'offer': {**detail['offer'], 'offerCode': request.url.path[-1]}}))
    source = InfoJobsSource(HttpOptions(delay=0), transport=httpx.MockTransport(handler))
    scan = source.fetch_jobs()
    assert scan.complete and scan.pages == scan.total_found == 2 and len(calls) == 4


@pytest.mark.parametrize('failure', ['http', 'login', 'filters', 'count', 'detail'])
def test_invalid_or_partial_scan_fails_closed(failure):
    listing = fixture('infojobs_listing')
    row = next(r for r in listing['offers'] if 'PROMOTED' not in r['upsellings'])
    listing.update(offers=[row], navigation={'self': 1, 'totalElements': 1, 'totalPages': 1})
    if failure == 'filters': listing['search']['provinceIds'] = []
    if failure == 'count': listing['navigation']['totalElements'] = 2
    def handler(request):
        if failure == 'http': return httpx.Response(403)
        if failure == 'login' or not request.url.params: return httpx.Response(200, text='<h1>Inicia sesión</h1>')
        return httpx.Response(200, text=html(listing))
    source = InfoJobsSource(HttpOptions(delay=0, retries=0), transport=httpx.MockTransport(handler))
    with pytest.raises(SourceError): source.fetch_jobs()


def memory_source(jobs):
    source = InfoJobsSource()
    source.fetch_jobs = lambda: ScanResult(tuple(jobs), 1, len(jobs), True)
    return source


def test_multiple_employers_reimport_manual_states_and_disabled_company(db):
    companies, repo = CompanyRepository(db), JobRepository(db)
    existing_id = companies.add('ABDE BUSINESS CONSULTING', 'https://example.com/careers')
    first = sample()
    second = replace(first, external_id='another', company='Otra empresa', url=first.url + '-other')
    source = memory_source([first, second])
    result = update_all_jobs(db, Event(), lambda message: None, sources=[source])
    assert result['new_jobs'] == 2 and result['errors'] == 0
    rows = repo.get_all_jobs()
    saved = next(j for j in rows if j['external_id'] == first.external_id)
    assert saved['company_id'] == existing_id and len(companies.get_companies()) == 2
    repo.update_job_status(saved['id'], 'CV enviado')
    result = JobImporter(db, source).run()
    assert result['new_jobs'] == 0 and result['updated_jobs'] == 2
    assert repo.get_job_by_id(saved['id'])['status'] == 'CV enviado'
    assert next(c for c in companies.get_companies() if c['id'] == existing_id)['careers_url'] == 'https://example.com/careers'
    companies.set_enabled(existing_id, False)
    before = repo.get_job_by_id(saved['id'])
    JobImporter(db, memory_source([])).run()
    assert repo.get_job_by_id(saved['id']) == before
    assert next(j for j in repo.get_all_jobs() if j['external_id'] == 'another')['is_active'] == 0


def test_portal_employer_change_rolls_back_all_changes(db):
    job = sample()
    JobImporter(db, memory_source([job])).run()
    before = JobRepository(db).get_all_jobs()
    with pytest.raises(ValueError, match='procedencia'):
        JobImporter(db, memory_source([replace(job, company='Empresa distinta')])).run()
    assert JobRepository(db).get_all_jobs() == before
    assert len(CompanyRepository(db).get_companies()) == 1
