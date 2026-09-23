import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import sqlite3
import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
from app.config.settings import Settings
from app.database.db import Database
from app.database.repositories import JobRepository
from app.services.seed_data import seed_database
from app.ui.job_detail import JobDetail
from app.ui.main_window import MainWindow


@pytest.fixture(scope='module')
def application():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(db, tmp_path, application):
    seed_database(db)
    settings = Settings(tmp_path / 'settings.json')
    settings.set('confirm_close', False)
    widget = MainWindow(db, settings)
    # Las pruebas históricas operan con el catálogo de demostración completo.
    widget.jobs.show_test.setChecked(True)
    widget.jobs.only_new.setChecked(False)
    widget.show()
    application.processEvents()
    yield widget
    widget.close()
    application.processEvents()


def test_initial_ui_and_navigation(window, application):
    assert window.isVisible()
    assert window.jobs.table.rowCount() == 18
    assert window.companies.table.rowCount() == 15
    assert window.dashboard.values['total'].text() == '18'
    assert window.dashboard.table.rowCount() == 5
    for index in range(4):
        window.navigation.setCurrentRow(index)
        assert window.pages.currentIndex() == index
    window.resize(1024, 768)
    application.processEvents()
    assert window.width() == 1024
    assert not window.jobs.detail_button.isEnabled()
    assert not window.jobs.open_button.isEnabled()


def test_filters_and_numeric_sort(window):
    view = window.jobs
    view.search.setText('java')
    assert view.table.rowCount() == 2
    view.clear_filters()
    view.company_filter.setCurrentIndex(1)
    expected = sum(job['company_id'] == view.company_filter.currentData() for job in view.jobs)
    assert view.table.rowCount() == expected
    view.clear_filters()
    for name, expected in [('90%+',4),('75%+',9),('Sevilla',5)]:
        view.quick_buttons[name].setChecked(True)
        assert view.table.rowCount() == expected
        view.clear_filters()
    view.quick_buttons['Remoto'].setChecked(True)
    assert view.table.rowCount() == sum(job['modality'] == 'Remoto' for job in view.jobs)
    view.clear_filters()
    view.table.sortItems(0, Qt.SortOrder.AscendingOrder)
    assert view.table.item(0, 0).data(Qt.ItemDataRole.DisplayRole) == 40
    view.table.sortItems(0, Qt.SortOrder.DescendingOrder)
    assert view.table.item(0, 0).data(Qt.ItemDataRole.DisplayRole) == 98
    for column in range(1, 8):
        view.table.sortItems(column, Qt.SortOrder.AscendingOrder)
        values = [view.table.item(row, column).text() for row in range(18)]
        view.table.sortItems(column, Qt.SortOrder.DescendingOrder)
        descending = [view.table.item(row, column).text() for row in range(18)]
        assert descending == list(reversed(values))
    view.search.setText('no existe esta oferta')
    assert view.table.rowCount() == 0
    assert not view.detail_button.isEnabled()


def test_status_detail_restart_and_preferences(window, db, application):
    view = window.jobs
    view.table.selectRow(0)
    job_id = view.current_job()['id']
    assert view.detail_button.isEnabled()
    assert not view.open_button.isEnabled()
    view.status.setCurrentText('Me interesa')
    assert JobRepository(db).get_job_by_id(job_id)['status'] == 'Me interesa'
    assert window.dashboard.values['nuevas'].text() == '17'
    view.state_filter.setCurrentText('Me interesa')
    assert view.table.rowCount() == 1
    view.only_new.setChecked(True)
    assert view.table.rowCount() == 0
    view.clear_filters()
    view.table.selectRow(0)
    opened = []

    def inspect_detail():
        dialog = application.activeModalWidget()
        if isinstance(dialog, JobDetail):
            opened.append(dialog.job['id'])
            dialog.status.setCurrentText('CV enviado')
            dialog.accept()

    QTimer.singleShot(0, inspect_detail)
    view.detail_button.click()
    assert opened == [job_id]
    assert JobRepository(db).get_job_by_id(job_id)['status'] == 'CV enviado'
    view.status.setCurrentText('Descartada')
    window.configuration.options['show_discarded'].setChecked(False)
    assert view.table.rowCount() == 17
    assert window.dashboard.values['total'].text() == '17'
    settings_path = window.settings.path
    window.close()
    reopened_db = Database(db.path)
    reopened_db.initialize()
    seed_database(reopened_db)
    reopened = MainWindow(reopened_db, Settings(settings_path))
    reopened.jobs.show_test.setChecked(True)
    reopened.jobs.only_new.setChecked(False)
    reopened.show()
    try:
        assert reopened.jobs.table.rowCount() == 17
        assert reopened.jobs.repository.get_job_by_id(job_id)['status'] == 'Descartada'
        assert len(reopened.jobs.repository.get_all_jobs()) == 18
    finally:
        reopened.close()


def test_companies_toggle_and_detail(window, application):
    view = window.companies
    view.table.selectRow(0)
    company_id = view.current_company()['id']
    view.toggle_button.click()
    assert next(c for c in view.repository.get_companies() if c['id'] == company_id)['enabled'] == 0
    opened = []

    def dismiss():
        dialog = application.activeModalWidget()
        if dialog:
            opened.append(dialog.windowTitle())
            dialog.accept()

    QTimer.singleShot(0, dismiss)
    view.detail_button.click()
    assert opened == ['Detalle de empresa']


def test_database_error_is_reported_and_ui_recovers(window, monkeypatch):
    view = window.jobs
    view.table.selectRow(0)
    messages = []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: messages.append(args[2]))

    def fail(*args):
        raise sqlite3.OperationalError('database is locked')

    monkeypatch.setattr(view.repository, 'update_job_status', fail)
    view.status.setCurrentText('Inscrito')
    assert messages
    assert view.status.currentText() == 'Nueva'
    assert window.isVisible()


def test_close_confirmation(window, monkeypatch):
    window.settings.set('confirm_close', True)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.No)
    assert not window.close()
    assert window.isVisible()
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    assert window.close()
