import re
from app.services.scoring.models import Component
from app.services.scoring.requirements import normalize, contains, clauses

EXCLUSION = 'Ubicación no compatible o no confirmada para trabajar desde Sevilla.'


def assess(job: dict, profile: dict) -> Component:
    place = normalize(job.get('location')).strip()
    mode = normalize(job.get('modality')).strip()
    description = re.split(r'descripcion del empleo|job description', normalize(job.get('description')))[-1]
    items = [place, mode, normalize(job.get('title')), *[normalize(c.text) for c in clauses(description) if not c.optional]]
    items = [re.sub(r'\s+', ' ', text) for text in items]
    local = any(contains(place, town) for town in profile['locations'])
    if 'aguadulce' in place and 'almeria' in place:
        local = False
    # Modalidad laboral, no infraestructura híbrida ni formación opcional.
    onsite = bool(re.search(r'presencial|hibrid[oa]|hybrid|on[ -]site', mode))
    evidence = []
    for text in items[2:]:
        if re.search(r'formacion presencial|entrevista presencial|no presencial|sin presencialidad', text):
            continue
        if re.search(r'(?:modelo|modalidad|trabajo|puesto|ubicacion|jornada)\W+(?:de\s+)?(?:trabajo\s+)?(?:hibrid[oa]|presencial|hybrid)|'
                     r'\bpresencial(?:mente)?\s+(?:en|a)|\bdias?\s+(?:en\s+oficina|presencial)|'
                     r'teletrabajo parcial|\d+\s+dias?\s+(?:(?:de|en)\s+)?(?:teletrabajo|remoto)', text):
            onsite = True
            evidence.append(text)
    country = normalize(profile['remote_country'])
    aliases = ('espana', 'spain') if country in ('espana', 'spain') else (country,)
    territory = '(?:' + '|'.join(re.escape(c) for c in aliases) + ')'
    full_remote = r'(?:100\s*%\s*(?:en\s*)?(?:remoto|remote|teletrabajo)|(?:remoto|remote|teletrabajo)\s*(?:al\s*)?100\s*%|fully remote|teletrabajo completo|totalmente remoto)'
    territory_remote = (r'\b(?:remoto|remote)\s+(?:desde\s+)?' + territory + r'\b|\b' + territory + r'\s+(?:remoto|remote)\b|'
                        r'(?:remoto|remote|teletrabajo completo).{0,70}desde cualquier (?:punto|lugar|parte) de ' + territory)
    remote_evidence = []
    for text in items:
        if re.search(r'no (?:es |hay |se permite )?(?:trabajo )?(?:en )?(?:100\s*%\s*)?remoto|sin (?:opcion de )?(?:teletrabajo|remoto)|remoto (?:parcial|ocasional)', text):
            continue
        paired = re.search(territory_remote, text)
        complete = re.search(full_remote, text)
        territory_confirmed = any(contains(text, c) or contains(place, c) for c in aliases)
        territory_confirmed |= bool(re.search(r'worldwide|todo el mundo|union europea|european union', text))
        if paired or (complete and (territory_confirmed or local)):
            remote_evidence.append(text)
    if place in aliases and mode in ('remoto', 'remote'):
        remote_evidence.append(f'{place} / {mode}')
    restrictions = r'(?:solo|only|residen\w* (?:en|in)|based in)\s*(?:uk|united kingdom|reino unido|usa|estados unidos|alemania|germany|francia|france)|(?:uk|germany|france)\s+only'
    restricted = any(re.search(restrictions, text) for text in items)
    facts = {'remote_confirmed': bool(remote_evidence) and not onsite and not restricted,
             'location_evidence': remote_evidence + evidence}
    # Una sede presencial expresa en el título y el cuerpo prevalece sobre
    # una etiqueta de listado contradictoria (Accenture: Sevilla / Córdoba).
    for item in items[3:]:
        match = re.search(r'presencial.{0,60}?\ben\s+(?:nuestras?\s+)?oficinas?\s+de\s+([a-z ]+?)(?=\s*\(|[,.;]|$)', item)
        if match:
            workplace = match[1].strip()
            if workplace and contains(job.get('title') or '', workplace) and not any(contains(workplace, town) for town in profile['locations']):
                facts.update(location_kind='outside', remote_confirmed=False)
                facts['location_evidence'].append(item)
                return Component(0, exclusions=['Sede presencial fuera de Sevilla indicada expresamente; contradice la ubicación del listado.'], facts=facts)
    if local and not restricted:
        facts['location_kind'] = 'seville'
        return Component(15 if 'hibrid' in mode else 14, positives=[f'Ubicación compatible: {job.get("location")}'], facts=facts)
    if remote_evidence and not onsite and not restricted and profile['allow_remote']:
        facts['location_kind'] = 'remote'
        return Component(15, positives=['Remoto completo compatible con España'], facts=facts)
    facts['location_kind'] = 'outside'
    return Component(0, exclusions=[EXCLUSION], facts=facts)
