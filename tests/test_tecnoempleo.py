import json
from datetime import date
from threading import Event

import httpx
import pytest

from app.database.repositories import JobRepository
from app.services.source_update import update_all_jobs
from app.sources.public_http import HttpOptions
from app.sources.tecnoempleo import TecnoempleoSource


def listing(ident='a', start=1, total=1):
    return f'<a href="https://www.tecnoempleo.com/developer/rf-{ident}">Developer</a><p>{start}-{start} de {total} Ofertas de Empleo</p>'


def detail(ident='a', external=False, education='FP2/Grado Superior'):
    data = dict(title='Developer junior', hiringOrganization={'name': 'Empresa ejemplo'},
                datePosted=date.today().isoformat(), jobLocationType='TELECOMMUTE',
                jobLocation={'address': {'addressCountry': 'ES'}},
                applicantLocationRequirements={'name': 'Spain'})
    data['@type'] = 'JobPosting'
    script = '' if external else '<script type="application/ld+json">' + json.dumps(data) + '</script>'
    return (f'<link rel="canonical" href="https://www.tecnoempleo.com/developer/rf-{ident}">'
            + script + f'<div><div><h1 itemprop="title">Developer junior</h1></div>Empresa ejemplo'
            f'<span class="bg-primary-soft">{date.today():%d/%m/%Y}</span></div>'
            '<div itemprop="description">Desarrollo de aplicaciones Java y SQL. Sin experiencia.</div>'
            f'<p>Formación Mínima: {education}</p>'
            '<li class="list-item"><span class="float-end">Sin experiencia</span><span class="d-inline-block">Experiencia</span></li>'
            '<li class="list-item"><span class="float-end">100% En remoto</span><span class="d-inline-block">Ubicación</span></li>')


@pytest.mark.parametrize('external', [False, True])
def test_public_detail_preserves_requirements_without_inventing_remote_country(external):
    job = TecnoempleoSource().parse_detail(detail(external=external), 'a', 'https://www.tecnoempleo.com/developer/rf-a')
    assert job.company == 'Empresa ejemplo' and job.remote
    assert job.experience_level == 'Sin experiencia' and job.study_area == 'FP2/Grado Superior'
    assert job.location == (None if external else 'España')
    assert job.published_date == date.today()


def test_pagination_existing_pipeline_filters_and_manual_state(db):
    calls = []
    def handler(request):
        calls.append(request.url)
        if '/rf-' in request.url.path:
            ident = request.url.path[-1]
            return httpx.Response(200, text=detail(ident, education='Grado universitario obligatorio' if ident == 'b' else 'FP2/Grado Superior'))
        page = request.url.params.get('pagina', '1')
        if page == '2':
            assert request.url.params['pr'] == ',274,'
        return httpx.Response(200, text=listing('a' if page == '1' else 'b', int(page), 2))
    source = TecnoempleoSource(HttpOptions(delay=0), transport=httpx.MockTransport(handler))
    result = update_all_jobs(db, Event(), lambda m: None, sources=[source])
    assert result['errors'] == 0 and result['new_jobs'] == 2 and len(calls) == 4
    repo = JobRepository(db)
    jobs = {j['external_id']: j for j in repo.get_all_jobs()}
    assert not jobs['a']['excluded'] and jobs['b']['excluded']
    repo.update_job_status(jobs['a']['id'], 'CV enviado')
    result = update_all_jobs(db, Event(), lambda m: None, sources=[source])
    assert result['new_jobs'] == 0
    assert repo.get_job_by_id(jobs['a']['id'])['status'] == 'CV enviado'


@pytest.mark.parametrize('failure', ['403', 'partial', 'repeat', 'detail'])
def test_incomplete_scan_fails_without_importing(db, failure):
    def handler(request):
        if failure == '403':
            return httpx.Response(403)
        if '/rf-' in request.url.path:
            return httpx.Response(200, text='<h1>Acceso candidatos</h1>')
        page = int(request.url.params.get('pagina', '1'))
        html = listing('a', page, 2 if failure in ('partial', 'repeat') else 1)
        if failure == 'partial' and page == 2:
            html = '<p>2-2 de 2 Ofertas de Empleo</p>'
        return httpx.Response(200, text=html)
    source = TecnoempleoSource(HttpOptions(delay=0, retries=0), transport=httpx.MockTransport(handler))
    result = update_all_jobs(db, Event(), lambda m: None, sources=[source])
    assert result['errors'] == 1 and JobRepository(db).get_all_jobs() == []


def test_removed_detail_is_skipped_but_other_errors_are_not():
    for status in (404, 410, 403, 500):
        def handler(request):
            return httpx.Response(status) if '/rf-' in request.url.path else httpx.Response(200, text=listing())
        source = TecnoempleoSource(HttpOptions(delay=0, retries=0), transport=httpx.MockTransport(handler))
        if status in (404, 410):
            scan = source.fetch_jobs()
            assert scan.complete and scan.jobs == () and scan.total_found == 0
        else:
            from app.sources.base import SourceError
            with pytest.raises(SourceError):
                source.fetch_jobs()


def test_explicit_confidential_employer_is_not_invented():
    html = detail(external=True).replace('</div>Empresa ejemplo', '</div>') + '<p>Oferta Ciega</p>'
    job = TecnoempleoSource().parse_detail(html, 'a', 'https://www.tecnoempleo.com/developer/rf-a')
    assert job.company == 'Empresa confidencial (Tecnoempleo)'
