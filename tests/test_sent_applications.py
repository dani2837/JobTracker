from PySide6.QtCore import QTimer
from app.config.settings import Settings
from app.database.db import Database
from app.ui.job_detail import JobDetail
from app.ui.main_window import MainWindow
from tests.test_ui import application, window


def test_cv_sent_tab_restart_detail_and_discard(window, application, monkeypatch):
    repo = window.jobs.repository
    job_id = repo.get_all_jobs()[0]['id']
    with window.db.connect() as c:
        c.execute("UPDATE jobs SET is_test_data=0,url='https://example.com/job',excluded=1,is_active=0 WHERE id=?", (job_id,))
    dialog = JobDetail(repo, job_id, window)
    dialog.changed.connect(window.refresh)
    dialog.cv_sent_button.click()
    assert dialog.status.currentText() == 'CV enviado'
    assert not dialog.cv_sent_button.isEnabled()
    assert not repo.get_job_by_id(job_id)['is_new']
    assert window.sent_applications.table.rowCount() == 1
    dialog.close()
    reopened = MainWindow(Database(window.db.path), Settings(window.settings.path))
    reopened.show()
    try:
        reopened.navigation.setCurrentRow(4)
        tab = reopened.sent_applications
        assert reopened.pages.currentWidget() is tab and tab.table.rowCount() == 1
        tab.table.selectRow(0)
        urls = []
        monkeypatch.setattr('app.ui.common.QDesktopServices.openUrl', lambda url: urls.append(url.toString()) or True)
        tab.open_button.click()
        assert urls == ['https://example.com/job']
        opened = []
        def close_detail():
            detail = application.activeModalWidget()
            opened.append(detail.job['id'])
            detail.accept()
        QTimer.singleShot(0, close_detail)
        tab.detail_button.click()
        assert opened == [job_id]
        tab.discard_button.click()
        assert tab.table.rowCount() == 0 and not tab.discard_button.isEnabled()
        assert repo.get_job_by_id(job_id)['status'] == 'Descartada'
        assert len(repo.get_all_jobs()) == 18
    finally:
        reopened.close()


def test_discard_from_offer_detail_and_restore_status(window):
    repo = window.jobs.repository
    job_id = repo.get_all_jobs()[0]['id']
    dialog = JobDetail(repo, job_id, window)
    dialog.discard_button.click()
    assert repo.get_job_by_id(job_id)['status'] == 'Descartada'
    assert not dialog.discard_button.isEnabled() and not dialog.seen_button.isEnabled()
    dialog.status.setCurrentText('Nueva')
    assert dialog.discard_button.isEnabled()
    assert repo.get_job_by_id(job_id)['status'] == 'Nueva'
    dialog.close()
