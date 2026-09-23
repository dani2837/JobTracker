import logging
from threading import Event
from PySide6.QtCore import QThread, Signal
from app.services.source_update import update_all_jobs


class UpdateWorker(QThread):
    progress = Signal(str)
    source_progress = Signal(object)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, db, parent=None, update=update_all_jobs, error_message=None):
        super().__init__(parent)
        self.db = db
        self.cancel = Event()
        self.update = update
        self.error_message = error_message

    def run(self):
        try:
            def report(message):
                self.progress.emit(message)
            report.source_progress = self.source_progress.emit
            result = self.update(self.db, self.cancel, report)
            self.succeeded.emit(result)
        except Exception:
            logging.getLogger(__name__).exception('Error al actualizar ofertas')
            self.failed.emit(self.error_message or 'No se ha podido completar la actualización. Las ofertas guardadas siguen disponibles. '
                             'Comprueba la conexión y que la empresa esté activa. Consulta el log para más detalles.')
