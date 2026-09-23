import json
from collections import Counter
from datetime import datetime, timezone


def write_score(connection, job_id: int, result):
    connection.execute('''UPDATE jobs SET score=?,classification=?,excluded=?,exclusion_reason=?,score_details=?,scored_at=?
        WHERE id=?''', (result.score, result.classification, result.excluded, result.exclusion_reason,
        json.dumps(result.to_dict(), ensure_ascii=False), datetime.now(timezone.utc).isoformat(), job_id))


class ScoringRepository:
    def __init__(self, db):
        self.db = db

    def recalculate(self, engine, cancel, only_unscored=False):
        from app.sources.base import ScanCancelled
        counts = Counter()
        with self.db.connect() as connection:
            rows = connection.execute('SELECT * FROM jobs WHERE (?=0 OR score_details IS NULL)', (only_unscored,)).fetchall()
        evaluated = []
        for row in rows:
            if cancel.is_set():
                raise ScanCancelled('Recálculo cancelado')
            evaluated.append((dict(row), engine.evaluate(dict(row))))
        with self.db.connect() as connection:
            # Calcular fuera de la transacción evita bloquear cambios manuales.
            # Si una importación alteró el contenido, se evalúa la fila más reciente.
            connection.execute('BEGIN IMMEDIATE')
            inputs = ('title', 'description', 'location', 'modality', 'remote', 'experience_level', 'source_url',
                      'employment_type', 'professional_profile', 'general_application')
            for previous, result in evaluated:
                if cancel.is_set():
                    raise ScanCancelled('Recálculo cancelado')
                current = connection.execute('SELECT * FROM jobs WHERE id=?', (previous['id'],)).fetchone()
                if current is None:
                    continue
                if any(current[key] != previous[key] for key in inputs):
                    result = engine.evaluate(dict(current))
                write_score(connection, current['id'], result)
                counts[result.classification] += 1
            if cancel.is_set():
                raise ScanCancelled('Recálculo cancelado')
        return {'processed': sum(counts.values()), 'distribution': dict(counts)}

    def counts(self, show_discarded=True):
        with self.db.connect() as connection:
            return dict(connection.execute('''SELECT COALESCE(SUM(excluded),0) AS excluded,
                COALESCE(SUM(classification='Ocultar'),0) AS hidden FROM jobs
                WHERE (? OR status != 'Descartada')''', (show_discarded,)).fetchone())
