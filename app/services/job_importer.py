import logging
import hashlib
from dataclasses import replace
from datetime import date
from threading import Event
from app.database.repositories import CompanyRepository, JobRepository, SourceRunRepository
from app.sources.base import BaseSource, ScanCancelled, SourceError

logger = logging.getLogger(__name__)


class JobImporter:
    def __init__(self, db, source: BaseSource, *, cancel: Event | None = None, today: date | None = None, scorer=None):
        self.source = source
        self.jobs = JobRepository(db)
        self.companies = CompanyRepository(db)
        self.runs = SourceRunRepository(db)
        self.cancel = cancel or Event()
        self.today = today
        self.scorer = scorer

    def check_cancel(self):
        if self.cancel.is_set():
            raise ScanCancelled('Actualización cancelada; se conservan los datos guardados')

    def run(self) -> dict:
        multi_company = getattr(self.source, 'multi_company', False)
        run_id = self.runs.start(self.source.name)
        logger.info('%s scan started (run %s)', self.source.name, run_id)
        try:
            self.check_cancel()
            companies = [c for c in self.companies.get_companies()
                         if c['name'].strip().casefold() == self.source.company.strip().casefold()]
            if not multi_company and (len(companies) != 1 or not companies[0]['enabled']):
                raise SourceError(f'Activa {self.source.company} en la pantalla Empresas para actualizar')
            scan = self.source.fetch_jobs()
            # Solo si el portal no aporta referencia; nunca fusionar dos IDs oficiales
            # distintos por compartir título o ciudad.
            normalized = []
            for job in scan.jobs:
                if not job.external_id:
                    key = '|'.join((job.company.casefold(), job.title.casefold(), (job.location or '').casefold()))
                    job = replace(job, external_id='fallback-' + hashlib.sha256(key.encode()).hexdigest()[:24])
                normalized.append(job)
            scan = replace(scan, jobs=tuple(normalized))
            self.check_cancel()
            identifiers = {job.external_id for job in scan.jobs}
            if not scan.complete or len(identifiers) != len(scan.jobs) or scan.total_found != len(scan.jobs):
                raise SourceError('Escaneo incompleto o con duplicados; no se modifican las ofertas')
            if any(job.source_name != self.source.name or not job.company.strip() or
                   (not multi_company and job.company != self.source.company) for job in scan.jobs):
                raise SourceError('El escaneo contiene ofertas de otra fuente')
            result = self.jobs.import_scan(self.source, scan, run_id, today=self.today or date.today(),
                                          check_cancel=self.check_cancel, scorer=self.scorer)
            logger.info('%s: total=%s nuevas=%s conocidas=%s fuera de 60 días=%s', self.source.name,
                        result['total_found'], result['new_jobs'], result['updated_jobs'], result['excluded_jobs'])
            return result
        except Exception as error:
            logger.exception('%s scan failed', self.source.name)
            try:
                self.runs.fail(run_id, str(error))
            except Exception:
                logger.exception('No se pudo registrar el fallo de la actualización %s', run_id)
            raise
