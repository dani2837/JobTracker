from dataclasses import replace
from pathlib import Path
from threading import Event
import httpx
import pytest
from bs4 import BeautifulSoup

from app.sources.base import ScanCancelled, SourceError
from app.sources.sopra_steria import SourceOptions, SopraSteriaSource, parse_detail, parse_listing

FIXTURES = Path(__file__).parent / 'fixtures'
LISTING = (FIXTURES / 'sopra_listing.html').read_text(encoding='utf-8')
DETAIL = (FIXTURES / 'sopra_detail.html').read_text(encoding='utf-8')
OPTIONS = SourceOptions(delay=0, retries=0)


def fixture_page(indices, total=3):
    soup = BeautifulSoup(LISTING, 'html.parser')
    return (f'<span class="attrax-pagination__total-results">{total} resultado(s)</span>'
            + ''.join(str(soup.select('.attrax-vacancy-tile')[i]) for i in indices))


def fixture_detail(row):
    first = parse_listing(LISTING)[1][0]
    return DETAIL.replace(first['external_id'], row['external_id']).replace(first['url'], row['url'])


def test_real_saved_format():
    total, rows = parse_listing(LISTING)
    assert total == 112
    assert len(rows) == 6
    job = parse_detail(DETAIL, rows[0])
    assert job.external_id == '2b56c76a-3f2a-4813-81b7-5bf2228c25fa'
    assert job.title == 'Administrador/a Citrix (Inglés alto)'
    assert job.location == 'Madrid, Spain'
    assert job.remote is False
    assert job.modality is None  # «No» no demuestra trabajo presencial.
    assert job.experience_level == '6 to 10 years'
    assert job.department == 'Aeroespacial y transporte'
    assert 'Citrix Virtual Apps and Desktops' in job.description
    assert '<p>' not in job.description
    assert job.published_date.isoformat() == '2026-09-07'
    assert job.url.startswith('https://careers.soprasteria.es/job/')


def test_remote_and_unknown_fields():
    row = parse_listing(LISTING)[1][0]
    job = parse_detail(DETAIL, {**row, 'remote': 'Si', 'experience-level': None, 'location': None})
    assert job.remote is True
    assert job.modality == 'Teletrabajo disponible'
    assert job.location is None and job.experience_level is None


def test_pagination():
    calls = []
    rows = parse_listing(LISTING)[1]

    def handler(request):
        calls.append(str(request.url))
        if request.url.path == '/jobs':
            page = request.url.params['page']
            return httpx.Response(200, text=fixture_page([0, 1] if page == '1' else [2]))
        row = next(row for row in rows if row['url'] == str(request.url))
        return httpx.Response(200, text=fixture_detail(row))

    result = SopraSteriaSource(OPTIONS, transport=httpx.MockTransport(handler)).fetch_jobs()
    assert result.complete and result.pages == 2 and result.total_found == 3
    assert len({job.external_id for job in result.jobs}) == 3
    assert len(calls) == 5
    assert 'page=2' in calls[1]


@pytest.mark.parametrize('kind', ['repeat', 'max_pages', 'empty', 'changed_total', 'http', 'bad_html'])
def test_incomplete_scan_fails(kind):
    def handler(request):
        if request.url.params.get('page') == '1':
            return httpx.Response(200, text=fixture_page([0, 1]))
        if kind == 'http':
            return httpx.Response(503)
        if kind == 'bad_html':
            return httpx.Response(200, text='<html>Unavailable</html>')
        if kind == 'empty':
            return httpx.Response(200, text=fixture_page([]))
        if kind == 'changed_total':
            return httpx.Response(200, text=fixture_page([2], total=4))
        return httpx.Response(200, text=fixture_page([0, 1]))

    options = replace(OPTIONS, max_pages=1) if kind == 'max_pages' else OPTIONS
    with pytest.raises(SourceError):
        SopraSteriaSource(options, transport=httpx.MockTransport(handler)).fetch_jobs()


def test_retry_is_limited(monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(503)
    source = SopraSteriaSource(replace(OPTIONS, retries=2), transport=httpx.MockTransport(handler))
    monkeypatch.setattr(source, '_pause', lambda seconds: None)
    with pytest.raises(SourceError, match='503'):
        source.fetch_jobs()
    assert len(calls) == 3


def test_cancel_before_network():
    cancel = Event()
    cancel.set()
    with pytest.raises(ScanCancelled):
        SopraSteriaSource(OPTIONS, cancel=cancel).fetch_jobs()


def test_mismatched_reference_is_rejected():
    with pytest.raises(SourceError, match='referencia'):
        parse_detail(DETAIL, parse_listing(LISTING)[1][1])
