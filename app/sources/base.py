from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


class SourceError(Exception):
    """No se ha podido completar una lectura fiable de la fuente."""


class ScanCancelled(SourceError):
    pass


@dataclass(frozen=True)
class NormalizedJob:
    external_id: str
    title: str
    company: str
    url: str
    source_name: str
    source_url: str
    location: str | None = None
    modality: str | None = None
    remote: bool | None = None
    description: str | None = None
    published_date: date | None = None
    experience_level: str | None = None
    department: str | None = None
    brand: str | None = None
    category: str | None = None
    employment_type: str | None = None
    professional_profile: str | None = None
    service_line: str | None = None
    study_area: str | None = None
    general_application: bool = False


@dataclass(frozen=True)
class ScanResult:
    jobs: tuple[NormalizedJob, ...]
    pages: int
    total_found: int
    complete: bool


class BaseSource(ABC):
    multi_company = False
    name: str
    company: str
    url: str

    @abstractmethod
    def fetch_jobs(self) -> ScanResult:
        """Devuelve un escaneo completo o lanza SourceError; no guarda datos."""
