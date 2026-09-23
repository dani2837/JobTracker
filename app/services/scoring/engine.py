from app.config.profile import load_profile, profile_hash, validate_profile
from app.services.scoring import education, experience, junior_signals, location, role, technology
from app.services.scoring.models import ScoreResult
from app.services.scoring.models import Component
from datetime import date
from app.services.scoring import job_kind
from app.services.scoring.requirements import assess_languages, clauses, Clause, normalize
import re

ENGINE_VERSION = '5.1.0'
MAXIMUMS = {'experience': 35, 'education': 20, 'role': 15, 'location': 15, 'junior_signals': 10, 'technology': 5}


def assess_preferences(job, profile, components):
    result = Component(0)
    prefs = profile.get('search_preferences')
    if prefs is None:
        return result
    mode = normalize(job.get('modality'))
    facts = components['location'].facts
    evidence = ' '.join(facts.get('location_evidence', []))
    if re.search(r'hibrid|hybrid', mode + ' ' + evidence):
        modality = 'hybrid'
    elif re.search(r'presencial|on[ -]?site', mode + ' ' + evidence):
        modality = 'onsite'
    elif facts.get('remote_confirmed') or re.search(r'remoto|remote|teletrabajo', mode):
        modality = 'remote'
    else:
        modality = None
    if modality and modality not in prefs['modalities']:
        result.exclusions.append('Modalidad desactivada en Mi perfil de búsqueda.')
    if modality == 'remote' and not prefs['remote_spain']:
        result.exclusions.append('Remoto España desactivado en Mi perfil de búsqueda.')
    if facts.get('location_kind') == 'seville' and modality != 'remote' and not prefs['seville']:
        result.exclusions.append('Sevilla/provincia desactivada en Mi perfil de búsqueda.')
    category = components['role'].facts.get('role_kind')
    if category == 'unknown':
        category = 'other_it'
    if re.search(r'\b(?:datos|data|cloud|nube|devops|aws|azure)\b', normalize(job.get('title'))):
        category = 'data_cloud'
    if category in ('development', 'systems', 'support', 'qa', 'data_cloud', 'other_it') and category not in prefs['categories']:
        result.exclusions.append('Categoría de puesto desactivada en Mi perfil de búsqueda.')
    published = job.get('published_date')
    if published:
        try:
            age = (date.today() - date.fromisoformat(str(published)[:10])).days
            if age > prefs['max_age_days']:
                result.exclusions.append(f"Oferta de más de {prefs['max_age_days']} días.")
        except ValueError:
            result.warnings.append('Fecha de publicación no reconocida; antigüedad sin confirmar.')
    else:
        result.warnings.append('Sin fecha de publicación; antigüedad sin confirmar.')
    return result


def classify(score: int, excluded: bool = False) -> str:
    if excluded:
        return 'Excluida'
    for threshold, name in [(90, 'Candidatura prioritaria'), (75, 'Muy interesante'), (60, 'Revisar'), (40, 'Baja prioridad')]:
        if score >= threshold:
            return name
    return 'Ocultar'


class ScoringEngine:
    def __init__(self, profile: dict | None = None):
        self.profile = profile if profile is not None else load_profile()
        validate_profile(self.profile)
        self.hash = profile_hash(self.profile)

    def evaluate(self, job: dict) -> ScoreResult:
        components = {name: module.assess(job, self.profile) for name, module in
                      [('experience', experience), ('education', education), ('role', role),
                       ('location', location), ('junior_signals', junior_signals), ('technology', technology)]}
        items = list(clauses(job.get('description')))
        title = job.get('title') or ''
        if re.search(r'\b(?:con|with)\b.*\b[bc][12]\b', normalize(title)):
            items.append(Clause(title, True, False))
        language = assess_languages(items, self.profile)
        kind = job_kind.assess(job, self.profile)
        preferences = assess_preferences(job, self.profile, components)
        all_components = [*components.values(), language, kind, preferences]
        positives, warnings, exclusions = [], [], []
        penalties, unmet, facts = {}, {}, {}
        for component in all_components:
            positives.extend(component.positives)
            warnings.extend(component.warnings)
            exclusions.extend(component.exclusions)
            penalties.update(component.penalties)
            unmet.update(component.unmet)
            facts.update(component.facts)
        if len(unmet) >= self.profile['rules']['max_unmet']:
            exclusions.append(f'{len(unmet)} requisitos obligatorios potencialmente incumplidos')
            exclusions.extend(value for key, value in unmet.items() if key.startswith('language_'))
        elif len(unmet) == 1:
            penalties['one_unmet'] = self.profile['penalties']['one_unmet']
        breakdown = {name: round(component.points / MAXIMUMS[name] * self.profile['weights'][name])
                     for name, component in components.items()}
        breakdown['penalties'] = -sum(penalties.values())
        raw = max(0, min(100, sum(breakdown.values())))
        excluded = bool(exclusions)
        # Las exclusiones no pueden aparecer con porcentajes altos engañosos.
        score = self.profile['rules']['excluded_score'] if excluded else raw
        facts['score_before_exclusion'] = raw
        facts['exclusion_reasons'] = list(dict.fromkeys(exclusions))
        facts['exclusion_categories'] = [name for name, component in components.items() if component.exclusions]
        if preferences.exclusions:
            facts['exclusion_categories'].append('search_preferences')
        if kind.exclusions:
            facts['exclusion_categories'].append('job_kind')
        facts['unmet_categories'] = list(unmet)
        if len(unmet) >= self.profile['rules']['max_unmet']:
            facts['exclusion_categories'].append('requirements')
            if any(key.startswith('language_') for key in unmet):
                facts['exclusion_categories'].append('languages')
        facts['junior'] = facts.get('junior', False) or facts.get('experience_kind') in ('none', 'zero_range', 'entry', 'junior')
        return ScoreResult(score, classify(score, excluded), excluded, '; '.join(dict.fromkeys(exclusions)) or None,
                           breakdown, list(dict.fromkeys(warnings)), list(dict.fromkeys(positives)),
                           list(unmet.values()), penalties, facts, self.profile['weights'].copy(), self.hash, ENGINE_VERSION)
