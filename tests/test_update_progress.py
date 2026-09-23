from threading import Event
from time import monotonic, sleep
from PySide6.QtWidgets import QApplication, QMessageBox
from app.services.source_update import update_all_jobs
from app.sources.base import BaseSource, ScanResult, SourceError, ScanCancelled
from app.ui.update_worker import UpdateWorker
from tests.test_ui import application, window


def wait_finished(window):
    deadline = monotonic() + 5
    while window.worker is not None and monotonic() < deadline:
        QApplication.processEvents()
        sleep(0.01)  # Ceder el GIL al worker que importa en SQLite.
    assert window.worker is None


class LocalSource(BaseSource):
    url = 'https://example.com'

    def __init__(self, name, failure=False):
        self.name = self.company = name
        self.failure = failure

    def fetch_jobs(self):
        if self.failure:
            raise SourceError('HTTP 403')
        return ScanResult((), 1, 0, True)


def test_real_source_events_cross_worker_and_errors_continue(window, monkeypatch):
    events = []
    def update(db, cancel, progress):
        return update_all_jobs(db, cancel, progress, sources=[
            LocalSource('Accenture', True), LocalSource('Ayesa'), LocalSource('Sin activar')])
    def factory(db, parent):
        worker = UpdateWorker(db, parent, update)
        worker.source_progress.connect(events.append)
        return worker
    monkeypatch.setattr('app.ui.main_window.UpdateWorker', factory)
    window.jobs.update_button.click()
    wait_finished(window)
    assert [(e['processed'], e['status']) for e in events] == [
        (0, 'starting'), (0, 'running'), (1, 'error'), (1, 'running'), (2, 'completed'), (3, 'skipped')]
    assert all(e['total'] == 3 for e in events)
    assert events[2]['error'] == 'HTTP 403'
    assert window.jobs.progress_bar.value() == 100
    assert '3/3' in window.jobs.progress_label.text() and '1 errores' in window.jobs.progress_label.text()
    assert 'Completado' in window.jobs.update_status.text()
    assert 'HTTP 403' in window.jobs.update_status.toolTip()
    assert window.jobs.update_button.isEnabled()


def test_pages_do_not_invent_percentage_and_new_run_resets(window, monkeypatch):
    window.jobs.progress_panel.show()
    window.update_source_progress(dict(total=10, processed=2, source='InfoJobs', status='running', errors=0))
    window.update_progress_message('InfoJobs · página 4: 65 ofertas')
    assert window.jobs.progress_bar.value() == 20
    assert '2/10' in window.jobs.progress_label.text() and 'InfoJobs' in window.jobs.progress_label.text()
    assert 'página 4' in window.jobs.page_progress.text()
    window.update_progress_message('InfoJobs · detalle 3/65')
    assert window.jobs.progress_bar.value() == 20 and '3/65' in window.jobs.page_progress.text()
    def interrupted(*args):
        raise ScanCancelled('Cancelada')
    monkeypatch.setattr('app.ui.main_window.UpdateWorker', lambda db, parent: UpdateWorker(db, parent, interrupted))
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: None)
    window.jobs.update_button.click()
    assert window.jobs.progress_bar.value() == 0 and not window.jobs.page_progress.text()
    wait_finished(window)
    assert window.jobs.progress_bar.value() == 0
    assert 'interrumpida' in window.jobs.progress_label.text()


def test_empty_batch_completes_without_division_by_zero(window):
    events = []
    def progress(message):
        pass
    progress.source_progress = events.append
    result = update_all_jobs(window.db, Event(), progress, sources=[])
    window.update_source_progress(events[0])
    assert window.jobs.progress_bar.value() == 0
    window.update_succeeded(result)
    assert window.jobs.progress_bar.value() == 100 and '0/0' in window.jobs.progress_label.text()
