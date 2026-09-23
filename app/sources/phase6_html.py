"""Dos portales HTML públicos; reutilizan HTTP limitado e importador existentes."""
import re
from datetime import date
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
from app.sources.base import NormalizedJob, ScanResult, SourceError
from app.sources.public_http import PublicHttpSource, official_url, plain_html, text, remote_value

MONTHS = 'enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre'.split()


class HtmlJobsSource(PublicHttpSource):
    def fetch_jobs(self):
        visited, references, rows = set(), set(), []
        url = self.url
        with self.client() as client:
            for page in range(1, self.options.max_pages+1):
                if url in visited:
                    raise SourceError(f'{self.name}: bucle de paginación')
                visited.add(url)
                batch, following = self.parse_listing(self.get(client, url))
                for row in batch:
                    if row['external_id'] in references:
                        raise SourceError(f'{self.name}: referencia repetida')
                    references.add(row['external_id']); rows.append(row)
                self.page_progress(page, len(batch))
                if not following:
                    break
                url = following
            else:
                raise SourceError(f'{self.name}: MAX_PAGES alcanzado')
            jobs = tuple(self.parse_detail(self.get(client, row['url']), row) for row in rows)
        return ScanResult(jobs, page, len(jobs), True)


class EmergyaSource(HtmlJobsSource):
    name = company = 'Emergya'
    url = 'https://www.emergya.com/es/trabaja-con-nosotros'

    def parse_listing(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        rows = []
        for card in soup.select('article.node--type-job-offer'):
            ref = card.get('data-history-node-id')
            href = card.get('about')
            if not ref or not href:
                raise SourceError('Emergya: oferta sin identidad')
            rows.append({'external_id':ref,'url':official_url(self.url,href,'/es/trabaja-con-nosotros/')})
        if not rows:
            raise SourceError('Emergya: listado vacío o cambiado; se conservan los datos')
        following=soup.select_one('.pager__item--next a, a[rel="next"]')
        return rows, official_url(self.url,following['href']) if following else None

    def parse_detail(self, html, row):
        soup=BeautifulSoup(html,'html.parser')
        article=soup.select_one('article.node--type-job-offer.node--view-mode-full')
        if article is None or article.get('data-history-node-id')!=row['external_id']:
            raise SourceError('Emergya: ficha incorrecta')
        title=text(article.select_one('h1'))
        stamp=text(article.select_one('.field--name-created'))
        match=re.fullmatch(r'(\d{1,2}) (\w+), (\d{4})', (stamp or '').casefold())
        if not title or not match or match[2] not in MONTHS or not article.select_one('.field--name-body'):
            raise SourceError('Emergya: ficha incompleta')
        fields={k:text(article.select_one('.field--name-field-joboffer-'+k)) for k in ('headquarter','department','experience-level')}
        for form in article.select('form'):
            form.decompose()
        return NormalizedJob(external_id=row['external_id'], title=title, company=self.company,
            url=row['url'],source_name=self.name,source_url=self.url,location=fields['headquarter'],
            description=plain_html(article),published_date=date(int(match[3]),MONTHS.index(match[2])+1,int(match[1])),
            experience_level=fields['experience-level'],department=fields['department'])


class IsotrolSource(HtmlJobsSource):
    name = company = 'Isotrol'
    url = 'https://www.isotrol.com/es/careers'

    def parse_listing(self, html):
        soup=BeautifulSoup(html,'html.parser')
        rows=[]
        for card in soup.select('a.position_item[href]'):
            url=official_url(self.url,card['href'],'/es/careers/')
            rows.append({'external_id':urlsplit(url).path.rstrip('/').split('/')[-1],'url':url})
        if not rows:
            raise SourceError('Isotrol: listado vacío o cambiado; se conservan los datos')
        following=soup.select_one('a.w-pagination-next:not([aria-disabled="true"])')
        return rows, official_url(self.url,following['href']) if following else None

    def parse_detail(self, html, row):
        soup=BeautifulSoup(html,'html.parser')
        left=soup.select_one('.job_left')
        body=soup.select_one('.job_richt-text')
        title=text(left.select_one('.heading-style-h4')) if left else None
        if not title or not text(body):
            raise SourceError('Isotrol: ficha incompleta')
        fields={text(label):text(label.parent.select_one('.text-size-medium')) for label in left.select('.text-style-tagline')}
        mode=text(left.select_one('[fs-cmsfilter-field="site"]'))
        return NormalizedJob(external_id=row['external_id'],title=title,company=self.company,
            url=row['url'],source_name=self.name,source_url=self.url,location=fields.get('LOCATION'),
            modality=mode,remote=remote_value(mode),department=fields.get('DEPARTMENT'),
            employment_type=text(left.select_one('[fs-cmsfilter-field="type"]')),
            description=plain_html(body),published_date=None)
