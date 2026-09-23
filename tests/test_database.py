import sqlite3
import pytest
from app.database.repositories import CompanyRepository, JobRepository
from app.services.seed_data import seed_database


def test_database_and_tables(db):
    assert db.path.exists()
    with db.connect() as connection:
        names = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {'companies','jobs','metadata'} <= names


def test_seed_idempotent(db):
    seed_database(db)
    repo = JobRepository(db)
    repo.update_job_status(repo.get_all_jobs()[0]['id'], 'Me interesa')
    seed_database(db)
    assert len(CompanyRepository(db).get_companies()) == 15
    assert len(repo.get_all_jobs()) == 18
    assert repo.get_all_jobs()[0]['status'] == 'Me interesa'


def test_foreign_key(db):
    with pytest.raises(sqlite3.IntegrityError):
        JobRepository(db).add(external_id='invalid', title='Test', company_id=999,
                             location='Sevilla', modality='Remoto', score=90)
