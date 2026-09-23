import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from threading import Event
import pytest
from app.database.db import Database
from app.database.repositories import JobRepository, SourceRunRepository
from app.services.job_importer import JobImporter
from app.services.scoring.engine import ScoringEngine
from app.services.scoring.recalculate import recalculate_all_jobs
from app.services.seed_data import seed_database
from app.sources.base import ScanCancelled
from tests.test_importer import MemorySource, real_job


def test_phase2_migration_preserves_everything(tmp_path):
    path = tmp_path / 'phase2.db'
    with sqlite3.connect(path) as connection:
        connection.executescript((Path(__file__).parent/'fixtures/phase2_schema.sql').read_text(encoding='utf-8'))
        connection.execute("INSERT INTO companies(id,name) VALUES (7,'Sopra Steria')")
        connection.execute("""INSERT INTO jobs(external_id,title,company_id,score,status,is_new,
            discovered_date,source_name,is_test_data) VALUES ('real','Developer',7,NULL,'CV enviado',0,'2026-01-01','Sopra Steria',0)""")
        connection.execute("INSERT INTO source_runs(source,success,total_found) VALUES ('Sopra Steria',1,112)")
    db = Database(path)
    db.initialize()
    assert path.with_name(path.name+'.pre-phase3.bak').exists()
    before = JobRepository(db).get_all_jobs()[0]
    db.initialize()
    assert JobRepository(db).get_all_jobs()[0] == before
    assert before['status'] == 'CV enviado' and before['discovered_date'] == '2026-01-01'
    assert SourceRunRepository(db).get_runs()[0]['total_found'] == 112
    with db.connect() as connection:
        assert connection.execute("SELECT value FROM metadata WHERE key='scoring_schema_version'").fetchone()[0] == '3'
        assert not connection.execute('PRAGMA foreign_key_check').fetchall()


def test_recalculate_persists_and_preserves_user_fields(db):
    seed_database(db)
    repo = JobRepository(db)
    repo.update_job_status(1, 'Me interesa')
    before = {j['id']: j for j in repo.get_all_jobs()}
    result = recalculate_all_jobs(db)
    assert result['processed'] == 18
    after = JobRepository(Database(db.path)).get_all_jobs()
    for row in after:
        for key in ('status','is_new','discovered_date','last_seen','updated_at','created_at','is_test_data'):
            assert row[key] == before[row['id']][key]
        details = json.loads(row['score_details'])
        assert details['score'] == row['score']
        assert details['score_breakdown']
    recalculate_all_jobs(db)
    assert {j['id']:j['score'] for j in repo.get_all_jobs()} == {j['id']:j['score'] for j in after}
    assert recalculate_all_jobs(db, only_unscored=True)['processed'] == 0


def test_scoring_in_import_transaction(db, real_job):
    seed_database(db)
    example = replace(real_job, title='Junior Developer', description='Sin experiencia. FP DAW. Python.',
                      location='Sevilla', modality='Híbrido', experience_level='0-2 años')
    source = MemorySource([example])
    JobImporter(db, source, scorer=ScoringEngine()).run()
    repo = JobRepository(db)
    saved = next(j for j in repo.get_all_jobs() if j['external_id'] == example.external_id)
    assert saved['score'] >= 90 and not saved['excluded']
    repo.update_job_status(saved['id'], 'CV enviado')
    source.jobs = (replace(example, description='Mínimo 3 años de experiencia.'),)
    result = JobImporter(db, source, scorer=ScoringEngine()).run()
    updated = repo.get_job_by_id(saved['id'])
    assert updated['excluded'] and updated['score'] == 0
    assert updated['status'] == 'CV enviado' and updated['discovered_date'] == saved['discovered_date']
    assert result['new_jobs'] == 0
    assert len(repo.get_all_jobs()) == 19
    assert updated['id'] not in [j['id'] for j in repo.get_top_jobs()]


def test_actual_update_service_injects_scorer(db, real_job, monkeypatch):
    seed_database(db)
    from app.services.source_update import update_jobs
    monkeypatch.setattr('app.services.source_update.SopraSteriaSource', lambda **kwargs: MemorySource([real_job]))
    update_jobs(db, Event(), lambda message: None)
    real = next(j for j in JobRepository(db).get_all_jobs() if not j['is_test_data'])
    assert real['score_details'] and real['score'] is not None


def test_recalculate_failure_and_cancel_leave_scores_unchanged(db, monkeypatch):
    seed_database(db)
    before = JobRepository(db).get_all_jobs()
    cancel = Event()
    cancel.set()
    with pytest.raises(ScanCancelled):
        recalculate_all_jobs(db, cancel=cancel)
    assert JobRepository(db).get_all_jobs() == before
    original = ScoringEngine.evaluate
    def failing(self, job):
        if job['id'] == 3:
            raise ValueError('Regla incorrecta')
        return original(self, job)
    monkeypatch.setattr(ScoringEngine, 'evaluate', failing)
    with pytest.raises(ValueError):
        recalculate_all_jobs(db)
    assert JobRepository(db).get_all_jobs() == before


def test_profile_recalculation_changes_score(db):
    from app.config.profile import load_profile
    seed_database(db)
    recalculate_all_jobs(db)
    before = JobRepository(db).get_job_by_id(1)
    profile = load_profile()
    profile['locations'] = ['Madrid']
    recalculate_all_jobs(db, profile=profile)
    after = JobRepository(db).get_job_by_id(1)
    assert after['excluded'] and not before['excluded']
    assert json.loads(before['score_details'])['profile_hash'] != json.loads(after['score_details'])['profile_hash']


def test_import_scoring_failure_rolls_back(db, real_job):
    seed_database(db)
    before = JobRepository(db).get_all_jobs()
    class BrokenEngine:
        def evaluate(self, job):
            raise ValueError('Fallo de scoring simulado')
    with pytest.raises(ValueError):
        JobImporter(db, MemorySource([real_job]), scorer=BrokenEngine()).run()
    assert JobRepository(db).get_all_jobs() == before
    assert SourceRunRepository(db).get_runs()[0]['success'] == 0
