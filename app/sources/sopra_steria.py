"""Attrax: listado HTML paginado y detalle JobPosting JSON-LD público."""
import json
import logging
import re
from dataclasses import dataclass
from datetime import date
from threading import Event
from typing import Callable
from urllib.parse import urljoin, urlparse
from uuid import UUID

import httpx
from bs4 import BeautifulSoup

from app.sources.base import BaseSource, NormalizedJob, ScanCancelled, ScanResult, SourceError

PORTAL = 'https://careers.soprasteria.es/jobs'
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceOptions:
    max_pages: int = 20
    page_size: int = 48
    max_requests: int = 250
    timeout: float = 20.0
    delay: float = 0.35
    retries: int = 2


def text_of(element) -> str | None:
    if element is None:
        return None
    return element.get_text(' ', strip=True) or None


def official_url(value: str) -> str:
    url = urljoin(PORTAL, value)
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.netloc != 'careers.soprasteria.es' or not parsed.path.startswith('/job/'):
        raise SourceError('La ficha no tiene una URL oficial de Sopra Steria')
    return url


def parse_listing(html: str) -> tuple[int, list[dict]]:
    soup = BeautifulSoup(html, 'html.parser')
    counter = text_of(soup.select_one('.attrax-pagination__total-results'))
    match = re.match(r'\s*(\d+)\s+resultado', counter or '', re.IGNORECASE)
    if not match:
        raise SourceError('No se reconoce el contador del listado; el portal puede haber cambiado')
    jobs = []
    for tile in soup.select('.attrax-vacancy-tile'):
        link = tile.select_one('.attrax-vacancy-tile__title')
        reference = text_of(tile.select_one('.attrax-vacancy-tile__reference-value'))
        try:
            reference = str(UUID(reference or ''))
        except ValueError as error:
            raise SourceError('Una oferta carece de referencia oficial válida') from error
        if link is None or not text_of(link):
            raise SourceError('Una oferta carece de título o enlace')
        fields = {}
        for name in ('experience-level', 'department', 'remote', 'brand'):
            fields[name] = text_of(tile.select_one(f'.attrax-vacancy-tile__option-{name} .attrax-vacancy-tile__item-value'))
        jobs.append({'external_id': reference, 'url': official_url(link.get('href', '')),
                     'title': text_of(link), 'location': text_of(tile.select_one(
                         '.attrax-vacancy-tile__location-freetext .attrax-vacancy-tile__item-value')),
                     **fields})
    return int(match[1]), jobs


def parse_detail(html: str, listing: dict) -> NormalizedJob:
    soup = BeautifulSoup(html, 'html.parser')
    posting = None
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            value = json.loads(script.get_text())
        except json.JSONDecodeError as error:
            raise SourceError('JSON-LD inválido en la ficha') from error
        candidates = value if isinstance(value, list) else [value]
        for item in candidates:
            if isinstance(item, dict):
                candidates_graph = item.get('@graph', [item])
                for node in candidates_graph:
                    if isinstance(node, dict) and node.get('@type') == 'JobPosting':
                        posting = node
    if posting is None:
        raise SourceError('No se encuentra JobPosting en la ficha')
    identifier = posting.get('identifier')
    reference = identifier.get('value') if isinstance(identifier, dict) else identifier
    if reference != listing['external_id']:
        raise SourceError('La referencia del listado no coincide con la ficha')
    title = posting.get('title')
    if not isinstance(title, str) or not title.strip():
        raise SourceError('JobPosting no contiene título')
    publication = posting.get('datePosted')
    try:
        published_date = date.fromisoformat(publication[:10]) if publication else None
    except (TypeError, ValueError) as error:
        raise SourceError('Fecha de publicación no reconocida') from error
    description = posting.get('description')
    plain_description = None
    if description:
        content = BeautifulSoup(description, 'html.parser')
        for tag in content.select('script, style'):
            tag.decompose()
        plain_description = content.get_text('\n', strip=True) or None
    remote = {'si': True, 'sí': True, 'no': False}.get((listing.get('remote') or '').casefold())
    # «No» en el filtro de teletrabajo también aparece en descripciones híbridas.
    # No equivale a presencial; tampoco se deduce una modalidad del texto libre.
    return NormalizedJob(
        external_id=reference, title=title.strip(), company='Sopra Steria',
        url=official_url(posting.get('url') or listing['url']), source_name='Sopra Steria', source_url=PORTAL,
        location=listing.get('location'), remote=remote,
        modality='Teletrabajo disponible' if remote else None,
        description=plain_description, published_date=published_date,
        experience_level=listing.get('experience-level'), department=listing.get('department'),
        brand=listing.get('brand'))


