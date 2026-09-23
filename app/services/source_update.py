"""Punto de composición: la UI solo necesita pedir una actualización."""
from app.services.job_importer import JobImporter
from app.sources.sopra_steria import SopraSteriaSource
from app.services.scoring.engine import ScoringEngine
from app.sources.izertis import IzertisSource
from app.sources.indra_minsait import IndraMinsaitSource
from app.sources.deloitte import DeloitteSource
from app.sources.accenture import AccentureSource
from app.sources.ayesa import AyesaSource
from app.sources.t_systems import TSystemsSource
from app.sources.phase6_html import EmergyaSource, IsotrolSource
from app.sources.infojobs import InfoJobsSource
from app.sources.tecnoempleo import TecnoempleoSource
from app.sources.base import ScanCancelled
from app.database.repositories import CompanyRepository, JobRepository


def update_jobs(db, cancel, progress):
    """Actualización individual de Sopra, compatible con las herramientas anteriores."""
    source = SopraSteriaSource(cancel=cancel, progress=progress)
    return JobImporter(db, source, cancel=cancel, scorer=ScoringEngine()).run()


def update_all_jobs(db, cancel, progress, *, sources=None):
    sources = sources if sources is not None else [factory(cancel=cancel, progress=progress) for factory in
        (SopraSteriaSource, IzertisSource, IndraMinsaitSource, DeloitteSource,
         AccentureSource, AyesaSource, TSystemsSource, EmergyaSource, IsotrolSource, InfoJobsSource, TecnoempleoSource)]
    results = []
    report_sources = getattr(progress, 'source_progress', lambda event: None)
    total_sources = len(sources)
    def report(source='', status='starting', error=None):
        report_sources(dict(source=source, status=status, processed=len(results), total=total_sources,
                            errors=sum(r.get('success') is False for r in results), error=error))
    report()
    engine = ScoringEngine()
    enabled = {c['name']: c['enabled'] for c in CompanyRepository(db).get_companies()}
    for source in sources:
        if cancel.is_set():
            raise ScanCancelled('Actualización cancelada; las fuentes terminadas se conservan')
        if not getattr(source, 'multi_company', False) and not enabled.get(source.company):
            results.append({'source': source.name, 'skipped': True, 'error': 'Empresa desactivada'})
            progress(f'{source.name} · omitida: empresa desactivada')
            report(source.name, 'skipped')
            continue
        report(source.name, 'running')
        progress(f'{source.name} · iniciando actualización…')
        try:
            result = JobImporter(db, source, cancel=cancel, scorer=engine).run()
            saved = [j for j in JobRepository(db).get_all_jobs() if j['source_name'] == source.name and not j['is_test_data'] and j['is_active']]
            result.update(source=source.name, success=True, excluded=sum(j['excluded'] for j in saved),
                          compatible=sum(not j['excluded'] for j in saved))
            results.append(result)
            progress(f'{source.name} ✓ · {result["new_jobs"]} nuevas · {result["updated_jobs"]} actualizadas')
            report(source.name, 'completed')
        except ScanCancelled:
            raise
        except Exception as error:
            results.append({'source': source.name, 'success': False, 'error': str(error)})
            progress(f'{source.name} · error: {error}. Continuando con la siguiente fuente.')
            report(source.name, 'error', str(error))
    totals = {key: sum(r.get(key,0) for r in results) for key in ('total_found','new_jobs','updated_jobs','excluded_jobs','excluded','compatible')}
    return {**totals, 'sources': results, 'errors': sum(r.get('success') is False for r in results)}
