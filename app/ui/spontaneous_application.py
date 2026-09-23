from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QFormLayout, QLabel, QComboBox, QPlainTextEdit, QPushButton
from app.ui.common import guarded, open_url, valid_url


class SpontaneousApplicationPanel(QWidget):
    saved = Signal()

    def __init__(self, repository, company, parent=None):
        super().__init__(parent)
        self.repository, self.company = repository, company
        form = QFormLayout(self)
        form.addRow(QLabel('Candidatura espontánea · Disponible: Sí'))
        note = QLabel('El envío se realiza manualmente en la web. Aquí solo registras tu seguimiento.')
        note.setWordWrap(True)
        form.addRow(note)
        self.status = QComboBox()
        self.status.addItems(['No enviada', 'CV enviado'])
        self.status.setCurrentText(company['spontaneous_application_status'])
        self.date = QLabel(company['spontaneous_application_date'] or 'No enviada')
        self.notes = QPlainTextEdit(company['notes'])
        self.notes.setMaximumHeight(100)
        form.addRow('Estado', self.status)
        form.addRow('Fecha', self.date)
        form.addRow('Notas', self.notes)
        self.open_button = QPushButton('Abrir página de candidatura')
        self.open_button.setEnabled(valid_url(company['spontaneous_application_url']))
        self.open_button.clicked.connect(lambda: open_url(self, company['spontaneous_application_url']))
        form.addRow(self.open_button)
        self.save_button = QPushButton('Guardar seguimiento')
        self.save_button.clicked.connect(self.save)
        form.addRow(self.save_button)

    @guarded
    def save(self):
        self.repository.save_spontaneous_application(self.company['id'], self.status.currentText(), self.notes.toPlainText())
        company = next(c for c in self.repository.get_companies() if c['id'] == self.company['id'])
        self.date.setText(company['spontaneous_application_date'] or 'No enviada')
        self.saved.emit()
