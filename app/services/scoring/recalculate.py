import logging
from threading import Event
from app.database.scoring_repository import ScoringRepository
from app.services.scoring.engine import ScoringEngine


def recalculate_all_jobs(db, cancel=None, progress=None, *, profile=None, only_unscored=False):
    logger = logging.getLogger(__name__)
    logger.info('Scoring started')
    try:
        if progress:
            progress('Recalculando compatibilidad desde los datos locales…')
        result = ScoringRepository(db).recalculate(ScoringEngine(profile), cancel or Event(), only_unscored)
        logger.info('Scoring: jobs processed=%s distribution=%s errors=0', result['processed'], result['distribution'])
        return result
    except Exception:
        logger.exception('Scoring failed; cambios revertidos')
        raise


if __name__ == '__main__':
    from app.config.settings import DATABASE_PATH
    from app.database.db import Database
    from app.main import configure_logging
    configure_logging()
    database = Database(DATABASE_PATH)
    database.initialize()
    recalculate_all_jobs(database)
