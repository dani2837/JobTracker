import re
from app.services.scoring.models import Component
from app.services.scoring.requirements import Clause, normalize, clauses

ZERO = r'\b(sin experiencia|no se requiere experiencia|no requiere experiencia|no hace falta (?:tener )?experiencia|no experience|primer empleo|primera experiencia)\b'
RANGE = re.compile(r'\b(?:entre\s+)?(\d+)\s*(?:-|a|y|to)\s*(\d+)\s*(?:anos?|years?)\b')
SINGLE = re.compile(r'\b(\d+)\s*(\+)?\s*(?:anos?|years?)\b')
WORDS = {'un': '1', 'uno': '1', 'una': '1', 'dos': '2', 'tres': '3', 'cuatro': '4', 'cinco': '5', 'seis': '6', 'siete': '7', 'diez': '10'}


def assess(job: dict, profile: dict) -> Component:
    result = Component(22, warnings=['Mínimo de experiencia no indicado; verificar requisitos'], facts={'experience_kind': 'unknown'})
    items = list(clauses(job.get('description')))
    title = normalize(job.get('title'))
    structured = job.get('experience_level')
    if structured:
        items.insert(0, Clause(str(structured), True, False))
    items.insert(0, Clause(str(job.get('title') or ''), True, False))
    candidates = []
    minima = []
    zero_signal = False
    for item in items:
        text = normalize(item.text)
        for word, number in WORDS.items():
            text = re.sub(r'\b' + word + r'(?=\s+anos?\b)', number, text)
        if re.search(ZERO, text):
            candidates.append((35, 'none', item.text))
            zero_signal = True
        if item.optional:
            continue
        spans = []
        for match in RANGE.finditer(text):
            low, high = int(match[1]), int(match[2])
            spans.append(match.span())
            if low == 0:
                candidates.append((33 if high <= 1 else 30, 'zero_range', item.text))
            elif item.required or 'experien' in text or text == normalize(structured):
                minima.append((low, item.text))
        for match in SINGLE.finditer(text):
            if any(start <= match.start() < end for start, end in spans):
                continue
            number = int(match[1])
            if re.search(r'(hasta|up to|menos de|less than)\s*$', text[:match.start()]):
                candidates.append((33 if number <= 1 else 30, 'zero_range', item.text))
            elif (item.required or 'experien' in text or re.fullmatch(r'\d+\+?\s*(anos?|years?)', text)):
                if not re.search(r'vacaciones|empresa.*(?:fundada|historia)|llevamos|somos|hace\s+\d+', text):
                    minima.append((number, item.text))
        if re.search(r'\b(entry[ -]level|trainee|primer empleo)\b', text):
            candidates.append((32, 'entry', item.text))
    senior_label = title + ' ' + normalize(structured)
    if re.search(r'\bsenior\b', senior_label) and not re.search(r'\bno\b.*\bsenior\b|\bjunior\b.*\bsenior\b|\bsenior\b.*\bjunior\b', senior_label):
        result.exclusions.append(f'Puesto senior: {job.get("title")}')
        result.unmet['experience'] = 'El puesto requiere nivel senior'
    if minima:
        minimum, evidence = max(minima, key=lambda value: value[0])
        result = Component(20, facts={'experience_kind': 'minimum', 'minimum_years': minimum},
                           exclusions=result.exclusions, unmet=result.unmet)
        if minimum > profile['max_required_experience_years']:
            result.exclusions.append(f'Experiencia mínima obligatoria de {minimum} años: {evidence}')
            result.unmet['experience'] = f'Experiencia mínima: {minimum} años ({evidence})'
        elif minimum > profile['professional_experience_years']:
            result.unmet['experience'] = f'Se solicita {minimum} año de experiencia profesional: {evidence}'
        if zero_signal or candidates or 'junior' in title:
            result.warnings.append('Señales junior y experiencia mínima contradictorias; prevalece el requisito mínimo')
        return result
    if candidates:
        points, kind, evidence = max(candidates, key=lambda value: value[0])
        result.points, result.facts = points, {'experience_kind': kind}
        result.warnings.clear()
        result.positives.append(f'Experiencia accesible: {evidence}')
    elif re.search(r'\bjunior\b', title + ' ' + normalize(structured)):
        result.points = 27
        result.facts = {'experience_kind': 'junior'}
        result.warnings.clear()
        result.positives.append('Puesto junior sin mínimo numérico')
    elif any('experien' in normalize(c.text) and not c.optional for c in items):
        result.penalties['ambiguous_experience'] = profile['penalties']['ambiguous_experience']
    if re.search(r'\bjunior\b', title) and re.search(r'\bsenior\b', normalize(structured)):
        result.warnings.append('El título indica junior pero la categoría del portal indica senior; confirmar el nivel real.')
    return result
