import json
from dataclasses import replace
from datetime import date
from pathlib import Path
import httpx
import pytest
from app.sources import accenture, ayesa, t_systems
from app.sources.base import ScanResult, SourceError, ScanCancelled
from app.sources.public_http import HttpOptions
from app.services.job_importer import JobImporter
from app.services.seed_data import seed_database
from app.services.source_configuration import configure_sources
from app.database.repositories import JobRepository, CompanyRepository
from app.services.scoring.engine import ScoringEngine

FIX = Path(__file__).parent/'fixtures/phase5'


def fixture(name):
    return (FIX/name).read_text(encoding='utf8')


def test_accenture_real_fields_no_generated_summary_or_invented_date():
    row=json.loads(fixture('accenture.json'))['data'][0]
    row['azureopenaiSummary']='DO NOT USE'
    job=accenture.parse_job(row)
    assert job.external_id=='R00354893' and job.location=='Madrid'
    assert 'Grado en cualquier Ingeniería' in job.description
    assert 'DO NOT USE' not in job.description and job.published_date is None
    assert '0-2 años' in job.experience_level and job.modality=='On-Site'
    assert job.url.startswith('https://www.accenture.com/es-es/careers/jobdetails?id=')


def test_ayesa_real_fields_and_requirements():
    links,next_url=ayesa.parse_listing(fixture('ayesa_listing.html'),ayesa.PORTAL)
    assert len(links)==10 and next_url.endswith('/page/2/')
    job=ayesa.parse_job(fixture('ayesa_detail.html'),links[0])
    assert job.external_id=='26SP.015' and job.location=='Barcelona, España'
    assert job.modality=='Híbrido' and job.employment_type=='Indefinido'
    assert job.published_date==date(2026,9,7) and 'mínima de 10 años' in job.description
    assert 'Subir CV' not in job.description


def test_tsystems_real_fields_and_general_application():
    row=json.loads(fixture('t_systems_detail.json'))
    job=t_systems.parse_job(row,row['id'])
    assert job.location=='Madrid, MD, Spain' and job.remote is False
    assert job.published_date==date(2026,9,2) and job.description
    assert job.experience_level=='Mid-Senior Level'
    row['name']='Únete a nuestra Talent Community'
    assert t_systems.parse_job(row,row['id']).general_application


@pytest.mark.parametrize('factory',[accenture.AccentureSource,ayesa.AyesaSource,t_systems.TSystemsSource])
def test_sources_http_failure_and_cancel(factory):
    source=factory(HttpOptions(delay=0,retries=0),transport=httpx.MockTransport(lambda r:httpx.Response(503)))
    with pytest.raises(SourceError): source.fetch_jobs()
    source.cancel.set()
    with pytest.raises(ScanCancelled): source.fetch_jobs()


def test_accenture_pagination_request_and_changed_total():
    payload=json.loads(fixture('accenture.json'))
    rows=[dict(payload['data'][0],requisitionId=f'R{i}',jobDetailUrl=f'https://www.accenture.com/{{0}}/careers/jobdetails?id=R{i}_es') for i in range(13)]
    calls=[]
    def response(request):
        assert request.method=='POST' and request.url.path=='/api/accenture/elastic/findjobs'
        calls.append(request.content)
        return httpx.Response(200,json={**payload,'data':rows[:12] if len(calls)==1 else rows[12:], 'totalHits':{'total':13,'overMaxHits':'False'}})
    result=accenture.AccentureSource(HttpOptions(delay=0),transport=httpx.MockTransport(response)).fetch_jobs()
    assert result.pages==2 and result.total_found==13
    assert b'name="startIndex"\r\n\r\n12' in calls[1]
    calls.clear()
    with pytest.raises(SourceError,match='MAX_PAGES'):
        accenture.AccentureSource(HttpOptions(delay=0,max_pages=1),transport=httpx.MockTransport(response)).fetch_jobs()


def test_tsystems_pagination_and_identity():
    detail=json.loads(fixture('t_systems_detail.json'))
    def response(request):
        if request.url.query:
            offset=int(request.url.params['offset'])
            rows=[{'id':str(i),'ref':t_systems.API+'/'+str(i)} for i in range(offset,min(offset+100,101))]
            return httpx.Response(200,json={'offset':offset,'totalFound':101,'content':rows})
        reference=request.url.path.split('/')[-1]
        return httpx.Response(200,json={**detail,'id':reference,
            'postingUrl':f'https://jobs.smartrecruiters.com/T-SystemsIberia/{reference}-job'})
    result=t_systems.TSystemsSource(HttpOptions(delay=0),transport=httpx.MockTransport(response)).fetch_jobs()
    assert result.pages==2 and result.total_found==101
    with pytest.raises(SourceError,match='identidad'):t_systems.parse_job(detail,'wrong')


