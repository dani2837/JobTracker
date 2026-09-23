from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from app.ui.common import heading, make_table, fill_table, selected_id, valid_url, open_url, guarded
from app.ui.job_detail import JobDetail


class SentApplicationsView(QWidget):
    changed = Signal()

    def __init__(self, repository):
        super().__init__()
        self.repository = repository
        self.jobs = []
        layout = QVBoxLayout(self)
        layout.addWidget(heading('CV enviados'))
        note = QLabel('Ofertas donde has registrado el envío de tu CV. Se muestran aunque estén inactivas o excluidas. '
                      'Si te rechazan o no quieres continuar, puedes descartarlas sin borrarlas.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.count = QLabel()
        layout.addWidget(self.count)
        self.table = make_table(['Score', 'Puesto', 'Empresa', 'Ubicación', 'Estado', 'Fuente'])
        for column, width in enumerate([65, 320, 180, 160, 120, 120]):
            self.table.setColumnWidth(column, width)
        self.table.sortItems(0, Qt.SortOrder.DescendingOrder)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        self.table.cellDoubleClicked.connect(self.show_detail)
        layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        self.detail_button = QPushButton('Ver detalle')
        self.open_button = QPushButton('Abrir oferta original')
        self.discard_button = QPushButton('Descartar candidatura')
        self.detail_button.clicked.connect(self.show_detail)
        self.open_button.clicked.connect(self.open_selected)
        self.discard_button.clicked.connect(self.discard_selected)
        for button in (self.detail_button, self.open_button, self.discard_button):
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        self.selection_changed()

    def refresh(self):
        current = selected_id(self.table)
        self.jobs = [job for job in self.repository.get_all_jobs()
                     if not job['is_test_data'] and job['status'] == 'CV enviado']
        fill_table(self.table, self.jobs, ['score', 'title', 'company', 'location', 'status', 'source_label'])
        self.table.clearSelection()
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) == current:
                self.table.selectRow(row)
                break
        self.count.setText(f'{len(self.jobs)} candidaturas con CV enviado' if self.jobs else
                           'Todavía no hay CV enviados. Abre una oferta y pulsa «CV ENVIADO» para registrarla aquí.')
        self.selection_changed()

    def current_job(self):
        return next((job for job in self.jobs if job['id'] == selected_id(self.table)), None)

    def selection_changed(self):
        job = self.current_job()
        self.detail_button.setEnabled(job is not None)
        self.discard_button.setEnabled(job is not None)
        self.open_button.setEnabled(job is not None and valid_url(job['url']))

    @guarded
    def show_detail(self, *_):
        job = self.current_job()
        if job:
            dialog = JobDetail(self.repository, job['id'], self)
            dialog.changed.connect(self.changed.emit)
            dialog.exec()

    def open_selected(self):
        job = self.current_job()
        if job:
            open_url(self, job['url'])

    @guarded
    def discard_selected(self):
        job = self.current_job()
        if job:
            self.repository.update_job_status(job['id'], 'Descartada')
            self.changed.emit()
