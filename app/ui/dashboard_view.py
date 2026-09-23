from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget
from app.ui.common import heading, make_table, fill_table
from app.database.scoring_repository import ScoringRepository


class DashboardView(QWidget):
    def __init__(self, repository, settings):
        super().__init__()
        self.repository, self.settings = repository, settings
        layout = QVBoxLayout(self)
        layout.addWidget(heading('Resumen'))
        self.source_summary = QLabel()
        self.source_summary.setWordWrap(True)
        layout.addWidget(self.source_summary)
        grid = QGridLayout()
        self.values = {}
        labels = [('total','Total de ofertas'),('nuevas','Ofertas nuevas'),
                  ('prioritarias','Candidaturas prioritarias · ≥90'),
                  ('interesantes','Muy interesantes · 75–89'),('revisar','Para revisar · 60–74'),
                  ('baja','Baja prioridad · 40–59'), ('excluded','Excluidas'), ('hidden','Ocultar · <40')]
        for index, (key, title) in enumerate(labels):
            card = QFrame()
            card.setObjectName('card')
            card_layout = QVBoxLayout(card)
            caption = QLabel(title)
            caption.setWordWrap(True)
            card_layout.addWidget(caption)
            value = QLabel('0')
            value.setObjectName('metric')
            card_layout.addWidget(value)
            self.values[key] = value
            grid.addWidget(card, index // 3, index % 3)
        layout.addLayout(grid)
        layout.addWidget(heading('Mejores oportunidades'))
        layout.addWidget(QLabel('Ofertas no excluidas. Índice de compatibilidad basado en reglas locales.'))
        self.table = make_table(['Score','Puesto','Empresa','Ubicación','Modalidad','Estado','Fuente'])
        for index, width in enumerate([70,270,150,160,110,150]):
            self.table.setColumnWidth(index, width)
        self.table.sortItems(0, Qt.SortOrder.DescendingOrder)
        layout.addWidget(self.table, 1)

    def refresh(self):
        visible = self.settings.get('show_discarded')
        counts = self.repository.get_source_counts(visible)
        self.source_summary.setText(self.repository.daily_summary() + '\n' + f"{counts['real']} reales · {counts['test']} datos de prueba · "
                                    f"{counts['unscored']} pendientes de analizar")
        new_by_source = self.repository.get_new_by_source(visible)
        if new_by_source:
            self.source_summary.setText(self.source_summary.text() + '\nMarcadas nuevas: ' +
                ' · '.join(f'{name}: {count}' for name, count in new_by_source.items()))
        for key, value in self.repository.get_dashboard_stats(visible).items():
            self.values[key].setText(str(value))
        for key, value in ScoringRepository(self.repository.db).counts(visible).items():
            self.values[key].setText(str(value))
        fill_table(self.table, self.repository.get_top_jobs(visible),
                   ['score','title','company','location','modality','status','source_label'])
