from threading import Event, get_ident
from dataclasses import replace
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox
from app.ui.job_detail import JobDetail
from app.ui.update_worker import UpdateWorker
from tests.test_ui import application, window
from tests.test_importer import importer, real_job


def test_real_filter_score_detail_and_open(window, real_job, monkeypatch):
    importer(window.db, [real_job]).run()
    window.refresh()
    view = window.jobs
    assert view.table.rowCount() == 19
    view.table.sortItems(0, Qt.SortOrder.DescendingOrder)
    assert view.table.item(0, 0).text() == '98'
    assert view.table.item(18, 0).text() == '—'
    view.source_filter.setCurrentText('Sopra Steria')
    assert view.table.rowCount() == 1
    assert view.table.item(0, 8).text() == 'Sopra Steria'
    view.quick_buttons['90%+'].setChecked(True)
    assert view.table.rowCount() == 0
    view.quick_buttons['90%+'].setChecked(False)
    view.table.selectRow(0)
    assert view.open_button.isEnabled()
    urls = []
    monkeypatch.setattr('app.ui.common.QDesktopServices.openUrl', lambda url: urls.append(url.toString()) or True)
    view.open_button.click()
    detail = JobDetail(view.repository, view.current_job()['id'], window)
    detail.open_button.click()
    assert urls == [real_job.url, real_job.url]
    assert detail.job['experience_level'] == real_job.experience_level
    detail.close()
    view.source_filter.setCurrentText('Datos de prueba')
    assert view.table.rowCount() == 18
    assert '1 reales' in window.dashboard.source_summary.text()
    assert '1 pendientes' in window.dashboard.source_summary.text()


def test_sevilla_filter_with_portal_location(window, real_job):
    importer(window.db, [replace(real_job, location='Sevilla, Spain')]).run()
    window.refresh()
    window.jobs.source_filter.setCurrentText('Sopra Steria')
    window.jobs.quick_buttons['Sevilla'].setChecked(True)
    assert window.jobs.table.rowCount() == 1


def wait_finished(window):
    for _ in range(100):
        QTest.qWait(20)
        if window.worker is None:
            return
    raise AssertionError('El worker no finalizó')


def test_update_runs_off_ui_thread_and_prevents_overlap(window, monkeypatch):
    ticks, threads = [], []
    release = Event()
    def update(db, cancel, progress):
        threads.append(get_ident())
        progress('Leyendo prueba')
        release.wait(1)
        return dict(total_found=0, new_jobs=0, updated_jobs=0, excluded_jobs=0)
    monkeypatch.setattr('app.ui.main_window.UpdateWorker', lambda db, parent: UpdateWorker(db, parent, update))
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(10)
    try:
        window.jobs.update_button.click()
        worker = window.worker
        window.start_update()
        assert window.worker is worker
        assert not window.jobs.update_button.isEnabled()
        QTest.qWait(100)
        assert ticks and threads[0] != get_ident()
        window.navigation.setCurrentRow(2)
        assert window.pages.currentIndex() == 2
    finally:
        release.set()
        timer.stop()
        wait_finished(window)
    assert window.jobs.update_button.isEnabled()
    assert 'Completado' in window.jobs.update_status.text()


def test_worker_error_keeps_window_and_data(window, monkeypatch):
    def update(*args):
        raise OSError('HTTP unavailable')
    monkeypatch.setattr('app.ui.main_window.UpdateWorker', lambda db, parent: UpdateWorker(db, parent, update))
    messages = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: messages.append(args[2]))
    window.start_update()
    wait_finished(window)
    assert messages and 'guardadas siguen disponibles' in messages[0]
    assert window.jobs.table.rowCount() == 18 and window.isVisible()


def test_close_cancels_worker_without_destroying_thread(window, monkeypatch):
    def update(db, cancel, progress):
        cancel.wait(2)
        raise OSError('Cancelado')
    monkeypatch.setattr('app.ui.main_window.UpdateWorker', lambda db, parent: UpdateWorker(db, parent, update))
    window.start_update()
    assert not window.close()
    assert window.worker.cancel.is_set()
    wait_finished(window)
    assert not window.isVisible()
