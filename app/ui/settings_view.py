from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QCheckBox, QFormLayout, QLabel, QVBoxLayout, QWidget, QHBoxLayout, QPushButton, QSpinBox, QScrollArea
from copy import deepcopy
from app import __version__
from app.config.settings import LOG_PATH
from app.ui.common import guarded, heading
from app.config.profile import load_profile, PROFILE_PATH, save_profile, search_preferences


class SettingsView(QWidget):
    changed = Signal()
    recalculate_requested = Signal()

    def __init__(self, settings, db_path, log_path=LOG_PATH):
        super().__init__()
        self.settings = settings
        layout = QVBoxLayout(self)
        layout.addWidget(heading('Configuración'))
        form = QFormLayout()
        for title, value in [('Base de datos',str(db_path)),('Logs',str(log_path)),('Versión',__version__)]:
            label = QLabel(value)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(title, label)
        self.options = {}
        for key, title in [('show_discarded','Mostrar ofertas descartadas'),('confirm_close','Confirmar antes de cerrar')]:
            checkbox = QCheckBox(title)
            checkbox.setChecked(settings.get(key))
            checkbox.toggled.connect(lambda value, key=key: self.save(key, value))
            self.options[key] = checkbox
            form.addRow(checkbox)
        layout.addLayout(form)
        note = QLabel('Las preferencias se guardan inmediatamente en este equipo.')
        note.setWordWrap(True)
        layout.addWidget(note)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        panel = QWidget()
        profile_layout = QVBoxLayout(panel)
        profile_layout.addWidget(heading('Mi perfil de búsqueda'))
        self.modalities = {}
        self.categories = {}
        for title, choices, target in [
            ('Modalidades aceptadas', [('onsite','Presencial'), ('hybrid','Híbrido'), ('remote','Remoto')], self.modalities),
            ('Categorías de puesto', [('development','Desarrollo'), ('systems','Sistemas'), ('support','Soporte'),
                ('qa','QA'), ('data_cloud','Datos / cloud'), ('other_it','Otras funciones IT / consultoría')], self.categories)]:
            profile_layout.addWidget(QLabel(title))
            row = QHBoxLayout()
            for key, label in choices:
                target[key] = QCheckBox(label)
                row.addWidget(target[key])
            profile_layout.addLayout(row)
        self.seville = QCheckBox('Sevilla y provincia')
        self.remote_spain = QCheckBox('Remoto España')
        places = QHBoxLayout()
        places.addWidget(self.seville)
        places.addWidget(self.remote_spain)
        profile_layout.addLayout(places)
        profile_form = QFormLayout()
        self.max_experience = QSpinBox()
        self.max_experience.setRange(0, 50)
        self.max_experience.setSuffix(' años')
        self.max_age = QSpinBox()
        self.max_age.setRange(1, 60)
        self.max_age.setSuffix(' días')
        self.exclude_university = QCheckBox('Excluir universidad obligatoria')
        profile_form.addRow('Experiencia máxima exigida', self.max_experience)
        profile_form.addRow('Antigüedad máxima', self.max_age)
        profile_form.addRow(self.exclude_university)
        profile_layout.addLayout(profile_form)
        info = QLabel('Antigüedad por fecha de publicación (máximo importado: 60 días). Sin fecha, se conserva la oferta con advertencia. '
                      'Las modalidades desconocidas mantienen la evaluación actual. No se modifican los demás requisitos del scoring.')
        info.setWordWrap(True)
        profile_layout.addWidget(info)
        buttons = QHBoxLayout()
        self.save_profile_button = QPushButton('Guardar perfil')
        self.save_recalculate_button = QPushButton('Guardar y recalcular ofertas')
        self.restore_profile_button = QPushButton('Restaurar perfil por defecto')
        for button in (self.save_profile_button, self.save_recalculate_button, self.restore_profile_button):
            buttons.addWidget(button)
        profile_layout.addLayout(buttons)
        self.profile_label = QLabel()
        self.profile_label.setWordWrap(True)
        profile_layout.addWidget(self.profile_label)
        profile_layout.addStretch()
        scroll.setWidget(panel)
        layout.addWidget(scroll, 1)
        self.save_profile_button.clicked.connect(lambda: self.save_search_profile(False))
        self.save_recalculate_button.clicked.connect(lambda: self.save_search_profile(True))
        self.restore_profile_button.clicked.connect(self.restore_profile)
        self.refresh_profile()

    def refresh_profile(self):
        self.populate_profile(load_profile())

    def populate_profile(self, profile):
        self.profile = deepcopy(profile)
        prefs = search_preferences(profile)
        for key, checkbox in self.modalities.items():
            checkbox.setChecked(key in prefs['modalities'])
        for key, checkbox in self.categories.items():
            checkbox.setChecked(key in prefs['categories'])
        self.seville.setChecked(prefs['seville'])
        self.remote_spain.setChecked(prefs['remote_spain'])
        self.max_experience.setValue(profile['max_required_experience_years'])
        self.max_age.setValue(prefs['max_age_days'])
        self.exclude_university.setChecked(prefs['exclude_university'])

    def set_profile_busy(self, busy):
        for button in (self.save_profile_button, self.save_recalculate_button, self.restore_profile_button):
            button.setEnabled(not busy)

    @guarded
    def save_search_profile(self, recalculate=False):
        profile = deepcopy(self.profile)
        profile['search_preferences'] = dict(
            modalities=[key for key, box in self.modalities.items() if box.isChecked()],
            categories=[key for key, box in self.categories.items() if box.isChecked()],
            seville=self.seville.isChecked(), remote_spain=self.remote_spain.isChecked(),
            exclude_university=self.exclude_university.isChecked(), max_age_days=self.max_age.value())
        profile['max_required_experience_years'] = self.max_experience.value()
        profile['allow_remote'] = self.modalities['remote'].isChecked() and self.remote_spain.isChecked()
        save_profile(profile)
        self.profile = profile
        self.profile_label.setText('Perfil guardado. Recalcula para aplicarlo a las ofertas existentes.')
        if recalculate:
            self.profile_label.setText('Perfil guardado. Recalculando desde SQLite…')
            self.recalculate_requested.emit()

    @guarded
    def restore_profile(self):
        profile = load_profile(PROFILE_PATH)
        save_profile(profile)
        self.populate_profile(profile)
        self.profile_label.setText('Perfil por defecto restaurado y guardado. Recalcula para aplicarlo a las ofertas existentes.')

    @guarded
    def save(self, key, value):
        try:
            self.settings.set(key, value)
        except Exception:
            checkbox = self.options[key]
            checkbox.blockSignals(True)
            checkbox.setChecked(self.settings.get(key))
            checkbox.blockSignals(False)
            raise
        self.changed.emit()
