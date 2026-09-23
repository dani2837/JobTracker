import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from app.services.scoring.models import Component


@lru_cache(maxsize=8192)
def normalize(value) -> str:
    text = unicodedata.normalize('NFKD', str(value or '').casefold())
    return ''.join(c for c in text if not unicodedata.combining(c)).replace('–', '-').replace('—', '-')


def contains(text: str, term: str) -> bool:
    return bool(re.search(r'(?<!\w)' + re.escape(normalize(term).strip()) + r'(?!\w)', normalize(text)))


def job_text(job: dict) -> str:
    text = normalize(job.get('description'))
    text = re.split(r'descripcion del empleo|job description', text)[-1]
    text = re.split(r'informacion adicional|additional information|que ofrecemos', text)[0]
    return normalize(job.get('title')) + ' ' + text


MANDATORY = r'\b(imprescindible|obligatori\w*|requerid\w*|required|must have|minimo|minimum|al menos|at least|se requiere|^requisitos?|requisitos?\s+(?:necesarios?|indispensables?))\b'
OPTIONAL = r'\b(valorable\w*|deseable\w*|opcional|nice to have|preferred|preferiblemente|se valorara|valoramos positivamente|valoraremos positivamente|se valoran|plus|idealmente|nos gustaria)\b'
NEGATED = r'\b(no (?:se )?(?:requiere|exige)|no es (?:obligatorio|imprescindible)|not required|sin necesidad)\b'


@dataclass(frozen=True)
class Clause:
    text: str
    required: bool
    optional: bool


@lru_cache(maxsize=2048)
def clauses(description: str | None) -> tuple[Clause, ...]:
    """Mantiene el contexto de encabezados sin propagar 'valorable' de una frase a otra."""
    result = []
    mode = False
    optional_section = False
    academic_scope = False
    lines = (description or '').splitlines()
    # Los saltos de línea del JSON-LD también pueden separar palabras en negrita.
    pending = []
    def flush():
        if not pending:
            return
        text = ' '.join(pending)
        pending.clear()
        parts = re.split(r'[;.!?]+\s*|\bpero\b', text)
        scoped = []
        for part in parts:
            norm = normalize(part)
            if re.search(MANDATORY, norm) and re.search(OPTIONAL, norm):
                scoped.extend(re.split(r'(?<!\d)\s+y\s+(?!\d)|,\s+(?=[^\W\d_])|,\s*(?=valorable|deseable|obligatorio|imprescindible)', part, flags=re.I))
            else:
                scoped.append(part)
        for part in scoped:
            part = part.strip(' •-')
            if not part:
                continue
            norm = normalize(part)
            inherited = optional_section and (not academic_scope or bool(re.search(r'ingenier|titulacion|universitari|grado|licenciatura|matematicas|fisica', norm)))
            optional = bool(re.search(OPTIONAL + '|' + NEGATED, norm)) or (inherited and not re.search(MANDATORY, norm))
            required = (mode or bool(re.search(MANDATORY, norm))) and not optional
            result.append(Clause(part, required, optional))
    for line in lines:
        norm = normalize(line).strip(' :¿?¡!-')
        if norm in ('requisitos', 'requerimientos', 'que buscamos', 'como te imaginamos', 'que necesitas', 'requirements', 'qualifications', 'must have', 'must to have skills', 'required skills',
                    'requisitos deseables', 'requisitos deseable', 'nice to have', 'nice to have skills', 'deseable', 'valorable', 'hard skills'):
            flush()
            mode = True
            optional_section = bool(re.search(OPTIONAL, norm))
            academic_scope = False
        elif norm in ('descripcion de la empresa', 'company description'):
            flush()
            mode = False
            optional_section = False
            academic_scope = False
        elif norm in ('informacion adicional', 'additional information', 'que ofrecemos', 'beneficios',
                      'descripcion del empleo', 'job description') or norm.startswith('como es trabajar'):
            flush()
            mode = optional_section = False
            academic_scope = False
        else:
            # Una línea acabada en punto o una viñeta es un límite de requisito.
            if line.lstrip().startswith(('•', '- ', '·')):
                flush()
            pending.append(line.strip())
            if re.fullmatch(r'titulad[oa]s?(?:/a)?(?: en)? arquitectura(?: o similar)?', norm):
                flush()
            elif re.search(r'nos gustaria que aportaras[. :]*$', norm):
                flush()
                optional_section = True
                academic_scope = False
            elif line.rstrip().endswith(('.', ';', '!', '?')):
                flush()
            elif line.rstrip().endswith(':') and re.search(OPTIONAL, norm):
                flush()
                optional_section = True
                academic_scope = bool(re.search(r'titulaciones|estudios|formacion', norm))
    flush()
    return tuple(result)


