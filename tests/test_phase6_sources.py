from pathlib import Path
from datetime import date
import httpx
import pytest
from app.sources.phase6_html import EmergyaSource, IsotrolSource
from app.sources.public_http import HttpOptions
from app.sources.base import SourceError

FIX=Path(__file__).parent/'fixtures/phase6'


def read(name):
    return (FIX/(name+'.html')).read_text(encoding='utf8')


def test_emergya_real_html_fields():
    source=EmergyaSource()
    rows,following=source.parse_listing(read('emergya'))
    assert len(rows)==3 and following is None
    job=source.parse_detail(read('emergya_detail'),rows[0])
    assert job.external_id=='11164' and job.title=='AI/Python Developer'
    assert job.location=='Sevilla, Remoto' and job.experience_level=='Senior'
    assert job.published_date==date(2026,4,10)
    assert 'Python' in job.description and 'Adjunta tu cv' not in job.description


def test_isotrol_real_html_fields():
    source=IsotrolSource()
    rows,following=source.parse_listing(read('isotrol'))
    assert len(rows)==7 and following is None
    row=next(r for r in rows if r['external_id']=='systems-and-network-technician')
    job=source.parse_detail(read('isotrol_detail'),row)
    assert job.location=='Mexico (CDMX)' and job.department=='Sistemas'
    assert job.modality=='Onsite' and job.employment_type=='Full-time'
    assert job.published_date is None and 'at least 2 years' in job.description


@pytest.mark.parametrize('factory',[EmergyaSource,IsotrolSource])
def test_http_failure_does_not_return_partial_scan(factory):
    source=factory(HttpOptions(delay=0,retries=0),transport=httpx.MockTransport(lambda r:httpx.Response(403)))
    with pytest.raises(SourceError):source.fetch_jobs()


@pytest.mark.parametrize('factory,name,next_link',[
    (EmergyaSource,'emergya','<a rel="next" href="?page=1">Next</a>'),
    (IsotrolSource,'isotrol','<a class="w-pagination-next" href="?page=1">Next</a>')])
def test_repeated_page_rejected(factory,name,next_link):
    source=factory(HttpOptions(delay=0),transport=httpx.MockTransport(lambda r:httpx.Response(200,text=read(name)+next_link)))
    with pytest.raises(SourceError,match='repetida'):source.fetch_jobs()
