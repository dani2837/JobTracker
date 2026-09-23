"""InfoJobs: búsqueda pública IT en Sevilla; JSON incrustado, sin sesión.

Los parámetros de categoría/provincia deben repetirse al paginar: el portal
ignora la ruta SEO cuando recibe solamente ?page=N.
"""
import json
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup

from app.sources.base import NormalizedJob, ScanResult, SourceError
from app.sources.public_http import PublicHttpSource, official_url, parse_date, plain_html, remote_value


def initial_props(html):
    if 'No podemos identificar tu navegador' in html or 'window.onProtectionInitialized' in html:
        raise SourceError('InfoJobs bloquea el acceso automatizado (protección JavaScript/cookies). '
                          'No se han actualizado sus ofertas; se conservan las guardadas.')
    for script in BeautifulSoup(html, 'html.parser').select('script'):
        content = script.get_text()
        if 'window.__INITIAL_PROPS__ =' not in content:
            continue
        try:
            encoded = content.split('window.__INITIAL_PROPS__ =', 1)[1].strip()
            if not encoded.startswith('JSON.parse('):
                break
            value, _ = json.JSONDecoder().raw_decode(encoded[len('JSON.parse('):])
            result = json.loads(value)
            if isinstance(result, dict):
                return result
        except (ValueError, TypeError):
            break
    raise SourceError('InfoJobs: JSON público ausente o no válido')


class InfoJobsSource(PublicHttpSource):
    name = company = 'InfoJobs'
    multi_company = True
    url = 'https://www.infojobs.net/ofertas-trabajo/informatica-telecomunicaciones/sevilla'

    def parse_listing(self, html, page):
        data = initial_props(html)
        try:
            nav, search = data['navigation'], data['search']
            if (nav['self'] != page or search['provinceIds'] != ['43'] or
                    search['categoryIds'] != ['150'] or not isinstance(data['offers'], list)):
                raise ValueError()
            total, pages = nav['totalElements'], nav['totalPages']
            if (type(total) is not int or type(pages) is not int or total < 0 or
                    pages < 1 or page > pages or pages > self.options.max_pages):
                raise ValueError()
            rows = []
            for row in data['offers']:
                # Los destacados repiten ofertas del listado normal, incluso de otras páginas.
                if 'PROMOTED' in row.get('upsellings', []):
                    continue
                if not row.get('code') or not row.get('title') or not row.get('companyName'):
                    raise ValueError()
                parsed = urlsplit(official_url(self.url, row['link']))
                if not parsed.path.endswith('/of-i' + row['code']):
                    raise ValueError()
                rows.append({**row, 'url': urlunsplit((parsed.scheme, parsed.netloc, parsed.path, '', ''))})
            return rows, total, pages
        except (KeyError, TypeError, ValueError) as error:
            raise SourceError('InfoJobs: listado, filtros o paginación no reconocidos') from error

    def parse_detail(self, html, row):
        try:
            offer = initial_props(html)['offer']
            if (offer['offerCode'] != row['code'] or not offer['title'].strip() or
                    not offer['companyName'].strip() or not offer['description'].strip()):
                raise ValueError()
            location = offer['location']
            place = ', '.join(dict.fromkeys(filter(None, [location.get('city'), location.get('province', {}).get('label')])) )
            study = offer.get('minimumStudies') or {}
            languages = '\n'.join(f"{item['language']}: {item['level']}" for item in offer.get('requiredLanguages', []))
            description = '\n'.join(filter(None, [
                plain_html(offer['description']),
                plain_html(offer.get('minimumRequirements')), plain_html(offer.get('desiredRequirements')),
                'Estudios mínimos: ' + study['level'] if study.get('level') else None,
                'Experiencia mínima: ' + offer['minimumExperience'] if offer.get('minimumExperience') else None,
                'Idiomas requeridos:\n' + languages if languages else None,
            ]))
            mode = offer.get('remoteWork')
            return NormalizedJob(
                external_id=offer['offerCode'], title=offer['title'].strip(), company=offer['companyName'].strip(),
                url=row['url'], source_name=self.name, source_url=self.url, location=place or None,
                modality=mode, remote=True if mode == 'Solo teletrabajo' else remote_value(mode),
                description=description, published_date=parse_date(offer.get('publishedAt')),
                experience_level=offer.get('minimumExperience'), study_area=study.get('level'),
                category=(offer.get('category') or {}).get('name'), department=offer.get('department'),
                employment_type=(offer.get('contract') or {}).get('type'), professional_profile=offer.get('level'))
        except (KeyError, TypeError, ValueError) as error:
            raise SourceError('InfoJobs: detalle público incompleto o referencia incorrecta') from error

    def fetch_jobs(self):
        rows, expected = {}, None
        with self.client() as client:
            page, pages = 1, 1
            while page <= pages:
                html = self.get(client, self.url + f'?provinceIds=43&categoryIds=150&page={page}')
                current, total, page_count = self.parse_listing(html, page)
                if expected is not None and (total != expected or page_count != pages):
                    raise SourceError('InfoJobs: el listado cambió durante el escaneo')
                expected, pages = total, page_count
                for row in current:
                    if row['code'] in rows:
                        raise SourceError('InfoJobs: página repetida o referencias duplicadas')
                    rows[row['code']] = row
                self.page_progress(page, len(rows))
                page += 1
            if len(rows) != expected:
                raise SourceError('InfoJobs: escaneo incompleto; no se importan datos parciales')
            jobs = tuple(self.parse_detail(self.get(client, row['url']), row) for row in rows.values())
        return ScanResult(jobs, pages, expected, True)
