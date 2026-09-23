from app.config.settings import Settings
from app.database.db import Database
from app.database.repositories import JobRepository, CompanyRepository
from app.ui.main_window import MainWindow
from app.ui.job_detail import JobDetail
from tests.test_ui import application
from tests.test_importer import real_job, importer


def test_seen_flag_survives_import_without_changing_manual_status(db, real_job):
    CompanyRepository(db).add(real_job.company)
    importer(db, [real_job]).run()
    repo = JobRepository(db)
    job = repo.get_all_jobs()[0]
    repo.mark_seen(job['id'])
    importer(db, [real_job]).run()
    saved = repo.get_job_by_id(job['id'])
    assert saved['status'] == 'Nueva' and not saved['is_new']


def test_daily_start_seen_state_and_restart(db, tmp_path, application):
    repo = JobRepository(db)
    company = CompanyRepository(db).add('Empresa')
    ids = [repo.add(external_id=str(i), title='Desarrollador Python', company_id=company,
                   location='Sevilla', modality='Remoto', score=70, url='https://example.com/job') for i in range(3)]
    with db.connect() as c:
        c.execute("UPDATE jobs SET source_name='InfoJobs'")
        c.execute('UPDATE jobs SET excluded=1 WHERE id=?', (ids[1],))
        c.execute('UPDATE jobs SET is_test_data=1 WHERE id=?', (ids[2],))
    settings = Settings(tmp_path / 'daily-settings.json')
    settings.set('confirm_close', False)
    window = MainWindow(db, settings)
    try:
        view = window.jobs
        assert window.pages.currentIndex() == 1 and view.only_new.isChecked()
        assert not view.show_excluded.isChecked() and not view.show_test.isChecked()
        assert view.table.rowCount() == 1
        assert '2 descubiertas' in view.daily_summary.text() and '1 no excluidas' in view.daily_summary.text()
        with db.connect() as c:
            c.execute('UPDATE jobs SET is_active=0 WHERE id=?', (ids[0],))
        window.refresh()
        assert '1 nuevas por revisar' in view.daily_summary.text() and view.table.rowCount() == 1
        assert view.source_filter.findText('InfoJobs') >= 0
        view.table.selectRow(0)
        view.seen_button.click()
        assert repo.get_job_by_id(ids[0])['status'] == 'Nueva'
        assert not repo.get_job_by_id(ids[0])['is_new'] and view.table.rowCount() == 0
        view.only_new.setChecked(False)
        view.table.selectRow(0)
        view.status.setCurrentText('Me interesa')
        detail = JobDetail(repo, ids[0], window)
        assert not detail.seen_button.isEnabled()
        detail.status.setCurrentText('Nueva')
        assert detail.seen_button.isEnabled()
        detail.seen_button.click()
        detail.close()
    finally:
        window.close()
    restarted = MainWindow(Database(db.path), Settings(settings.path))
    try:
        assert restarted.jobs.table.rowCount() == 0
        assert not restarted.jobs.repository.get_job_by_id(ids[0])['is_new']
        restarted.jobs.only_new.setChecked(False)
        restarted.jobs.show_excluded.setChecked(True)
        assert restarted.jobs.table.rowCount() == 2
    finally:
        restarted.close()
