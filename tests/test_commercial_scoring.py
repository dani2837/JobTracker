import pytest
from app.services.scoring.engine import ScoringEngine


@pytest.mark.parametrize('title', ['Sales Executive Renewable Energy', 'Sales', 'Account Manager',
    'Business Development Manager', 'Comercial', 'Software Sales Engineer'])
def test_commercial_titles_are_excluded_even_at_software_company(title):
    result=ScoringEngine().evaluate({'title':title,'location':'Sevilla',
        'description':'We develop software and cloud solutions. Sell products, manage accounts and meet sales targets. Use Salesforce CRM and Python reports.'})
    assert result.excluded and result.score==0
    assert 'role' in result.facts['exclusion_categories']


@pytest.mark.parametrize('title,description',[
    ('Technical Account Manager','Responsibilities:\nDevelop backend APIs in Python.\nConfigure Linux servers and networks.'),
    ('Técnico comercial','Funciones:\nDesarrollar aplicaciones en Java.\nAdministrar servidores Linux.')])
def test_real_technical_duties_allow_commercial_title(title,description):
    result=ScoringEngine().evaluate({'title':title,'location':'Sevilla','description':description})
    assert not result.excluded and result.facts['role_kind']!='non_it_sales'


def test_salesforce_developer_is_not_sales():
    result=ScoringEngine().evaluate({'title':'Salesforce Developer','location':'Sevilla'})
    assert not result.excluded and result.facts['role_kind']=='development'
