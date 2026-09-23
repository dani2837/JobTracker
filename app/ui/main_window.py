import logging
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QMainWindow, QMessageBox,
                               QStackedWidget, QVBoxLayout, QWidget)
from app.database.repositories import CompanyRepository, JobRepository
from app.ui.common import guarded
from app.ui.companies_view import CompaniesView
from app.ui.dashboard_view import DashboardView
from app.ui.jobs_view import JobsView
from app.ui.settings_view import SettingsView
from app.ui.sent_applications_view import SentApplicationsView
from app.ui.update_worker import UpdateWorker
from app.services.scoring.recalculate import recalculate_all_jobs

STYLE = """
QWidget { font-family: 'Segoe UI'; font-size: 10pt; color: #233248; }
QMainWindow, QDialog { background: #f3f6fa; }
QLabel#heading { font-size: 22pt; font-weight: 600; margin: 8px 0; }
QLabel#metric { font-size: 28pt; font-weight: 600; color: #225cc5; }
QFrame#card { background: white; border: 1px solid #dce3ee; border-radius: 8px; }
QListWidget { background: #17283f; color: #dce7f7; border: none; border-radius: 6px; }
QListWidget::item { padding: 16px 12px; }
QListWidget::item:selected { background: #2d5da1; color: white; }
QTableWidget { background: white; alternate-background-color: #f5f8fc;
               gridline-color: #e5eaf1; border: 1px solid #dce3ee; }
QTableWidget::item:selected { background: #d9e8fc; color: #142f55; }
QHeaderView::section { background: #e9eff7; border: none; padding: 10px 6px; font-weight: 600; }
QPushButton, QComboBox, QLineEdit { padding: 7px; border: 1px solid #bdcadb;
                                  border-radius: 5px; background: white; }
QPushButton:hover { background: #eaf1fd; }
QPushButton:checked { background: #225cc5; color: white; }
QPushButton:disabled, QComboBox:disabled { color: #8995a5; background: #edf0f4; }
QCheckBox { spacing: 6px; }
"""


