from dataclasses import replace
import json
from datetime import date
from pathlib import Path
from threading import Event
import httpx
import pytest
from bs4 import BeautifulSoup
from app.sources.base import ScanResult, SourceError, ScanCancelled
from app.sources.public_http import HttpOptions, parse_date, official_url
from app.sources.izertis import IzertisSource, parse_listing as iz_listing, parse_detail as iz_detail
from app.sources.indra_minsait import IndraMinsaitSource
from app.sources.deloitte import DeloitteSource
from app.sources.successfactors import parse_listing as sf_listing, parse_detail as sf_detail
from app.services.job_importer import JobImporter
from app.services.scoring.engine import ScoringEngine
from app.services.seed_data import seed_database
from app.database.repositories import JobRepository, CompanyRepository, SourceRunRepository

FIXTURES = Path(__file__).parent/'fixtures/phase4'
OPTIONS = HttpOptions(delay=0, retries=0)


def fixture(name):
    return (FIXTURES/name).read_text(encoding='utf-8')


def sample(source):
    if source.name == 'Izertis':
        row = iz_listing(fixture('izertis_listing.html'))[0][0]
        return iz_detail(fixture('izertis_detail.html'), row)
    listing = 'indra_spain_listing.html' if source.name == 'Indra / Minsait' else 'deloitte_listing.html'
    detail = 'minsait_detail.html' if source.name == 'Indra / Minsait' else 'deloitte_detail.html'
    return sf_detail(fixture(detail), sf_listing(fixture(listing), source.url)[0][0], source)


def test_izertis_real_format():
    rows, next_url = iz_listing(fixture('izertis_listing.html'))
    assert len(rows) == 12 and next_url.endswith('page=2')
    result = iz_detail(fixture('izertis_detail.html'), rows[0])
    assert result.external_id == 'trabaja-con-nosotros-as-espana'
    assert result.title == 'Trabaja con nosotros/as (España)' and result.general_application
    assert result.modality == 'Híbrido' and result.location is None
    assert result.department == 'Informática' and result.category == 'Informática y telecomunicaciones'
    assert result.employment_type == 'Completa' and result.published_date is None
    assert result.description and result.url.startswith('https://jobs.izertis.com/jobs/')
    assert ScoringEngine().evaluate(result.__dict__).excluded


@pytest.mark.parametrize('factory', [IndraMinsaitSource, DeloitteSource])
def test_successfactors_real_format(factory):
    source = factory()
    result = sample(source)
    assert result.external_id.isdigit() and result.company == source.company
    assert result.description and result.published_date and result.url.startswith('https://')
    if source.name == 'Indra / Minsait':
        assert result.modality == 'Remoto' and result.location == 'ES'
        assert result.experience_level == 'Más de 2 años de experiencia'
        assert result.professional_profile is None
    else:
        assert result.study_area == 'Informática, Industriales  y Telecomunicaciones'
        assert result.experience_level == 'Profesionales con experiencia'
        assert result.location == 'Madrid, España'
        assert result.service_line is None


@pytest.mark.parametrize('factory', [IzertisSource, IndraMinsaitSource, DeloitteSource])
def test_two_pages_details_and_loop_protection(factory):
    source = factory(OPTIONS)
    if source.name == 'Izertis':
        soup = BeautifulSoup(fixture('izertis_listing.html'),'html.parser')
        cards = soup.select('a.job-card')[:2]
        pages = [str(cards[0])+'<ul class="pagination"><a class="next" href="/jobs?page=2">Siguiente</a></ul>', str(cards[1])]
        detail = fixture('izertis_detail.html')
    else:
        file = 'indra_spain_listing.html' if source.name == 'Indra / Minsait' else 'deloitte_listing.html'
        links = BeautifulSoup(fixture(file),'html.parser').select('a.jobTitle-link')
        unique = list({a['href']: str(a) for a in links}.values())[:2]
        pages = ['<p class="paginationLabel">Resultados 1 – 1 de 2</p>'+unique[0],
                 '<p class="paginationLabel">Resultados 2 – 2 de 2</p>'+unique[1]]
        detail = fixture('minsait_detail.html' if source.name == 'Indra / Minsait' else 'deloitte_detail.html')
    requests = []
    def handle(request):
        requests.append(str(request.url))
        if '/job/' in request.url.path or (source.name=='Izertis' and request.url.path.startswith('/jobs/')):
            return httpx.Response(200,text=detail)
        return httpx.Response(200,text=pages[0 if len(requests)==1 else 1])
    source.transport = httpx.MockTransport(handle)
    scan = source.fetch_jobs()
    assert scan.complete and scan.pages == 2 and scan.total_found == 2 and len(requests) == 4
    source.transport = httpx.MockTransport(lambda request: httpx.Response(200,text=pages[0]))
    with pytest.raises(SourceError):
        source.fetch_jobs()


@pytest.mark.parametrize('factory', [IzertisSource, IndraMinsaitSource, DeloitteSource])
@pytest.mark.parametrize('status', [403,404,429,503])
def test_http_failure_does_not_return_partial_scan(factory,status):
    source = factory(OPTIONS,transport=httpx.MockTransport(lambda request: httpx.Response(status)))
    with pytest.raises(SourceError):
        source.fetch_jobs()


@pytest.mark.parametrize('factory', [IzertisSource, IndraMinsaitSource, DeloitteSource])
def test_cancel_before_network(factory):
    cancel = Event(); cancel.set()
    source = factory(OPTIONS,cancel=cancel,transport=httpx.MockTransport(lambda request: pytest.fail('HTTP tras cancelación')))
    with pytest.raises(ScanCancelled):
        source.fetch_jobs()


