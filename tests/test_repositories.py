import pytest
from app.database.db import Database
from app.database.repositories import CompanyRepository, JobRepository
from app.services.seed_data import seed_database


def test_insert_company_and_job(db):
    companies, jobs = CompanyRepository(db), JobRepository(db)
    company_id = companies.add('Test')
    job_id = jobs.add(external_id='1', title='Developer', company_id=company_id,
                      location='Sevilla', modality='Remoto', score=90)
    assert jobs.get_job_by_id(job_id)['company'] == 'Test'
    assert companies.get_companies()[0]['job_count'] == 1
    assert len(jobs.get_jobs_by_company(company_id)) == 1
    companies.set_enabled(company_id, False)
    assert companies.get_companies()[0]['enabled'] == 0


def test_status_persists(db):
    seed_database(db)
    repo = JobRepository(db)
    job_id = repo.get_all_jobs()[0]['id']
    repo.update_job_status(job_id, 'CV enviado')
    reopened = JobRepository(Database(db.path))
    assert reopened.get_job_by_id(job_id)['status'] == 'CV enviado'
    assert reopened.get_job_by_id(job_id)['is_new'] == 0
    with pytest.raises(ValueError):
        repo.update_job_status(job_id, 'Entrevista')


def test_statistics_and_top(db):
    seed_database(db)
    repo = JobRepository(db)
    assert repo.get_dashboard_stats() == dict(total=18,nuevas=18,prioritarias=4,interesantes=5,revisar=4,baja=5)
    assert [j['score'] for j in repo.get_top_jobs()] == [98,94,91,90,89]
    repo.update_job_status(repo.get_top_jobs()[0]['id'], 'Descartada')
    assert repo.get_dashboard_stats(False)['total'] == 17
    assert len(repo.get_all_jobs(show_discarded=False)) == 17
