"""Vacantes públicas Ayesa Engineering: HTML paginado y requisitos completos."""
import re
from datetime import date
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
from app.sources.base import NormalizedJob, ScanResult, SourceError
from app.sources.public_http import PublicHttpSource, official_url, plain_html, text, remote_value

PORTAL = 'https://www.ayesa.com/ofertas-trabajo/page/1/'
MONTHS = 'enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre'.split()


def parse_listing(html, url):
    soup = BeautifulSoup(html, 'html.parser')
    links = [official_url(PORTAL, a['href'], '/ofertas-trabajo/oferta/') for a in soup.select('a[href*="/ofertas-trabajo/oferta/"]')]
    if not links:
        raise SourceError('Ayesa: listado vacío o estructura no reconocida; no se inactivan ofertas')
    if len(links) != len(set(links)):
        raise SourceError('Ayesa: ofertas repetidas')
    following = soup.select_one('a.next.page-numbers')
    return links, official_url(PORTAL, following['href'], '/ofertas-trabajo/page/') if following else None


def parse_job(html, url):
    soup = BeautifulSoup(html, 'html.parser')
    title = text(soup.select_one('.hero-title'))
    dates = [text(x) for x in soup.select('.hero-date .date-info')]
    body = plain_html(soup.select_one('.description-text'))
    requirements = plain_html(soup.select_one('.requirements-text'))
    if not title or len(dates) != 3 or not (body or requirements):
        raise SourceError('Ayesa: ficha incompleta')
    match = re.fullmatch(r'(\d{1,2}) (\w+), (\d{4})', dates[2].casefold())
    if not match or match[2] not in MONTHS:
        raise SourceError('Ayesa: fecha no reconocida')
    published = date(int(match[3]), MONTHS.index(match[2])+1, int(match[1]))
    fields = dict(re.findall(r'(Ubicación|Modalidad|Contrato|Sección)\s*\[([^\]]+)\]', body or ''))
    mode = fields.get('Modalidad')
    return NormalizedJob(external_id=urlsplit(url).path.rstrip('/').split('/')[-1], title=title,
        company='Ayesa', url=url, source_name='Ayesa', source_url=PORTAL, location=dates[0],
        modality=mode, remote=remote_value(mode), published_date=published,
        description=(body or '')+('\nRequisitos\n'+requirements if requirements else ''),
        employment_type=fields.get('Contrato'), department=fields.get('Sección'))


class AyesaSource(PublicHttpSource):
    name = company = 'Ayesa'
    url = PORTAL

    def fetch_jobs(self):
        url, visited, links = PORTAL, set(), []
        with self.client() as client:
            for page in range(1, self.options.max_pages+1):
                if url in visited:
                    raise SourceError('Ayesa: bucle de paginación')
                visited.add(url)
                rows, following = parse_listing(self.get(client, url), url)
                if set(rows).intersection(links):
                    raise SourceError('Ayesa: ofertas repetidas entre páginas')
                links.extend(rows); self.page_progress(page, len(rows))
                if not following:
                    break
                url = following
            else:
                raise SourceError('Ayesa: MAX_PAGES alcanzado')
            jobs = tuple(parse_job(self.get(client, link), link) for link in links)
            if len({j.external_id for j in jobs}) != len(jobs):
                raise SourceError('Ayesa: referencias duplicadas')
        return ScanResult(jobs, page, len(jobs), True)
