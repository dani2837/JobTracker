import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator
from app.database.schema import SCHEMA
from app.database.migrations import migrate
from app.database.scoring_migration import migrate_scoring
from app.database.phase4_migration import migrate_phase4

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = None
        try:
            connection = sqlite3.connect(self.path, timeout=5)
            connection.row_factory = sqlite3.Row
            connection.execute('PRAGMA foreign_keys=ON')
            with connection:
                yield connection
        except sqlite3.Error:
            logger.exception('Error de base de datos')
            raise
        finally:
            if connection is not None:
                connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        logger.info('Inicialización de base de datos: %s', self.path)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            migrate(connection, self.path)
        with self.connect() as connection:
            migrate_scoring(connection, self.path)
        with self.connect() as connection:
            migrate_phase4(connection, self.path)
        logger.info('Tablas creadas o verificadas')
