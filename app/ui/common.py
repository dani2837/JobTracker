import logging
from functools import wraps
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QHeaderView, QLabel, QMessageBox,
                               QTableWidget, QTableWidgetItem)


def guarded(function):
    @wraps(function)
    def wrapped(self, *args, **kwargs):
        try:
            return function(self, *args, **kwargs)
        except Exception:
            logging.getLogger(__name__).exception('Error en %s', function.__name__)
            QMessageBox.critical(self, 'No se pudo completar la operación',
                                 'No se ha podido leer o guardar la información. '
                                 'Comprueba los permisos y el espacio disponible. '
                                 'Puedes volver a intentarlo. Consulta logs/jobtracker.log.')
    return wrapped


def heading(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName('heading')
    return label


def make_table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.verticalHeader().hide()
    table.verticalHeader().setDefaultSectionSize(40)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    table.horizontalHeader().setStretchLastSection(True)
    table.setSortingEnabled(True)
    return table


class ScoreItem(QTableWidgetItem):
    def __lt__(self, other):
        left = self.data(Qt.ItemDataRole.UserRole + 1)
        right = other.data(Qt.ItemDataRole.UserRole + 1)
        return (left if left is not None else -1) < (right if right is not None else -1)


def fill_table(table: QTableWidget, rows: list[dict], columns: list[str]) -> None:
    header = table.horizontalHeader()
    sort_column, sort_order = header.sortIndicatorSection(), header.sortIndicatorOrder()
    table.setSortingEnabled(False)
    table.setRowCount(len(rows))
    for row_index, row in enumerate(rows):
        for column_index, key in enumerate(columns):
            value = row.get(key)
            if key == 'source_label':
                value = 'Datos de prueba' if row.get('is_test_data') else row.get('source_name') or 'Sin fuente'
            if key in ('is_new', 'enabled', 'is_active'):
                value = 'Sí' if value else 'No'
            if value is None or value == '':
                value = '—'
            item = ScoreItem() if key == 'score' else QTableWidgetItem()
            if key == 'score':
                item.setData(Qt.ItemDataRole.UserRole + 1, row.get('score') if row.get('score') is not None else -1)
            item.setData(Qt.ItemDataRole.DisplayRole, value)
            item.setData(Qt.ItemDataRole.UserRole, row['id'])
            item.setToolTip('Pendiente de analizar' if key == 'score' and row.get('score') is None else str(value))
            table.setItem(row_index, column_index, item)
    table.setSortingEnabled(True)
    table.sortItems(sort_column, sort_order)


def selected_id(table: QTableWidget) -> int | None:
    selection = table.selectionModel().selectedRows()
    if not selection:
        return None
    return table.item(selection[0].row(), 0).data(Qt.ItemDataRole.UserRole)


def valid_url(url: str) -> bool:
    parsed = QUrl(url)
    return parsed.isValid() and parsed.scheme() in ('http', 'https') and bool(parsed.host())


def open_url(parent, url: str) -> None:
    if valid_url(url) and not QDesktopServices.openUrl(QUrl(url)):
        QMessageBox.warning(parent, 'No se pudo abrir el enlace', 'Comprueba el navegador predeterminado de Windows.')
