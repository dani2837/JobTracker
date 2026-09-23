from PySide6.QtTest import QTest
import time
from app.services.scoring.recalculate import recalculate_all_jobs
from app.ui.job_detail import JobDetail
from tests.test_ui import application, window


def wait_finished(window):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        QTest.qWait(10)
        # QTest.qWait puede retener el GIL en Windows; cederlo al motor Python.
        time.sleep(0.01)
        if window.worker is None:
            return
    raise AssertionError('El recálculo no terminó')


def test_scoring_filters_and_detail(window):
    repo = window.jobs.repository
    company_id = window.companies.repository.get_companies()[0]['id']
    repo.add(external_id='score-a', title='Junior Developer', company_id=company_id,
             location='Sevilla', modality='Híbrido', score=None, description='Sin experiencia. FP DAW. Python.')
    repo.add(external_id='score-b', title='Senior Developer', company_id=company_id,
             location='Madrid', modality='Presencial', score=None, description='5 años requeridos.')
    recalculate_all_jobs(window.db)
    window.refresh()
    view = window.jobs
    view.score_filter.setCurrentText('Prioritarias 90+')
    assert view.table.rowCount() == 1
    view.experience_filter.setCurrentText('Sin experiencia')
    assert view.table.rowCount() == 1
    view.role_filter.setCurrentText('QA')
    assert view.table.rowCount() == 0
    view.role_filter.setCurrentText('Desarrollo')
    assert view.table.rowCount() == 1
    view.table.selectRow(0)
    detail = JobDetail(repo, view.current_job()['id'], window)
    assert 'Puntos positivos' in detail.compatibility.toPlainText()
    assert 'Experiencia: 35/35' in detail.compatibility.toPlainText()
    detail.close()
    view.clear_filters()
    count = view.table.rowCount()
    view.show_excluded.setChecked(True)
    assert view.table.rowCount() > count
    view.score_filter.setCurrentText('Excluidas')
    assert view.table.rowCount() >= 1
    view.table.selectRow(0)
    assert view.current_job()['excluded']
    assert int(window.dashboard.values['excluded'].text()) >= 1
    assert all(not job['excluded'] for job in repo.get_top_jobs())


def test_recalculate_button_is_local(window, monkeypatch):
    monkeypatch.setattr('httpx.Client.get', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('Red no permitida')))
    window.jobs.recalculate_button.click()
    assert not window.jobs.update_button.isEnabled()
    wait_finished(window)
    assert all(job['score_details'] for job in window.jobs.repository.get_all_jobs())
    assert 'Sin consultar Internet' in window.jobs.update_status.text()
    assert window.jobs.recalculate_button.isEnabled()


def test_exclusion_is_prominent_without_positive_percentage(window):
    from PySide6.QtWidgets import QLabel
    repo = window.jobs.repository
    repo.add(external_id='strict-location', title='Junior Developer', company_id=1,
             location='Madrid', modality=None, score=81, description='Sin experiencia. FP DAW.')
    recalculate_all_jobs(window.db)
    job = next(j for j in repo.get_all_jobs() if j['external_id'] == 'strict-location')
    detail = JobDetail(repo, job['id'], window)
    assert any(label.text().startswith('EXCLUIDA\n') for label in detail.findChildren(QLabel))
    text = detail.compatibility.toPlainText()
    assert text.startswith('EXCLUIDA\nMotivos:') and '81/100' not in text
    assert 'Ubicación no compatible o no confirmada' in text
    detail.close()
