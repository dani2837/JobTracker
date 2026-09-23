"""Listado público Sevilla (incluye remoto) y fichas HTML/JSON-LD, sin login."""
import json
import re
from datetime import datetime
import httpx

from bs4 import BeautifulSoup

from app.sources.base import NormalizedJob, ScanResult, SourceError
from app.sources.public_http import PublicHttpSource, official_url, parse_date, plain_html, text


class TecnoempleoSource(PublicHttpSource):
    name = company = 'Tecnoempleo'
    multi_company = True
    url = 'https://www.tecnoempleo.com/ofertas-trabajo/sevilla'

    def parse_listing(self, html, offset):
        soup = BeautifulSoup(html, 'html.parser')
        count = re.search(r'(\d+)-(\d+) de (\d+) Ofertas de Empleo', soup.get_text(' ', strip=True))
        if not count:
            raise SourceError('Tecnoempleo: listado o paginación no reconocidos')
        start, end, total = map(int, count.groups())
        rows = {}
        for link in soup.select('a[href*="/rf-"]'):
            url = official_url(self.url, link['href'])
            ident = re.search(r'/rf-([a-zA-Z0-9]+)$', url)
            if not ident or not text(link) or ident[1] in rows:
                raise SourceError('Tecnoempleo: referencia inválida o repetida')
            rows[ident[1]] = url
        if start != offset + 1 or end > total or end - start + 1 != len(rows) or not rows:
            raise SourceError('Tecnoempleo: página incompleta o repetida')
        return rows, total

    def parse_detail(self, html, ident, url):
        soup = BeautifulSoup(html, 'html.parser')
        try:
            postings = []
            for script in soup.select('script[type="application/ld+json"]'):
                value = json.loads(script.get_text())
                entries = value if isinstance(value, list) else [value]
                postings.extend(v for v in entries if isinstance(v, dict) and v.get('@type') == 'JobPosting')
            if len(postings) > 1:
                raise ValueError()
            if postings:
                data = postings[0]
            else:
                # Las ofertas externas usan la misma ficha, sin JobPosting.
                heading = soup.select_one('h1[itemprop="title"]')
                header = heading.parent.parent
                company_name = ' '.join(s.strip() for s in header.find_all(string=True, recursive=False) if s.strip())
                if not company_name and 'Oferta Ciega' in soup.get_text(' ', strip=True):
                    company_name = 'Empresa confidencial (Tecnoempleo)'
                posted = text(header.select_one('span.bg-primary-soft'))
                data = dict(title=text(heading), hiringOrganization={'name': company_name},
                            datePosted=datetime.strptime(posted, '%d/%m/%Y').date().isoformat())
            canonical = soup.select_one('link[rel="canonical"]')
            if not canonical or official_url(self.url, canonical['href']) != url:
                raise ValueError()
            title, company = data['title'].strip(), data['hiringOrganization']['name'].strip()
            body = plain_html(soup.select_one('[itemprop="description"]'))
            if not title or not company or not body:
                raise ValueError()
            fields = {}
            for item in soup.select('li.list-item'):
                label, value = item.select_one('span.d-inline-block'), item.select_one('span.float-end')
                if label is not None and value is not None:
                    fields[text(label)] = text(value)
            education = None
            extras = []
            for p in soup.select('p'):
                value = text(p) or ''
                if value.startswith(('Formación Mínima:', 'Imprescindible Residir:')):
                    if value.startswith('Formación Mínima:'):
                        education = value.split(':', 1)[1].strip()
                        extras.append('Formación obligatoria mínima: ' + education + '.')
                    else:
                        extras.append(value + '.')
            experience = fields.get('Experiencia')
            if experience:
                extras.append('Experiencia mínima: ' + experience)
            location_data = data.get('jobLocation', [])
            if isinstance(location_data, dict):
                location_data = [location_data]
            places = []
            for item in location_data:
                address = item.get('address', {})
                places.extend(address.get(k) for k in ('addressLocality', 'addressRegion') if address.get(k))
                if address.get('addressCountry') == 'ES':
                    places.append('España')
            required = data.get('applicantLocationRequirements', [])
            if isinstance(required, dict):
                required = [required]
            extras.extend('Residencia requerida: ' + r['name'] for r in required if r.get('name'))
            mode = fields.get('Ubicación') or ''
            remote = data.get('jobLocationType') == 'TELECOMMUTE' or '100% en remoto' in mode.casefold()
            if not places and mode and not remote:
                places.append(mode)
            modality = ('100% remoto' if remote else 'Híbrido' if 'híbrido' in mode.casefold()
                        else 'Presencial' if mode else None)
            return NormalizedJob(
                external_id=ident, title=title, company=company, url=url,
                source_name=self.name, source_url=self.url,
                location=', '.join(dict.fromkeys(places)) or None,
                modality=modality, remote=remote, description='\n'.join([*extras, body]),
                published_date=parse_date(data.get('datePosted')), experience_level=experience,
                study_area=education, category=fields.get('Funciones'),
                employment_type=data.get('employmentType'))
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise SourceError('Tecnoempleo: ficha pública incompleta o referencia incorrecta') from error

    def fetch_jobs(self):
        rows, expected = {}, None
        with self.client() as client:
            for page in range(1, self.options.max_pages + 1):
                url = self.url if page == 1 else f'https://www.tecnoempleo.com/ofertas-trabajo/?pr=,274,&pagina={page}'
                batch, total = self.parse_listing(self.get(client, url), len(rows))
                if expected is not None and total != expected:
                    raise SourceError('Tecnoempleo: el listado cambió durante el escaneo')
                if rows.keys() & batch.keys():
                    raise SourceError('Tecnoempleo: ofertas repetidas entre páginas')
                expected = total
                rows.update(batch)
                self.page_progress(page, len(batch))
                if len(rows) == expected:
                    break
            else:
                raise SourceError('Tecnoempleo: límite de páginas; escaneo no importado')
            jobs = []
            for number, (ident, url) in enumerate(rows.items(), 1):
                try:
                    html = self.get(client, url)
                except SourceError as error:
                    cause = error.__cause__
                    if not isinstance(cause, httpx.HTTPStatusError) or cause.response.status_code not in (404, 410):
                        raise
                    self.progress(f'{self.name} · oferta retirada: {ident}')
                else:
                    jobs.append(self.parse_detail(html, ident, url))
                self.progress(f'{self.name} · detalle {number}/{len(rows)}')
        return ScanResult(tuple(jobs), page, len(jobs), True)