@pytest.mark.parametrize('factory', [IzertisSource, IndraMinsaitSource, DeloitteSource])
def test_import_twice_with_scoring_preserves_state_and_extra_fields(db,factory):
    seed_database(db)
    source = factory()
    original = sample(source)
    source.fetch_jobs = lambda: ScanResult((original,),1,1,True)
    importer = JobImporter(db,source,scorer=ScoringEngine(),today=date(2026,9,7))
    assert importer.run()['new_jobs'] == 1
    repo = JobRepository(db)
    before = next(j for j in repo.get_all_jobs() if not j['is_test_data'])
    repo.update_job_status(before['id'],'Inscrito')
    assert importer.run()['new_jobs'] == 0
    after = repo.get_job_by_id(before['id'])
    assert after['status']=='Inscrito' and after['discovered_date']==before['discovered_date']
    assert after['score_details']==before['score_details']
    assert after['professional_profile']==original.professional_profile
    assert after['service_line']==original.service_line and after['study_area']==original.study_area
    assert len(CompanyRepository(db).get_companies())==15
    assert len(SourceRunRepository(db).get_runs())==2


def test_indra_fields_preserve_junior_training_and_country():
    source = IndraMinsaitSource()
    html = fixture('minsait_detail.html').replace('Más de 2 años','Menos de 2 años')
    html = html.replace('itemprop="description"', 'itemprop="description"')
    soup = BeautifulSoup(html,'html.parser')
    soup.select_one('[itemprop="description"]').clear()
    soup.select_one('[itemprop="description"]').append('Requisitos\nFP DAW, DAM o ASIR. CFGS. Sin experiencia.')
    soup.select_one('[data-careersite-propertyid="customfield1"]').string = 'Junior'
    result = sf_detail(str(soup),{'external_id':'123','url':source.url,'study_area':None},source)
    assert result.professional_profile == 'Junior' and 'DAM' in result.description
    engine = ScoringEngine()
    scored = engine.evaluate(result.__dict__)
    assert 'experience' not in scored.facts['exclusion_categories'] and 'education' not in scored.facts['exclusion_categories']
    assert 'location' in scored.facts['exclusion_categories']
    assert not engine.evaluate({**result.__dict__,'description':result.description+'\n100% remoto desde España.'}).excluded


@pytest.mark.parametrize('place,excluded', [('Sevilla',False),('Madrid',True),('ES',True),('España',True),(None,True)])
def test_new_source_location_stays_strict(place,excluded):
    assert ScoringEngine().evaluate({'title':'Junior Developer','location':place,'description':'Sin experiencia. FP DAW.'}).excluded is excluded


@pytest.mark.parametrize('text,excluded', [('Menos de 2 años',False),('0-2 años',False),('Mínimo 2 años',True),('Al menos 2 años',True),('3+ años',True)])
def test_experience_below_two_is_not_minimum(text,excluded):
    assert ScoringEngine().evaluate({'title':'Developer','location':'Sevilla','experience_level':text}).excluded is excluded


@pytest.mark.parametrize('title', ['Beca de desarrollo','Prácticas de QA','Internship software'])
def test_internships_are_excluded(title):
    assert 'job_kind' in ScoringEngine().evaluate({'title':title,'location':'Sevilla'}).facts['exclusion_categories']


def test_public_url_and_dates():
    assert parse_date('Mon Sep 07 02:00:00 UTC 2026') == date(2026,9,7)
    assert parse_date(None) is None
    with pytest.raises(SourceError): parse_date('fecha imposible')
    with pytest.raises(SourceError): official_url(DeloitteSource.url,'https://example.org/private')


def test_explicit_remote_in_title_is_evidence_but_country_code_is_not():
    engine=ScoringEngine()
    job={'title':'Junior Developer — España 100% remoto','location':'ES','modality':'Indiferente',
         'description':'Sin experiencia. FP DAW.'}
    assert not engine.evaluate(job).excluded
    assert engine.evaluate({**job,'title':'Junior Developer — Remoto'}).excluded


@pytest.mark.parametrize('case',json.loads(fixture('scoring_regressions.json')),ids=lambda c:c['job']['external_id'])
def test_all_initial_compatible_offers_manually_audited(case):
    result=ScoringEngine().evaluate(case['job'])
    assert result.excluded is case['expected_excluded']
    if case['expected_excluded']:
        assert 'education' in result.facts['exclusion_categories']
    else:
        assert result.score==61 and result.classification=='Revisar'


def test_optional_graduate_degree_is_not_obligatory():
    result=ScoringEngine().evaluate({'title':'Junior Developer','location':'Sevilla',
        'description':'¿Cómo te imaginamos?\nGrado universitario valorable.\nFP o formación equivalente.'})
    assert not result.excluded


@pytest.mark.parametrize('factory,file',[(IzertisSource,'izertis_listing.html'),
    (IndraMinsaitSource,'indra_spain_listing.html'),(DeloitteSource,'deloitte_listing.html')])
def test_page_and_request_limits_preserve_complete_scan_requirement(factory,file):
    transport=httpx.MockTransport(lambda request:httpx.Response(200,text=fixture(file)))
    with pytest.raises(SourceError,match='MAX_PAGES'):
        factory(HttpOptions(max_pages=1,delay=0,retries=0),transport=transport).fetch_jobs()
    with pytest.raises(SourceError,match='MAX_REQUESTS'):
        factory(HttpOptions(max_requests=1,delay=0,retries=0),transport=transport).fetch_jobs()


@pytest.mark.parametrize('factory',[IzertisSource,IndraMinsaitSource,DeloitteSource])
def test_timeout_is_reported(factory):
    def timeout(request):
        raise httpx.ReadTimeout('Timeout de prueba',request=request)
    with pytest.raises(SourceError,match='conectar'):
        factory(OPTIONS,transport=httpx.MockTransport(timeout)).fetch_jobs()
