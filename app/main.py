import logging
from logging.handlers import RotatingFileHandler
import sys
from PySide6.QtWidgets import QApplication, QMessageBox
from app.config.settings import DATABASE_PATH, LOG_PATH, Settings
from app.database.db import Database
from app.services.seed_data import seed_database
from app.services.source_configuration import configure_sources
from app.ui.main_window import MainWindow
from app.services.scoring.recalculate import recalculate_all_jobs


def configure_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding='utf-8')
    logging.basicConfig(level=logging.INFO, handlers=[handler],
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s', force=True)


def main() -> int:
    application = QApplication(sys.argv)
    application.setApplicationName('JobTracker')
    application.setStyle('Fusion')
    try:
        configure_logging()
        logging.info('Inicio de aplicación')
        db = Database(DATABASE_PATH)
        db.initialize()
        seed_database(db)
        configure_sources(db)
        recalculate_all_jobs(db, only_unscored=True)
        settings = Settings()
        window = MainWindow(db, settings)
    except Exception:
        logging.exception('Error durante el inicio')
        QMessageBox.critical(None, 'No se pudo iniciar JobTracker',
            'Comprueba los permisos de data y logs y los archivos data/settings.json y app/config/profile.json. '
            'Consulta logs/jobtracker.log para más información.')
        return 1

    def exception_hook(exc_type, value, traceback):
        logging.error('Error inesperado', exc_info=(exc_type, value, traceback))
        QMessageBox.critical(window, 'Error inesperado',
            'No se pudo completar la operación. Consulta logs/jobtracker.log y vuelve a intentarlo.')

    sys.excepthook = exception_hook
    window.show()
    result = application.exec()
    logging.info('Aplicación finalizada: %s', result)
    return result


if __name__ == '__main__':
    raise SystemExit(main())