def test_ayesa_loop_and_complete_detail():
    listing=fixture('ayesa_listing.html')
    def response(request):
        return httpx.Response(200,text=listing if '/page/' in request.url.path else fixture('ayesa_detail.html'))
    with pytest.raises(SourceError,match='repetidas'):
        ayesa.AyesaSource(HttpOptions(delay=0),transport=httpx.MockTransport(response)).fetch_jobs()
    single=listing[:listing.index('<a class="next')]
    result=ayesa.AyesaSource(HttpOptions(delay=0),transport=httpx.MockTransport(lambda r:httpx.Response(200,text=single if '/page/' in r.url.path else fixture('ayesa_detail.html')))).fetch_jobs()
    assert result.pages==1 and len(result.jobs)==10


@pytest.mark.parametrize('name',['Accenture','Ayesa','T-Systems'])
def test_import_twice_and_preserve_state(db,name):
    seed_database(db);configure_sources(db)
    row=accenture.parse_job(json.loads(fixture('accenture.json'))['data'][0])
    job=replace(row,source_name=name,company=name,published_date=date.today())
    class Source:
        company=name
        url=job.source_url
        def fetch_jobs(self):return ScanResult((job,),1,1,True)
    source=Source();source.name=name
    assert JobImporter(db,source,scorer=ScoringEngine()).run()['new_jobs']==1
    repo=JobRepository(db);saved=next(j for j in repo.get_all_jobs() if j['source_name']==name)
    repo.update_job_status(saved['id'],'Me interesa')
    result=JobImporter(db,source,scorer=ScoringEngine()).run()
    after=next(j for j in repo.get_all_jobs() if j['id']==saved['id'])
    assert result['new_jobs']==0 and result['updated_jobs']==1 and after['status']=='Me interesa'
    assert after['score_details'] and after['excluded']
    assert len(CompanyRepository(db).get_companies())==15


@pytest.mark.parametrize('parser,args',[
    (accenture.parse_job,({},)),(ayesa.parse_job,('<html>changed</html>',ayesa.PORTAL)),
    (t_systems.parse_job,({},'1'))])
def test_incomplete_details_rejected(parser,args):
    with pytest.raises(SourceError):parser(*args)


def test_accenture_requirements_inside_description():
    job=accenture.parse_job(json.loads(fixture('accenture_inline_requirements.json')))
    assert job.external_id=='R00298038' and 'Scrum' in job.description
    assert 'Barcelona' in job.description
    assert ScoringEngine().evaluate(job.__dict__).excluded


def test_ayesa_legacy_requirements_without_description():
    job=ayesa.parse_job(fixture('ayesa_requirements_only.html'),
        'https://www.ayesa.com/ofertas-trabajo/oferta/ingeniero-a-dise-o-de-tuber-as/25SP.275/')
    assert job.published_date==date(2025,9,22) and 'Mínimo 5 años' in job.description
    assert job.modality is None and ScoringEngine().evaluate(job.__dict__).excluded


def test_tsystems_real_community_has_no_qualifications():
    job=t_systems.parse_job(json.loads(fixture('t_systems_community.json')),'744000141235019')
    assert job.general_application and ScoringEngine().evaluate(job.__dict__).excluded


@pytest.mark.parametrize('index,score,category',[(0,0,'location'),(1,0,'role'),(2,0,'education'),(3,73,None),(4,0,'experience')])
def test_source_requirement_regressions(index,score,category):
    row=json.loads(fixture('scoring_regressions.json'))[index]
    result=ScoringEngine().evaluate(row)
    assert result.score==score and result.excluded==(category is not None)
    if category:assert category in result.facts['exclusion_categories']
    else:
        assert result.classification=='Revisar'
        assert result.penalties['english_high']==7
        assert any('confirmar el nivel' in w for w in result.warnings)
        german=[x for x in result.facts['languages_detected'] if x['language']=='aleman']
        assert not any(x['required'] for x in german)


def test_seville_workplace_not_rejected_as_contradiction():
    row=json.loads(fixture('scoring_regressions.json'))[0]
    row['title']=row['title'].replace('Córdoba','Dos Hermanas')
    row['description']=row['description'].replace('Córdoba','Dos Hermanas')
    assert 'location' not in ScoringEngine().evaluate(row).facts['exclusion_categories']