class MainWindow(QMainWindow):
    def __init__(self, db, settings):
        super().__init__()
        self.settings = settings
        self.db = db
        self.worker = None
        self.closing_after_update = False
        self.setWindowTitle('JobTracker')
        self.resize(1360, 820)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(STYLE)
        jobs, companies = JobRepository(db), CompanyRepository(db)
        self.dashboard = DashboardView(jobs, settings)
        self.jobs = JobsView(jobs, companies, settings)
        self.companies = CompaniesView(companies)
        self.configuration = SettingsView(settings, db.path)
        self.sent_applications = SentApplicationsView(jobs)
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(20)
        sidebar = QVBoxLayout()
        brand = QLabel('JobTracker')
        brand.setStyleSheet('font-size: 20pt; font-weight: 700; padding: 12px 0;')
        sidebar.addWidget(brand)
        self.navigation = QListWidget()
        self.navigation.setFixedWidth(165)
        self.navigation.addItems(['Resumen','Ofertas','Empresas','Configuración','CV enviados'])
        sidebar.addWidget(self.navigation, 1)
        sidebar.addWidget(QLabel('Local · Seguimiento\nde ofertas'))
        layout.addLayout(sidebar)
        self.pages = QStackedWidget()
        for page in [self.dashboard, self.jobs, self.companies, self.configuration, self.sent_applications]:
            self.pages.addWidget(page)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(root)
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.jobs.changed.connect(self.refresh)
        self.sent_applications.changed.connect(self.refresh)
        self.jobs.update_requested.connect(self.start_update)
        self.jobs.recalculate_requested.connect(self.start_recalculate)
        self.configuration.changed.connect(self.refresh)
        self.configuration.recalculate_requested.connect(self.start_recalculate)
        self.refresh()
        self.navigation.setCurrentRow(1)

    @guarded
    def refresh(self):
        self.jobs.refresh()
        self.dashboard.refresh()
        self.companies.refresh()
        self.sent_applications.refresh()

    def closeEvent(self, event):
        if self.settings.get('confirm_close') and not self.closing_after_update:
            answer = QMessageBox.question(self, 'Cerrar JobTracker', '¿Quieres cerrar JobTracker?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        if self.worker is not None and self.worker.isRunning():
            self.closing_after_update = True
            self.worker.cancel.set()
            self.jobs.update_status.setText('Cancelando actualización antes de cerrar…')
            event.ignore()
            return
        logging.getLogger(__name__).info('Cierre de aplicación')
        event.accept()

    @guarded
    def start_update(self):
        if self.worker is not None:
            return
        self.jobs.update_button.setEnabled(False)
        self.jobs.recalculate_button.setEnabled(False)
        self.jobs.update_status.setText('Actualizando fuentes…')
        self.configuration.set_profile_busy(True)
        self.jobs.update_status.setToolTip('')
        self.jobs.progress_panel.show()
        self.jobs.progress_bar.setValue(0)
        self.jobs.progress_label.setText('Preparando fuentes…')
        self.jobs.page_progress.clear()
        self.worker = UpdateWorker(self.db, self)
        self.worker.progress.connect(self.update_progress_message)
        self.worker.source_progress.connect(self.update_source_progress)
        self.worker.succeeded.connect(self.update_succeeded)
        self.worker.failed.connect(self.update_failed)
        self.worker.finished.connect(self.update_finished)
        self.worker.start()

    def update_progress_message(self, message):
        self.jobs.update_status.setText(message)
        if 'página' in message.casefold():
            self.jobs.page_progress.setText(message + ' · total interno no disponible')
        elif 'detalle' in message.casefold():
            self.jobs.page_progress.setText(message)

    def update_source_progress(self, event):
        total, processed = event['total'], event['processed']
        self.jobs.progress_bar.setValue(processed * 100 // total if total else 0)
        status = {'running': 'En curso', 'completed': 'Completada', 'error': 'Error',
                  'skipped': 'Omitida', 'starting': 'Preparando'}.get(event['status'], '')
        self.jobs.progress_label.setText(f"{processed}/{total} fuentes procesadas · {event['errors']} errores · "
                                         f"{status}: {event['source']}")
        if event['status'] in ('running', 'starting', 'skipped'):
            self.jobs.page_progress.clear()
        if event.get('error'):
            self.jobs.page_progress.setText(f"{event['source']}: {event['error']}")

    def update_succeeded(self, result):
        self.jobs.progress_bar.setValue(100)
        self.jobs.page_progress.clear()
        count = len(result.get('sources', []))
        self.jobs.progress_label.setText(f"Finalizado · {count}/{count} fuentes procesadas · {result.get('errors', 0)} errores")
        self.refresh()
        if 'sources' in result:
            lines = [f"Completado · {result['total_found']} encontradas · {result['new_jobs']} nuevas · "
                     f"{result['updated_jobs']} actualizadas · {result['excluded']} excluidas · {result['errors']} errores."]
            for item in result['sources']:
                lines.append(f"{item['source']} · " + (f"{item['new_jobs']} nuevas, {item['updated_jobs']} actualizadas, "
                    f"{item['excluded_jobs']} >60 días, {item['compatible']} compatibles" if item.get('success') else item['error']))
            self.jobs.update_status.setText(lines[0])
            self.jobs.update_status.setToolTip('\n'.join(lines))
            return
        self.jobs.update_status.setText(
            f"Sopra Steria · {result['total_found']} encontradas · {result['new_jobs']} nuevas · "
            f"{result['updated_jobs']} conocidas · {result['excluded_jobs']} anteriores a 60 días. Completado.")

    def update_failed(self, message):
        self.configuration.profile_label.setText(message)
        if not self.jobs.progress_panel.isHidden():
            self.jobs.progress_label.setText(self.jobs.progress_label.text() + ' · Actualización interrumpida')
        self.jobs.update_status.setText(message)
        if not self.closing_after_update:
            QMessageBox.warning(self, 'Actualización no completada', message)

    def update_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.configuration.set_profile_busy(False)
        self.jobs.update_button.setEnabled(True)
        self.jobs.recalculate_button.setEnabled(True)
        if self.closing_after_update:
            self.close()

    @guarded
    def start_recalculate(self):
        if self.worker is not None:
            return
        self.jobs.progress_panel.hide()
        self.configuration.set_profile_busy(True)
        self.jobs.update_button.setEnabled(False)
        self.jobs.recalculate_button.setEnabled(False)
        self.jobs.update_status.setText('Recalculando compatibilidad…')
        self.worker = UpdateWorker(self.db, self, update=recalculate_all_jobs,
            error_message='No se pudo recalcular. Se conservan los scores anteriores. Comprueba el perfil JSON y el log.')
        self.worker.progress.connect(self.jobs.update_status.setText)
        self.worker.succeeded.connect(self.recalculation_succeeded)
        self.worker.failed.connect(self.update_failed)
        self.worker.finished.connect(self.update_finished)
        self.worker.start()

    @guarded
    def recalculation_succeeded(self, result):
        self.refresh()
        self.configuration.refresh_profile()
        self.configuration.profile_label.setText(f"Compatibilidad recalculada: {result['processed']} ofertas. Sin consultar Internet.")
        self.jobs.update_status.setText(f"Compatibilidad recalculada: {result['processed']} ofertas. Sin consultar Internet.")
