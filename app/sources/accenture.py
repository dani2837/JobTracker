"""Búsqueda pública de Accenture: JSON completo, sin usar resúmenes generados."""
import json
from urllib.parse import parse_qs, urlsplit
from app.sources.base import NormalizedJob, ScanResult, SourceError
from app.sources.public_http import PublicHttpSource, official_url, plain_html, remote_value

PORTAL = 'https://www.accenture.com/es-es/careers/jobsearch'
ENDPOINT = 'https://www.accenture.com/api/accenture/elastic/findjobs'


def parse_job(row):
    reference = row.get('requisitionId')
    title = row.get('title')
    url = official_url(PORTAL, (row.get('jobDetailUrl') or '').replace('{0}', 'es-es'), '/es-es/careers/jobdetails')
    if not reference or not title or not parse_qs(urlsplit(url).query).get('id', [''])[0].startswith(reference + '_'):
        raise SourceError('Accenture: referencia o ficha inválida')
    description = plain_html(row.get('jobDescription'))
    requirements = plain_html(row.get('qualification'))
    if not description or 'qualification' not in row:
        raise SourceError('Accenture: descripción/requisitos incompletos')
    location = row.get('location')
    if not isinstance(location, list):
        raise SourceError('Accenture: formato de ubicación cambiado')
    mode = row.get('remoteType')
    return NormalizedJob(external_id=reference, title=title, company='Accenture',
        url=url, source_name='Accenture', source_url=PORTAL,
        location=', '.join(location) or None, modality=mode, remote=remote_value(mode),
        description=description + ('\nRequisitos\n' + requirements if requirements else ''),
        # updateDate es modificación, no publicación. El texto relativo no se inventa como fecha.
        published_date=None, experience_level='; '.join(filter(None, [row.get('jobTypeDescription'),
            (str(row['yearsOfExperience'])+' años de experiencia') if row.get('yearsOfExperience') else None])) or None,
        professional_profile=row.get('careerLevel'), employment_type=row.get('employeeType'),
        department=row.get('businessArea'))


class AccentureSource(PublicHttpSource):
    name = company = 'Accenture'
    url = PORTAL

    def fetch_jobs(self):
        jobs, seen, total = [], set(), None
        with self.client() as client:
            for page in range(1, self.options.max_pages + 1):
                form = dict(startIndex=(page-1)*12, maxResultSize=12, jobKeyword='', jobCountry='España',
                    jobLanguage='es', countrySite='es-es', sortBy=1, searchType='vectorSearch',
                    enableQueryBoost='true', minScore='0.6', getFeedbackJudgmentEnabled='true',
                    useCleanEmbedding='true', score='true', totalHits='true', debugQuery='false', jobFilters='[]')
                payload = json.loads(self.get(client, ENDPOINT, form=form))
                count = payload['totalHits']['total']
                if payload.get('message') != 'Success' or payload['totalHits'].get('overMaxHits') not in ('False', False):
                    raise SourceError('Accenture: resultados incompletos')
                if not isinstance(count, int) or count < 0 or (total is not None and total != count):
                    raise SourceError('Accenture: contador inestable')
                total = count
                rows = payload['data']
                if len(rows) != min(12, total-len(jobs)):
                    raise SourceError('Accenture: página incompleta')
                for row in rows:
                    job = parse_job(row)
                    if job.external_id in seen:
                        raise SourceError('Accenture: referencia repetida entre páginas')
                    seen.add(job.external_id); jobs.append(job)
                self.page_progress(page, len(rows))
                if len(jobs) == total:
                    return ScanResult(tuple(jobs), page, total, True)
        raise SourceError('Accenture: MAX_PAGES alcanzado')
