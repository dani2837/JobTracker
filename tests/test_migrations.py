from pathlib import Path
import sqlite3
from app.database.db import Database
from app.database.repositories import JobRepository
from app.services.seed_data import seed_database


def test_phase1_migration_preserves_data(tmp_path):
    path = tmp_path / 'legacy.db'
    legacy = (Path(__file__).parent / 'fixtures' / 'phase1_schema.sql').read_text(encoding='utf-8')
    with sqlite3.connect(path) as connection:
        connection.executescript(legacy)
        connection.execute("INSERT INTO companies(id,name) VALUES (7,'Sopra Steria')")
        connection.execute('''INSERT INTO jobs(id,external_id,title,company_id,location,modality,
            description,score,status,is_new,discovered_date) VALUES
            (42,'demo-007','Application Support Junior',7,'Sevilla','Remoto',
            'DATOS DE PRUEBA — oferta ficticia',81,'CV enviado',0,'2025-01-01')''')
    db = Database(path)
    db.initialize()
    repo = JobRepository(db)
    job = repo.get_job_by_id(42)
    assert job['status'] == 'CV enviado' and job['is_new'] == 0
    assert job['discovered_date'] == '2025-01-01' and job['company_id'] == 7
    assert job['is_test_data'] == 1 and job['source_name'] == 'Datos de prueba'
    assert path.with_name(path.name + '.pre-phase2.bak').exists()
    db.initialize()
    assert repo.get_job_by_id(42) == job
    repo.add(external_id='real', title='Real', company_id=7, location=None, modality=None, score=None)
    with db.connect() as connection:
        assert not connection.execute('PRAGMA foreign_key_check').fetchall()
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 2
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='source_runs'").fetchone()


def test_fresh_schema_needs_no_rebuild(db):
    seed_database(db)
    db.initialize()
    assert not db.path.with_name(db.path.name + '.pre-phase2.bak').exists()
    assert all(job['is_test_data'] for job in JobRepository(db).get_all_jobs())
