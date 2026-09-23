"""Bizneo: listado HTML público /jobs?page=N y fichas /jobs/<id oficial>."""
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
from app.sources.base import NormalizedJob, ScanResult, SourceError
from app.sources.public_http import PublicHttpSource, text, plain_html, official_url, parse_date, remote_value

PORTAL = 'https://jobs.izertis.com/jobs'


def parse_listing(html):
    soup = BeautifulSoup(html, 'html.parser')
    rows = []
    for card in soup.select('a.job-card'):
        url = official_url(PORTAL, card.get('href',''), '/jobs/')
        title = text(card.select_one('.title'))
        if not title:
            raise SourceError('Izertis: tarjeta sin título')
        rows.append({'external_id': urlsplit(url).path.rstrip('/').split('/')[-1], 'url': url, 'title': title})
    if not rows:
        raise SourceError('Izertis: listado vacío o formato cambiado; se conservan las ofertas')
    next_link = soup.select_one('.pagination a.next, .pagination a[rel="next"]')
    return rows, official_url(PORTAL, next_link['href']) if next_link else None


def parse_detail(html, row):
    soup = BeautifulSoup(html, 'html.parser')
    detail = soup.select_one('#job-details')
    if detail is None:
        raise SourceError('Izertis: detalle no reconocido')
    title = text(detail.select_one('h1'))
    description = plain_html(detail.select_one('.general-content'))
    if not title or not description:
        raise SourceError('Izertis: falta título o descripción')
    fields = {tag['title']: text(tag) for tag in detail.select('aside div[title]')}
    time = detail.select_one('time[datetime]')
    mode = fields.get('Modalidad de trabajo')
    general = title.casefold().startswith(('trabaja con nosotros', 'candidatura espontánea', 'candidatura espontanea'))
    return NormalizedJob(external_id=row['external_id'], title=title, company='Izertis', url=row['url'],
        source_name='Izertis', source_url=PORTAL, location=fields.get('Ubicación'), modality=mode,
        remote=remote_value(mode), description=description, published_date=parse_date(time['datetime']) if time else None,
        department=fields.get('Departamento'), category=fields.get('Categoría'),
        employment_type=fields.get('Jornada laboral'), professional_profile=fields.get('Nivel profesional'),
        general_application=general)


class IzertisSource(PublicHttpSource):
    name = company = 'Izertis'
    url = PORTAL

    def fetch_jobs(self):
        rows, seen, visited = [], set(), set()
        url = self.url
        with self.client() as client:
            for page in range(1, self.options.max_pages + 1):
                if url in visited:
                    raise SourceError('Izertis: bucle de paginación')
                visited.add(url)
                batch, next_url = parse_listing(self.get(client, url))
                self.page_progress(page, len(batch))
                for row in batch:
                    if row['external_id'] in seen:
                        raise SourceError('Izertis: página/oferta repetida')
                    seen.add(row['external_id'])
                    rows.append(row)
                if not next_url:
                    break
                url = next_url
            else:
                raise SourceError('Izertis: MAX_PAGES alcanzado')
            jobs = []
            for index, row in enumerate(rows, 1):
                self.progress(f'{self.name} · detalle {index}/{len(rows)}')
                jobs.append(parse_detail(self.get(client, row['url']), row))
        return ScanResult(tuple(jobs), page, len(jobs), True)
