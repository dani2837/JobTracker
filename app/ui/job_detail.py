import json
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QLabel, QPushButton, QTabWidget, QTextBrowser, QVBoxLayout, QWidget, QScrollArea)
from app.database.schema import STATUSES
from app.ui.common import guarded, heading, open_url, valid_url


class JobDetail(QDialog):
    changed = Signal()

    def __init__(self, repository, job_id: int, parent=None):
        super().__init__(parent)
        self.repository = repository
        self.job = repository.get_job_by_id(job_id)
        if self.job is None:
            raise ValueError('Oferta inexistente')
        self.setWindowTitle('Detalle de oferta · JobTracker')
        self.resize(720, 720)
        layout = QVBoxLayout(self)
        title = heading(self.job['title'])
        title.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(QLabel(self.job['company']))
        if self.job.get('excluded'):
            banner = QLabel('EXCLUIDA\n' + (self.job.get('exclusion_reason') or ''))
            banner.setTextFormat(Qt.TextFormat.PlainText)
            banner.setWordWrap(True)
            banner.setStyleSheet('color: #a52a2a; font-weight: bold;')
            layout.addWidget(banner)
        form = QFormLayout()
        form.addRow('Clasificación', QLabel(self.job.get('classification') or 'Pendiente de analizar'))
        for label, key in [('Score','score'),('Ubicación','location'),('Modalidad','modality'),
                           ('Experiencia','experience_level'),('Departamento','department'),('Marca','brand'),
                           ('Categoría','category'),('Jornada / contrato','employment_type'),('Perfil profesional','professional_profile'),
                           ('Línea de servicio','service_line'),('Área de estudio','study_area'),
                           ('Fuente','source_name'),('Publicación','published_date'),
                           ('Descubrimiento','discovered_date'),('URL','url')]:
            raw = self.job[key]
            value = QLabel(str(raw if raw is not None and raw != '' else 'No disponible'))
            value.setTextFormat(Qt.TextFormat.PlainText)
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(label, value)
        remote = self.job.get('remote')
        form.addRow('Teletrabajo (portal)', QLabel('No disponible' if remote is None else 'Sí' if remote else 'No'))
        form.addRow('Datos', QLabel('DATOS DE PRUEBA' if self.job['is_test_data'] else 'Oferta real'))
        form.addRow('Registro', QLabel('Candidatura general' if self.job.get('general_application') else 'Vacante'))
        self.status = QComboBox()
        self.status.addItems(STATUSES)
        self.status.setCurrentText(self.job['status'])
        self.status.currentTextChanged.connect(self.save_status)
        state_row = QHBoxLayout()
        state_row.addWidget(QLabel('Estado'))
        state_row.addWidget(self.status, 1)
        layout.addLayout(state_row)
        metadata = QWidget()
        metadata.setLayout(form)
        description = QTextBrowser()
        description.setPlainText(self.job['description'] or 'Descripción no disponible')
        tabs = QTabWidget()
        tabs.addTab(description, 'Descripción')
        self.compatibility = QTextBrowser()
        details = json.loads(self.job['score_details']) if self.job.get('score_details') else None
        if details:
            lines = [f"Compatibilidad: {self.job['score']}/100", self.job['classification'],
                     'Índice de reglas; no es una probabilidad de contratación.']
            if self.job['excluded']:
                reasons = details.get('facts', {}).get('exclusion_reasons') or [self.job['exclusion_reason']]
                lines = ['EXCLUIDA', 'Motivos:', *['• ' + reason for reason in reasons],
                         'El desglose interno no es una recomendación de candidatura.']
            for heading_text, key in [('Puntos positivos', 'positive_signals'), ('Advertencias', 'warnings'),
                                      ('Requisitos incumplidos', 'unmet_requirements')]:
                lines.extend(['', heading_text, *['• ' + value for value in details[key]]])
                if not details[key]:
                    lines.append('Ninguno detectado')
            if self.job['excluded']:
                lines.extend(['', 'Motivo de exclusión', self.job['exclusion_reason'],
                              'El score final se fija en 0 por exclusión. El desglose muestra la evaluación previa.'])
            lines.extend(['', 'Desglose'])
            labels = {'experience': 'Experiencia', 'education': 'Formación', 'role': 'Puesto',
                      'location': 'Ubicación', 'junior_signals': 'Junior', 'technology': 'Tecnología'}
            for key, label in labels.items():
                lines.append(f"{label}: {details['score_breakdown'][key]}/{details['weights'][key]}")
            lines.append(f"Penalizaciones: {details['score_breakdown']['penalties']}")
            for name, amount in details['penalties'].items():
                label = {'one_unmet': 'Un requisito obligatorio pendiente', 'english_b2': 'Inglés B2',
                         'english_high': 'Inglés alto', 'ambiguous_experience': 'Experiencia ambigua',
                         'unclear_location': 'Ubicación o modalidad poco clara'}.get(name, name)
                lines.append(f'• {label}: -{amount}')
            lines.extend(['', f"Motor {details['engine_version']} · Perfil {details['profile_hash']}"])
            self.compatibility.setPlainText('\n'.join(lines))
        else:
            self.compatibility.setPlainText('Pendiente de analizar. Pulsa Recalcular compatibilidad en Ofertas.')
        tabs.addTab(self.compatibility, 'Compatibilidad')
        metadata_scroll = QScrollArea()
        metadata_scroll.setWidgetResizable(True)
        metadata_scroll.setWidget(metadata)
        tabs.addTab(metadata_scroll, 'Datos de la oferta')
        layout.addWidget(tabs, 1)
        self.seen_button = QPushButton('Marcar como vista')
        self.seen_button.setEnabled(bool(self.job['is_new']))
        self.seen_button.clicked.connect(self.mark_seen)
        layout.addWidget(self.seen_button)
        self.open_button = QPushButton('Abrir oferta original')
        self.open_button.setEnabled(valid_url(self.job['url']))
        self.open_button.clicked.connect(lambda: open_url(self, self.job['url']))
        layout.addWidget(self.open_button)
        application_actions = QHBoxLayout()
        self.cv_sent_button = QPushButton('CV ENVIADO')
        self.cv_sent_button.setToolTip('Registrar que ya has enviado tu CV; no envía ninguna candidatura.')
        self.cv_sent_button.setEnabled(self.job['status'] != 'CV enviado')
        self.cv_sent_button.clicked.connect(lambda: self.status.setCurrentText('CV enviado'))
        self.discard_button = QPushButton('Descartar')
        self.discard_button.setToolTip('Marcar como descartada sin borrar la oferta.')
        self.discard_button.setEnabled(self.job['status'] != 'Descartada')
        self.discard_button.clicked.connect(lambda: self.status.setCurrentText('Descartada'))
        application_actions.addWidget(self.cv_sent_button)
        application_actions.addWidget(self.discard_button)
        layout.addLayout(application_actions)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText('Cerrar')
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @guarded
    def mark_seen(self):
        self.repository.mark_seen(self.job['id'])
        self.job['is_new'] = 0
        self.seen_button.setEnabled(False)
        self.changed.emit()

    @guarded
    def save_status(self, status: str):
        try:
            self.repository.update_job_status(self.job['id'], status)
        except Exception:
            self.status.blockSignals(True)
            self.status.setCurrentText(self.job['status'])
            self.status.blockSignals(False)
            raise
        self.job['status'] = status
        self.job['is_new'] = status == 'Nueva'
        self.seen_button.setEnabled(self.job['is_new'])
        self.cv_sent_button.setEnabled(status != 'CV enviado')
        self.discard_button.setEnabled(status != 'Descartada')
        self.changed.emit()