class SopraSteriaSource(BaseSource):
    name = company = 'Sopra Steria'
    url = PORTAL

    def __init__(self, options: SourceOptions | None = None, *,
                 transport: httpx.BaseTransport | None = None, cancel: Event | None = None,
                 progress: Callable[[str], None] | None = None):
        self.options = options or SourceOptions()
        if (self.options.max_pages < 1 or self.options.page_size not in (12, 24, 48)
                or self.options.max_requests < 1 or self.options.delay < 0
                or self.options.timeout <= 0 or not 0 <= self.options.retries <= 3):
            raise ValueError('Límites HTTP no válidos')
        self.transport = transport
        self.cancel = cancel or Event()
        self.progress = progress or (lambda message: None)
        self.requests = 0

    def _pause(self, seconds: float):
        if self.cancel.wait(seconds):
            raise ScanCancelled('Actualización cancelada')

    def _get(self, client: httpx.Client, url: str, **kwargs) -> str:
        for attempt in range(self.options.retries + 1):
            self._pause(self.options.delay if self.requests else 0)
            if self.requests >= self.options.max_requests:
                raise SourceError('Se alcanzó MAX_REQUESTS; no se importará un escaneo parcial')
            self.requests += 1
            try:
                response = client.get(url, **kwargs)
                if response.status_code in (429, 500, 502, 503, 504) and attempt < self.options.retries:
                    retry_after = response.headers.get('retry-after', '')
                    delay = max(1.0 * 2 ** attempt, float(retry_after)) if retry_after.isdigit() else 1.0 * 2 ** attempt
                    if delay > 60:
                        raise SourceError('El servidor solicita esperar; inténtalo más tarde')
                    logger.warning('HTTP %s; reintento %s', response.status_code, attempt + 1)
                    self._pause(delay)
                    continue
                response.raise_for_status()
                return response.text
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                if attempt == self.options.retries:
                    raise SourceError('No se pudo conectar con Sopra Steria') from error
                logger.warning('Error de conexión; reintento %s', attempt + 1)
                self._pause(1.0 * 2 ** attempt)
            except httpx.HTTPStatusError as error:
                raise SourceError(f'Sopra Steria devolvió HTTP {error.response.status_code}') from error
        raise SourceError('No se pudo completar la petición')

    def fetch_jobs(self) -> ScanResult:
        self.requests = 0
        expected = None
        listings = {}
        pages = 0
        with httpx.Client(timeout=self.options.timeout, transport=self.transport,
                          headers={'User-Agent': 'JobTracker/0.2 (public job listings)'},
                          follow_redirects=False) as client:
            for page in range(1, self.options.max_pages + 1):
                total, rows = parse_listing(self._get(client, self.url,
                    params={'page': page, 'size': self.options.page_size}))
                pages = page
                if expected is not None and total != expected:
                    raise SourceError('El total cambió durante el escaneo; vuelve a actualizar')
                expected = total
                logger.info('Sopra Steria página %s: %s ofertas', page, len(rows))
                self.progress(f'Sopra Steria · página {page}: {len(rows)} ofertas')
                for row in rows:
                    if row['external_id'] in listings:
                        raise SourceError('El portal repitió una oferta/página; escaneo incompleto')
                    listings[row['external_id']] = row
                if len(listings) == total:
                    break
                if not rows or len(listings) > total:
                    raise SourceError('La paginación no coincide con el total publicado')
            else:
                raise SourceError('Se alcanzó MAX_PAGES; escaneo incompleto')
            jobs = []
            for index, row in enumerate(listings.values(), 1):
                self.progress(f'Sopra Steria · leyendo detalle {index}/{expected}')
                jobs.append(parse_detail(self._get(client, row['url']), row))
            self._pause(0)
        logger.info('Sopra Steria: %s páginas, %s ofertas, %s peticiones', pages, len(jobs), self.requests)
        return ScanResult(tuple(jobs), pages, len(jobs), complete=True)
