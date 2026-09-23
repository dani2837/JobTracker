"""HTML/microdatos públicos de SAP SuccessFactors; configuración propia por portal."""
import re
from bs4 import BeautifulSoup
from app.sources.base import NormalizedJob, ScanResult, SourceError
from app.sources.public_http import PublicHttpSource, text, plain_html, official_url, parse_date, remote_value


def parse_listing(html, portal):
    soup = BeautifulSoup(html, 'html.parser')
    rows = {}
    for link in soup.select('a.jobTitle-link'):
        url = official_url(portal, link.get('href',''), '/job/')
        match = re.search(r'/(\d+)/?$', url)
        if not match or not text(link):
            raise SourceError('SuccessFactors: referencia o título no reconocido')
        ident = match[1]
        study = soup.select_one(f'#job-{ident}-desktop-section-customfield1-value')
        rows[ident] = {'external_id': ident, 'url': url, 'title': text(link),
                       'study_area': text(study)}
    label = text(soup.select_one('.paginationLabel')) or soup.get_text(' ', strip=True)
    count = re.search(r'Resultados\s+\d+\s*[–-]\s*\d+\s+de\s+(\d+)|Mostrando\s+\d+\s+a\s+\d+\s+de\s+(\d+)', label)
    return list(rows.values()), int(next(g for g in count.groups() if g)) if count else None


def parse_detail(html, row, source):
    soup = BeautifulSoup(html, 'html.parser')
    title = text(soup.select_one('[itemprop="title"]'))
    description = plain_html(soup.select_one('[itemprop="description"]'))
    if not title or not description:
        raise SourceError(f'{source.name}: ficha sin título o descripción')
    def prop(key):
        return text(soup.select_one(f'[data-careersite-propertyid="{key}"]'))
    def meta(key):
        tag = soup.select_one(f'meta[itemprop="{key}"]')
        return tag.get('content') or None if tag else None
    indra = source.name == 'Indra / Minsait'
    mode = prop('customfield4') if indra else None
    return NormalizedJob(external_id=row['external_id'], title=title, company=source.company,
        url=row['url'], source_name=source.name, source_url=source.url,
        location=meta('streetAddress'), modality=mode, remote=remote_value(mode), description=description,
        published_date=parse_date(meta('datePosted')), experience_level=prop('customfield3') if indra else prop('shifttype'),
        professional_profile=prop('customfield1') if indra else None,
        department=prop('customfield5') if indra else prop('dept'),
        service_line=prop('dept') if not indra else None,
        study_area=(prop('customfield1') or row.get('study_area')) if not indra else None)


class SuccessFactorsSource(PublicHttpSource):
    def listing_url(self, offset):
        raise NotImplementedError

    def fetch_jobs(self):
        rows, seen, total = [], set(), None
        with self.client() as client:
            for page in range(1, self.options.max_pages + 1):
                batch, advertised = parse_listing(self.get(client, self.listing_url(len(rows))), self.url)
                if total is None:
                    if advertised is None:
                        raise SourceError(f'{self.name}: no se reconoce el contador')
                    total = advertised
                elif advertised is not None and advertised != total:
                    raise SourceError(f'{self.name}: el contador cambió durante el escaneo')
                self.page_progress(page, len(batch))
                for row in batch:
                    if row['external_id'] in seen:
                        raise SourceError(f'{self.name}: página/oferta repetida')
                    seen.add(row['external_id'])
                    rows.append(row)
                if len(rows) == total:
                    break
                if not batch or len(rows) > total:
                    raise SourceError(f'{self.name}: paginación incompleta')
            else:
                raise SourceError(f'{self.name}: MAX_PAGES alcanzado')
            jobs = []
            for index, row in enumerate(rows, 1):
                self.progress(f'{self.name} · detalle {index}/{total}')
                jobs.append(parse_detail(self.get(client, row['url']), row, self))
        return ScanResult(tuple(jobs), page, len(jobs), True)
