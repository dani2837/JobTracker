import json
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QProgressBar, QVBoxLayout, QWidget)
from app.database.schema import STATUSES
from app.ui.common import fill_table, guarded, heading, make_table, open_url, selected_id, valid_url
from app.ui.job_detail import JobDetail


class JobsView(QWidget):
    changed = Signal()
    update_requested = Signal()
    recalculate_requested = Signal()

    def __init__(self, repository, companies, settings):
        super().__init__()
        self.repository, self.companies, self.settings = repository, companies, settings
        self.jobs = []
        layout = QVBoxLayout(self)
        layout.addWidget(heading('Ofertas'))
        self.daily_summary = QLabel()
        self.daily_summary.setWordWrap(True)
        layout.addWidget(self.daily_summary)
        update_row = QHBoxLayout()
        self.update_button = QPushButton('Actualizar ofertas')
        self.update_button.setStyleSheet('background: #225cc5; color: white; font-weight: bold;')
        self.update_button.clicked.connect(self.update_requested.emit)
        update_row.addWidget(self.update_button)
        self.recalculate_button = QPushButton('Recalcular compatibilidad')
        self.recalculate_button.clicked.connect(self.recalculate_requested.emit)
        update_row.addWidget(self.recalculate_button)
        self.update_status = QLabel('Pulsa Actualizar ofertas para buscar novedades')
        self.update_status.setWordWrap(True)
        update_row.addWidget(self.update_status, 1)
        layout.addLayout(update_row)
        self.progress_panel = QWidget()
        progress_layout = QVBoxLayout(self.progress_panel)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat('%p% · progreso por fuentes')
        self.progress_label = QLabel()
        self.progress_label.setWordWrap(True)
        self.page_progress = QLabel()
        self.page_progress.setWordWrap(True)
        for widget in (self.progress_bar, self.progress_label, self.page_progress):
            progress_layout.addWidget(widget)
        layout.addWidget(self.progress_panel)
        self.progress_panel.hide()
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Buscar puesto, empresa, ubicación o descripción…')
        self.search.setClearButtonEnabled(True)
        self.state_filter = QComboBox()
        self.state_filter.addItems(['Todos los estados', *STATUSES])
        self.company_filter = QComboBox()
        self.company_filter.setMinimumContentsLength(12)
        self.company_filter.addItem('Todas las empresas', None)
        self.only_new = QCheckBox('Solo nuevas')
        self.only_new.setChecked(True)
        for widget in [self.search, self.state_filter, self.company_filter, self.only_new]:
            filters.addWidget(widget)
        filters.setStretch(0, 1)
        layout.addLayout(filters)
        quick = QHBoxLayout()
        self.source_filter = QComboBox()
        self.source_filter.addItems(['Todas las fuentes', 'Datos de prueba', 'Sopra Steria', 'Izertis', 'Indra / Minsait', 'Deloitte', 'Accenture', 'Ayesa', 'T-Systems', 'Emergya', 'Isotrol', 'InfoJobs', 'Tecnoempleo'])
        self.source_filter.currentIndexChanged.connect(self.apply_filters)
        quick.addWidget(self.source_filter)
        self.quick_buttons = {}
        for name in ['90%+', '75%+', '60%+', 'Sevilla', 'Remoto']:
            button = QPushButton(name)
            button.setCheckable(True)
            button.toggled.connect(self.apply_filters)
            self.quick_buttons[name] = button
            quick.addWidget(button)
        clear = QPushButton('Limpiar filtros')
        clear.clicked.connect(self.clear_filters)
        quick.addWidget(clear)
        quick.addStretch()
        self.count = QLabel()
        self.count.setMinimumWidth(80)
        quick.addWidget(self.count)
        layout.addLayout(quick)
        scoring_filters = QHBoxLayout()
        self.score_filter = QComboBox()
        self.score_filter.addItems(['Todos los scores', 'Prioritarias 90+', 'Interesantes 75+', 'Revisar 60+', 'Excluidas'])
        self.experience_filter = QComboBox()
        self.experience_filter.addItems(['Toda experiencia', 'Sin experiencia', 'Junior'])
        self.role_filter = QComboBox()
        for title, key in [('Todos los puestos', None), ('Desarrollo', 'development'), ('Sistemas', 'systems'),
                           ('Soporte', 'support'), ('QA', 'qa')]:
            self.role_filter.addItem(title, key)
        self.show_excluded = QCheckBox('Mostrar excluidas')
        self.show_hidden = QCheckBox('Mostrar <40')
        self.show_test = QCheckBox('Datos de prueba')
        for widget in [self.score_filter, self.experience_filter, self.role_filter]:
            widget.currentIndexChanged.connect(self.apply_filters)
            scoring_filters.addWidget(widget)
        for widget in [self.show_excluded, self.show_hidden, self.show_test]:
            widget.toggled.connect(self.apply_filters)
            scoring_filters.addWidget(widget)
        layout.addLayout(scoring_filters)
        self.table = make_table(['Score','Estado','Puesto','Empresa','Ubicación','Modalidad','Fecha','Nueva','Fuente','Activa','Clasificación'])
        for index, width in enumerate([65,160,260,140,155,100,105,60]):
            self.table.setColumnWidth(index, width)
        self.table.setColumnWidth(8, 130)
        self.table.setColumnWidth(10, 170)
        # Mantener índices lógicos de las columnas existentes; cambiar su orden visual.
        header = self.table.horizontalHeader()
        header.moveSection(header.visualIndex(10), 1)
        header.moveSection(header.visualIndex(8), 7)
        self.table.sortItems(0, Qt.SortOrder.DescendingOrder)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        self.table.cellDoubleClicked.connect(self.show_detail)
        layout.addWidget(self.table, 1)
        self.empty_message = QLabel('No hay ofertas con estos filtros. Actualiza o desmarca «Solo nuevas» para ver las anteriores.')
        self.empty_message.setWordWrap(True)
        layout.addWidget(self.empty_message)
        actions = QHBoxLayout()
        self.detail_button = QPushButton('Ver detalle')
        self.open_button = QPushButton('Abrir oferta original')
        self.seen_button = QPushButton('Marcar como vista')
        self.seen_button.clicked.connect(self.mark_seen)
        self.status = QComboBox()
        self.status.addItems(STATUSES)
        actions.addWidget(self.detail_button)
        actions.addWidget(self.open_button)
        actions.addWidget(self.seen_button)
        actions.addStretch()
        actions.addWidget(QLabel('Cambiar estado:'))
        actions.addWidget(self.status)
        layout.addLayout(actions)
        self.detail_button.clicked.connect(self.show_detail)
        self.open_button.clicked.connect(self.open_selected)
        self.status.currentTextChanged.connect(self.save_status)
        self.search.textChanged.connect(self.apply_filters)
        self.state_filter.currentIndexChanged.connect(self.apply_filters)
        self.company_filter.currentIndexChanged.connect(self.apply_filters)
        self.only_new.toggled.connect(self.apply_filters)
        self.selection_changed()

    def refresh(self):
        self.daily_summary.setText(self.repository.daily_summary())
        company_id = self.company_filter.currentData()
        self.company_filter.blockSignals(True)
        self.company_filter.clear()
        self.company_filter.addItem('Todas las empresas', None)
        for company in self.companies.get_companies():
            self.company_filter.addItem(company['name'], company['id'])
        self.company_filter.setCurrentIndex(max(0, self.company_filter.findData(company_id)))
        self.company_filter.blockSignals(False)
        self.jobs = self.repository.get_all_jobs(show_discarded=self.settings.get('show_discarded'))
        for name in sorted({job['source_name'] for job in self.jobs if job['source_name'] and not job['is_test_data']}):
            if self.source_filter.findText(name) < 0:
                self.source_filter.addItem(name)
        self.apply_filters()

    def apply_filters(self, *_):
        query = self.search.text().strip().casefold()
        state = self.state_filter.currentText()
        company_id = self.company_filter.currentData()
        quick = {key: button.isChecked() for key, button in self.quick_buttons.items()}
        rows = []
        for job in self.jobs:
            if job['is_test_data'] and not self.show_test.isChecked() and self.source_filter.currentIndex() != 1:
                continue
            details = json.loads(job['score_details']) if job.get('score_details') else {}
            facts = details.get('facts', {})
            only_excluded = self.score_filter.currentText() == 'Excluidas'
            if only_excluded and not job['excluded']:
                continue
            if job['excluded'] and not (self.show_excluded.isChecked() or only_excluded):
                continue
            if job.get('classification') == 'Ocultar' and not self.show_hidden.isChecked():
                continue
            minimum = {1: 90, 2: 75, 3: 60}.get(self.score_filter.currentIndex())
            if minimum is not None and (job['score'] is None or job['score'] < minimum or job['excluded']):
                continue
            if self.experience_filter.currentText() == 'Sin experiencia' and facts.get('experience_kind') not in ('none', 'zero_range', 'entry'):
                continue
            if self.experience_filter.currentText() == 'Junior' and not facts.get('junior'):
                continue
            if self.role_filter.currentData() and facts.get('role_kind') != self.role_filter.currentData():
                continue
            if self.source_filter.currentIndex() == 1 and not job['is_test_data']:
                continue
            if self.source_filter.currentIndex() >= 2 and (job['is_test_data'] or job['source_name'] != self.source_filter.currentText()):
                continue
            if query and query not in ' '.join(str(job[key]) for key in ['title','company','location','description']).casefold():
                continue
            if self.state_filter.currentIndex() and job['status'] != state:
                continue
            if company_id is not None and job['company_id'] != company_id:
                continue
            if self.only_new.isChecked() and not job['is_new']:
                continue
            score = job['score'] if job['score'] is not None else -1
            if quick['90%+'] and score < 90 or quick['75%+'] and score < 75:
                continue
            if quick['60%+'] and score < 60:
                continue
            if quick['Sevilla'] and facts.get('location_kind') != 'seville' and (job['location'] or '').split(',')[0].strip().casefold() != 'sevilla':
                continue
            if quick['Remoto'] and facts.get('location_kind') != 'remote' and job['modality'] != 'Remoto' and job.get('remote') != 1:
                continue
            rows.append(job)
        current_id = selected_id(self.table)
        fill_table(self.table, rows, ['score','status','title','company','location','modality','published_date','is_new',
                                     'source_label','is_active','classification'])
        self.table.clearSelection()
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) == current_id:
                self.table.selectRow(row)
                break
        self.count.setText(f'{len(rows)} ofertas')
        self.empty_message.setVisible(not rows)
        self.selection_changed()

    def clear_filters(self):
        self.search.clear()
        self.state_filter.setCurrentIndex(0)
        self.company_filter.setCurrentIndex(0)
        self.source_filter.setCurrentIndex(0)
        self.only_new.setChecked(False)
        self.score_filter.setCurrentIndex(0)
        self.experience_filter.setCurrentIndex(0)
        self.role_filter.setCurrentIndex(0)
        self.show_excluded.setChecked(False)
        self.show_hidden.setChecked(False)
        for button in self.quick_buttons.values():
            button.setChecked(False)

    def current_job(self):
        job_id = selected_id(self.table)
        return next((job for job in self.jobs if job['id'] == job_id), None)

    def selection_changed(self):
        job = self.current_job()
        self.detail_button.setEnabled(job is not None)
        self.open_button.setEnabled(job is not None and valid_url(job['url']))
        self.status.setEnabled(job is not None)
        self.seen_button.setEnabled(job is not None and bool(job['is_new']))
        self.status.blockSignals(True)
        self.status.setCurrentText(job['status'] if job else 'Nueva')
        self.status.blockSignals(False)

    @guarded
    def mark_seen(self):
        job = self.current_job()
        if job:
            self.repository.mark_seen(job['id'])
            self.changed.emit()

    @guarded
    def save_status(self, status):
        job = self.current_job()
        if job:
            try:
                self.repository.update_job_status(job['id'], status)
            except Exception:
                self.selection_changed()
                raise
            self.changed.emit()

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
