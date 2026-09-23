from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QLabel, QPushButton, QVBoxLayout, QWidget)
from app.ui.common import fill_table, guarded, heading, make_table, selected_id
from app.ui.spontaneous_application import SpontaneousApplicationPanel


class CompaniesView(QWidget):
    def __init__(self, repository):
        super().__init__()
        self.repository = repository
        self.companies = []
        layout = QVBoxLayout(self)
        layout.addWidget(heading('Empresas'))
        note = QLabel('Fuentes: Sopra Steria, Izertis, Indra / Minsait, Deloitte, Accenture, Ayesa y T-Systems. NTT DATA y Viewnext: sin integración pública fiable en esta fase. Las candidaturas son manuales.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.table = make_table(['Empresa','Tipo de fuente','Activa','Última revisión','Número de ofertas'])
        for index, width in enumerate([240,160,90,170,150]):
            self.table.setColumnWidth(index, width)
        self.table.sortItems(0, Qt.SortOrder.AscendingOrder)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        self.table.cellDoubleClicked.connect(self.show_detail)
        layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        self.toggle_button = QPushButton('Activar / desactivar')
        self.detail_button = QPushButton('Ver detalle')
        actions.addWidget(self.toggle_button)
        actions.addWidget(self.detail_button)
        actions.addStretch()
        layout.addLayout(actions)
        self.toggle_button.clicked.connect(self.toggle)
        self.detail_button.clicked.connect(self.show_detail)
        self.selection_changed()

    def refresh(self):
        self.companies = self.repository.get_companies()
        fill_table(self.table, self.companies, ['name','source_type','enabled','last_checked','job_count'])
        self.selection_changed()

    def current_company(self):
        company_id = selected_id(self.table)
        return next((company for company in self.companies if company['id'] == company_id), None)

    def selection_changed(self):
        company = self.current_company()
        self.toggle_button.setEnabled(company is not None)
        self.detail_button.setEnabled(company is not None)
        self.toggle_button.setText(('Desactivar' if company['enabled'] else 'Activar') if company else 'Activar / desactivar')

    @guarded
    def toggle(self):
        company = self.current_company()
        if company:
            self.repository.set_enabled(company['id'], not company['enabled'])
            self.refresh()

    @guarded
    def show_detail(self, *_):
        company = self.current_company()
        if not company:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('Detalle de empresa')
        dialog.resize(460, 300)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        for label, key in [('Empresa','name'),('URL de empleo','careers_url'),('Tipo de fuente','source_type'),
                           ('Última revisión','last_checked'),('Ofertas','job_count'),('Creada','created_at')]:
            value = QLabel(str(company[key] if company[key] is not None and company[key] != '' else 'No disponible'))
            value.setTextFormat(Qt.TextFormat.PlainText)
            value.setWordWrap(True)
            form.addRow(label, value)
        form.addRow('Activa', QLabel('Sí' if company['enabled'] else 'No'))
        layout.addLayout(form)
        if company.get('accepts_spontaneous_application'):
            panel = SpontaneousApplicationPanel(self.repository, company, dialog)
            panel.saved.connect(self.refresh)
            layout.addWidget(panel)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()
