"""API pública de publicaciones SmartRecruiters enlazada por T-Systems España."""
import json
from app.sources.base import NormalizedJob, ScanResult, SourceError
from app.sources.public_http import PublicHttpSource, official_url, plain_html, parse_date

PORTAL = 'https://careers.smartrecruiters.com/T-SystemsIberia'
API = 'https://api.smartrecruiters.com/v1/companies/T-SystemsIberia/postings'


def parse_job(row, reference):
    if row.get('id') != reference or row.get('company', {}).get('identifier') != 'T-SystemsIberia':
        raise SourceError('T-Systems: identidad de ficha incorrecta')
    sections = row.get('jobAd', {}).get('sections', {})
    if not row.get('name') or not sections.get('jobDescription', {}).get('text') or 'qualifications' not in sections:
        raise SourceError('T-Systems: ficha incompleta')
    description = '\n'.join((section.get('title') or '') + '\n' + (plain_html(section.get('text')) or '')
        for section in sections.values())
    loc = row.get('location', {})
    mode = loc.get('hybridDescription') or ('Hybrid' if loc.get('hybrid') else 'Remote' if loc.get('remote') else None)
    return NormalizedJob(external_id=reference, title=row['name'], company='T-Systems',
        url=official_url('https://jobs.smartrecruiters.com', row.get('postingUrl', ''), '/T-SystemsIberia/'+reference+'-'),
        source_name='T-Systems', source_url=PORTAL, location=loc.get('fullLocation') or loc.get('city'),
        modality=mode, remote=loc.get('remote'), description=description,
        published_date=parse_date(row.get('releasedDate')),
        experience_level=row.get('experienceLevel', {}).get('label'),
        employment_type=row.get('typeOfEmployment', {}).get('label'),
        department=row.get('department', {}).get('label'),
        general_application='talent community' in row['name'].casefold())


class TSystemsSource(PublicHttpSource):
    name = company = 'T-Systems'
    url = API

    def fetch_jobs(self):
        listings, seen, total = [], set(), None
        with self.client() as client:
            for page in range(1, self.options.max_pages + 1):
                payload = json.loads(self.get(client, f'{API}?limit=100&offset={len(listings)}'))
                count = payload['totalFound']
                if not isinstance(count, int) or count < 0 or (total is not None and count != total) or payload['offset'] != len(listings):
                    raise SourceError('T-Systems: paginación inconsistente')
                total = count
                rows = payload['content']
                if len(rows) != min(100, total-len(listings)):
                    raise SourceError('T-Systems: página incompleta')
                for row in rows:
                    reference = row.get('id')
                    if not reference or reference in seen:
                        raise SourceError('T-Systems: referencia ausente/repetida')
                    seen.add(reference); listings.append(row)
                self.page_progress(page, len(rows))
                if len(listings) == total:
                    break
            else:
                raise SourceError('T-Systems: MAX_PAGES alcanzado')
            jobs = []
            for row in listings:
                ref = official_url(API, row['ref'], '/v1/companies/T-SystemsIberia/postings/')
                jobs.append(parse_job(json.loads(self.get(client, ref)), row['id']))
        return ScanResult(tuple(jobs), page, total, True)
