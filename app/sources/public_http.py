"""HTTP público limitado y utilidades de normalización, sin formularios ni sesiones."""
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from threading import Event
from urllib.parse import urljoin, urlsplit, urlunsplit
import httpx
from bs4 import BeautifulSoup
from app.sources.base import BaseSource, SourceError, ScanCancelled

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HttpOptions:
    max_pages: int = 60
    max_requests: int = 1200
    timeout: float = 25
    delay: float = 0.15
    retries: int = 1


def text(tag):
    return tag.get_text(' ', strip=True) or None if tag is not None else None


def plain_html(tag):
    if tag is None:
        return None
    copy = BeautifulSoup(str(tag), 'html.parser')
    for node in copy.select('script,style'):
        node.decompose()
    for node in copy.select('p,li,h1,h2,h3,h4,br,div'):
        node.insert_after('\n')
    return '\n'.join(' '.join(line.split()) for line in copy.get_text(' ').splitlines() if line.strip()) or None


def official_url(base, href, prefix=None):
    parsed = urlsplit(urljoin(base, href))
    if parsed.scheme != 'https' or parsed.netloc != urlsplit(base).netloc or (prefix and not parsed.path.startswith(prefix)):
        raise SourceError('Enlace fuera del portal público autorizado')
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ''))


def parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        try:
            return datetime.strptime(value, '%a %b %d %H:%M:%S UTC %Y').date()
        except ValueError as error:
            raise SourceError(f'Fecha de publicación no reconocida: {value}') from error


def remote_value(mode):
    value = (mode or '').casefold()
    if 'remoto' in value or 'remote' in value:
        return True
    if 'híbrido' in value or 'hibrido' in value or 'presencial' in value:
        return False
    return None


class PublicHttpSource(BaseSource):
    def __init__(self, options=None, *, transport=None, cancel=None, progress=None):
        self.options = options or HttpOptions()
        if self.options.max_pages < 1 or self.options.max_requests < 1 or self.options.timeout <= 0 or self.options.delay < 0 or not 0 <= self.options.retries <= 3:
            raise ValueError('Límites HTTP no válidos')
        self.transport, self.cancel = transport, cancel or Event()
        self.progress = progress or (lambda message: None)
        self.requests = 0

    def client(self):
        self.requests = 0
        return httpx.Client(timeout=self.options.timeout, transport=self.transport,
                            follow_redirects=False, headers={'User-Agent': 'JobTracker/0.4 (public job listings)'})

    def get(self, client, url, *, form=None):
        official_url(self.url, url)
        for attempt in range(self.options.retries + 1):
            if self.cancel.wait(self.options.delay if self.requests else 0):
                raise ScanCancelled('Actualización cancelada')
            if self.requests >= self.options.max_requests:
                raise SourceError('MAX_REQUESTS alcanzado; escaneo no importado')
            self.requests += 1
            try:
                response = (client.get(url) if form is None else
                            client.post(url, files={key: (None, str(value)) for key, value in form.items()}))
                if response.status_code in (429, 500, 502, 503, 504) and attempt < self.options.retries:
                    delay = max(1, int(response.headers.get('retry-after', '1'))) if response.headers.get('retry-after','1').isdigit() else 2
                    if delay > 60:
                        raise SourceError('El servidor solicita esperar; reintenta más tarde')
                    if self.cancel.wait(delay):
                        raise ScanCancelled('Actualización cancelada')
                    continue
                response.raise_for_status()
                return response.text
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                if attempt == self.options.retries:
                    raise SourceError(f'No se pudo conectar con {self.name}') from error
            except httpx.HTTPStatusError as error:
                raise SourceError(f'{self.name}: HTTP {error.response.status_code}') from error
        raise SourceError('Petición no completada')

    def page_progress(self, page, count):
        logger.info('%s página=%s ofertas=%s', self.name, page, count)
        self.progress(f'{self.name} · página {page}: {count} ofertas')
