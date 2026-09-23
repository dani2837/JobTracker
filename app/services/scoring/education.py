import re
from app.services.scoring.models import Component
from app.services.scoring.requirements import clauses, normalize

UNIVERSITY = r'\b(grados?(?: universitario)?|graduad[oa]s? en|titulad[oa]s?(?:/a)?(?: en)? arquitectura|universitari\w*|ingenieria|licenciatura|bachelor|university degree|master)\b'
FP = r'\b(fp|formacion profesional|cfgs|cfgm|ciclo formativo|grado superior|grado medio|daw|dam|asir)\b'


def assess(job: dict, profile: dict) -> Component:
    result = Component(13, warnings=['Formación no especificada'])
    candidates = []
    for clause in clauses(job.get('description')):
        text = normalize(clause.text)
        university = bool(re.search(UNIVERSITY, text))
        if university and not re.search(r'\b(grados?|graduad[oa]s? en|titulad[oa]s?|titulacion|licenciatura|universitari\w*|bachelor|degree)\b|'
                                        r'(?:titulo oficial de |^|\bo )master\b|master o ingenieria|'
                                        r'^ingenieria\b|ingenieria\s+(?:obligatoria|imprescindible)|'
                                        r'(?:valorara|preferiblemente)\s+ingenieria', text):
            # Ingeniería como actividad («experiencia en proyectos de ingeniería»)
            # no prueba que se exija una titulación.
            university = False
        fp = bool(re.search(FP, text))
        fp_alternative = fp and not re.search(FP + r'\s+(?:valorable|deseable|opcional)', text)
        equivalent = bool(re.search(r'equivalente|equivalent|formacion tecnica|titulacion tecnica|estudios relacionados', text))
        # Las alternativas se evalúan en la misma cláusula, no en toda la oferta.
        if (university and not (fp_alternative or equivalent) and clause.required and not profile['university_degree']
                and profile.get('search_preferences', {}).get('exclude_university', True)):
            result.points = 0
            result.warnings.clear()
            result.exclusions.append('Titulación universitaria obligatoria no compatible con el perfil.')
            result.facts.setdefault('education_evidence', []).append(clause.text)
            result.unmet['education'] = 'El perfil no dispone de la titulación universitaria exigida'
        if fp:
            points = 17 if university else 20 if re.search(r'\b(daw|dam|asir|fp)\b', text) else 19
            candidates.append((points, f'Admite Formación Profesional: {clause.text}'))
        elif equivalent:
            candidates.append((15 if university else 17, f'Admite formación equivalente: {clause.text}'))
        elif university and clause.optional:
            candidates.append((10, f'Universidad preferida, no excluyente: {clause.text}'))
    if candidates:
        result.points, message = max(candidates, key=lambda item: item[0])
        result.positives.append(message)
        result.warnings.clear()
    return result