LANGUAGES = {
    'espanol': r'espanol|castellano|spanish', 'ingles': r'ingles|english',
    'frances': r'frances|french', 'aleman': r'aleman|german',
    'italiano': r'italiano|italian', 'portugues': r'portugues|portuguese',
    'catalan': r'catalan|catalan', 'valenciano': r'valenciano',
    'euskera': r'euskera|vasco|basque', 'gallego': r'gallego|galician',
    'neerlandes': r'neerlandes|holandes|dutch', 'arabe': r'arabe|arabic',
    'chino': r'chino|mandarin|chinese', 'japones': r'japones|japanese',
    'ruso': r'ruso|russian', 'polaco': r'polaco|polish',
    'rumano': r'rumano|romanian', 'sueco': r'sueco|swedish',
}


def assess_languages(items, profile: dict) -> Component:
    result = Component(0, facts={'languages_detected': []})
    names = {**LANGUAGES, **{normalize(k): re.escape(normalize(k)) for k in profile['languages'] if normalize(k) not in LANGUAGES}}
    ranks = {'basico': 1, 'basic': 1, 'a1': 1, 'a2': 1, 'intermedio': 2,
             'intermediate': 2, 'b1': 2, 'b2': 3, 'c1': 4, 'c2': 5, 'nativo': 6}
    language_pattern = '(?:' + '|'.join(names.values()) + ')'
    for clause in items:
        original = normalize(clause.text)
        # No atribuir C1 de francés al inglés B1 de la misma frase.
        segments = re.split(r'(?:,|\by\b|\band\b)\s*(?=(?:nivel\s+)?(?:' + language_pattern + r'|[abc][12]\b))', original)
        for text in segments:
            for language, pattern in names.items():
                if not re.search(r'\b(?:' + pattern + r')\b', text):
                    continue
                optional = clause.optional or bool(re.search(OPTIONAL + '|' + NEGATED, text))
                strong = not optional and (clause.required or bool(re.search(MANDATORY, text))
                                          or bool(re.search(r'buscamos|necesitamos|we (?:require|need)', original)))
                level = re.search(r'\b(a1|a2|b1|b2|c1|c2|basico|basic|intermedio|intermediate|nativo)\b', text)
                level_name = level[1] if level else None
                high = bool(re.search(r'\b(alto|fluido|fluent|advanced|avanzado)\b', text))
                record = {'language': language, 'level': level_name or ('alto sin CEFR' if high else 'no especificado'),
                          'required': strong, 'optional': optional, 'evidence': text.strip()}
                if record not in result.facts['languages_detected']:
                    result.facts['languages_detected'].append(record)
                if optional:
                    result.warnings.append(f'Idioma valorable, sin penalización: {text.strip()}')
                    continue
                known = ranks.get(normalize(profile['languages'].get(language)), 0)
                if level_name and known >= ranks[level_name]:
                    continue
                if language == 'ingles' and not level_name:
                    if high and strong:
                        result.penalties['english_high'] = profile['penalties']['english_high']
                        result.warnings.append(f'Nivel alto de inglés sin nivel CEFR explícito: {text.strip()}')
                    continue
                if not strong:
                    result.warnings.append(f'Idioma mencionado, obligatoriedad no confirmada: {text.strip()}')
                elif language == 'ingles' and level_name == 'b2':
                    result.penalties['english_b2'] = profile['penalties']['english_b2']
                    result.warnings.append(f'Inglés B2 requerido: {text.strip()}')
                elif (level_name and known < ranks[level_name]) or not known:
                    result.unmet['language_' + language] = f'Idioma obligatorio no acreditado: {language} {record["level"]} ({text.strip()})'
                    if language == 'ingles':
                        result.penalties['english_high'] = profile['penalties']['english_high']
                elif high and known < 4:
                    result.unmet['language_' + language] = f'Nivel alto obligatorio no acreditado: {language} ({text.strip()})'
    return result


