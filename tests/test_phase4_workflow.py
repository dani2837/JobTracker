import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from threading import Event
import pytest
from app.database.db import Database
from app.database.repositories import CompanyRepository, JobRepository, SourceRunRepository
from app.services.seed_data import seed_database
from app.services.source_configuration import configure_sources, GUADALTEL_URL
from app.services.source_update import update_all_jobs
from app.services.job_importer import JobImporter
from app.sources.base import ScanResult, SourceError
from app.sources.izertis import IzertisSource
from app.sources.deloitte import DeloitteSource
from tests.test_phase4_sources import sample


def memory(factory, *, ident='123', location='Sevilla'):
    source = factory()
    row = replace(sample(source),external_id=ident,location=location,published_date=None)
    source.fetch_jobs = lambda: ScanResult((row,),1,1,True)
    return source


def test_failure_is_independent_and_preserves_previous_active_jobs(db):
    seed_database(db)
    first,second = memory(IzertisSource),memory(DeloitteSource)
    JobImporter(db,first).run()
    before=next(j for j in JobRepository(db).get_all_jobs() if not j['is_test_data'])
    first.fetch_jobs=lambda: (_ for _ in ()).throw(SourceError('HTTP simulado'))
    messages=[]
    result=update_all_jobs(db,Event(),messages.append,sources=[first,second])
    assert result['errors']==1 and result['new_jobs']==1
    assert result['sources'][1]['success']
    assert JobRepository(db).get_job_by_id(before['id']) == before
    assert [r['success'] for r in SourceRunRepository(db).get_runs()][:2] == [1,0]


def test_source_id_collision_is_not_a_duplicate(db):
    seed_database(db)
    for factory in (IzertisSource,DeloitteSource): JobImporter(db,memory(factory)).run()
    real=[j for j in JobRepository(db).get_all_jobs() if not j['is_test_data']]
    assert len(real)==2 and real[0]['external_id']==real[1]['external_id']=='123'
    assert real[0]['company_id']!=real[1]['company_id']


def test_missing_reference_uses_conservative_fallback(db):
    seed_database(db)
    source=memory(DeloitteSource,ident='')
    assert JobImporter(db,source).run()['new_jobs']==1
    assert JobImporter(db,source).run()['new_jobs']==0
    assert next(j for j in JobRepository(db).get_all_jobs() if not j['is_test_data'])['external_id'].startswith('fallback-')


def test_spontaneous_configuration_and_persistence(db):
    seed_database(db);configure_sources(db)
    repo=CompanyRepository(db)
    company=next(c for c in repo.get_companies() if c['name']=='Guadaltel')
    assert company['accepts_spontaneous_application']==1
    assert company['spontaneous_application_url']==GUADALTEL_URL
    assert company['spontaneous_application_status']=='No enviada' and company['spontaneous_application_date'] is None
    repo.save_spontaneous_application(company['id'],'CV enviado','Contactar más adelante')
    sent=next(c for c in repo.get_companies() if c['id']==company['id'])
    assert sent['spontaneous_application_date'] and sent['notes']=='Contactar más adelante'
    repo.set_enabled(company['id'],False)
    reopened=Database(db.path);reopened.initialize();configure_sources(reopened)
    persisted=next(c for c in CompanyRepository(reopened).get_companies() if c['id']==company['id'])
    assert persisted=={**sent,'enabled':0}
    with pytest.raises(ValueError): repo.save_spontaneous_application(company['id'],'Enviando automáticamente','')


def test_disabled_source_is_not_requested(db):
    seed_database(db)
    source=memory(IzertisSource)
    repo=CompanyRepository(db)
    repo.set_enabled(next(c['id'] for c in repo.get_companies() if c['name']=='Izertis'),False)
    source.fetch_jobs=lambda: pytest.fail('Fuente desactivada consultada')
    result=update_all_jobs(db,Event(),lambda m:None,sources=[source])
    assert result['sources'][0]['skipped'] and result['errors']==0


def test_phase4_migration_preserves_ids_and_manual_data(tmp_path):
    path=tmp_path/'legacy.db'
    with sqlite3.connect(path) as connection:
        connection.executescript((Path(__file__).parent/'fixtures/phase3_schema.sql').read_text(encoding='utf-8'))
        connection.execute("INSERT INTO companies(id,name) VALUES (8,'Indra / Minsait')")
        connection.execute("""INSERT INTO jobs(id,external_id,title,company_id,status,is_new,score,classification,excluded,
            score_details,source_name,discovered_date) VALUES(99,'official','Developer',8,'Inscrito',0,0,'Excluida',1,'{}','Indra / Minsait','2026-08-10')""")
        connection.execute("INSERT INTO source_runs(source,success,total_found) VALUES('Indra / Minsait',1,10)")
    db=Database(path);db.initialize()
    original=JobRepository(db).get_job_by_id(99)
    assert path.with_name(path.name+'.pre-phase4.bak').exists()
    assert original['status']=='Inscrito' and original['discovered_date']=='2026-08-10' and original['score_details']=='{}'
    db.initialize()
    assert JobRepository(db).get_job_by_id(99)==original
    assert SourceRunRepository(db).get_runs()[0]['total_found']==10
    with db.connect() as connection:
        assert not connection.execute('PRAGMA foreign_key_check').fetchall()
        assert connection.execute("SELECT value FROM metadata WHERE key='sources_schema_version'").fetchone()[0]=='4'
