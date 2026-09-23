import hashlib
import json
from pathlib import Path

EXAMPLE_PROFILE_PATH = Path(__file__).with_name('profile.example.json')
LOCAL_PROFILE_PATH = Path(__file__).with_name('profile.json')
PROFILE_PATH = LOCAL_PROFILE_PATH if LOCAL_PROFILE_PATH.exists() else EXAMPLE_PROFILE_PATH
USER_PROFILE_PATH = PROFILE_PATH.parents[2] / 'data/search_profile.json'
MODALITIES = ('onsite', 'hybrid', 'remote')
SEARCH_ROLES = ('development', 'systems', 'support', 'qa', 'data_cloud', 'other_it')


def load_profile(path: Path | None = None) -> dict:
    path = path if path is not None else USER_PROFILE_PATH if USER_PROFILE_PATH.exists() else PROFILE_PATH
    profile = json.loads(path.read_text(encoding='utf-8'))
    validate_profile(profile)
    return profile


def search_preferences(profile):
    return profile.get('search_preferences', dict(modalities=list(MODALITIES) if profile['allow_remote'] else ['onsite', 'hybrid'],
        seville=True, remote_spain=profile['allow_remote'], categories=list(SEARCH_ROLES),
        exclude_university=not profile['university_degree'], max_age_days=60))


def save_profile(profile):
    validate_profile(profile)
    USER_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = USER_PROFILE_PATH.with_suffix('.tmp')
    temporary.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(USER_PROFILE_PATH)


def validate_profile(profile: dict) -> None:
    required = {'education', 'university_degree', 'professional_experience_years',
                'max_required_experience_years', 'allow_remote', 'remote_country',
                'languages', 'weights', 'penalties', 'rules', 'roles', 'technologies', 'junior_terms', 'locations'}
    if not isinstance(profile, dict) or not required <= profile.keys():
        raise ValueError('El perfil no contiene todos los campos necesarios')
    weights = profile['weights']
    if set(weights) != {'experience', 'education', 'role', 'location', 'junior_signals', 'technology'}:
        raise ValueError('Componentes de score incorrectos')
    if any(type(n) is not int or n < 0 for n in weights.values()) or sum(weights.values()) != 100:
        raise ValueError('Los pesos deben ser enteros no negativos y sumar 100')
    if any(type(n) is not int or n < 0 for n in profile['penalties'].values()):
        raise ValueError('Las penalizaciones deben ser enteros no negativos')
    if profile['max_required_experience_years'] < 0 or profile['professional_experience_years'] < 0:
        raise ValueError('La experiencia del perfil no puede ser negativa')
    if type(profile['allow_remote']) is not bool or type(profile['university_degree']) is not bool:
        raise ValueError('Remoto y titulación universitaria deben ser booleanos')
    if (type(profile['rules'].get('max_unmet')) is not int or profile['rules']['max_unmet'] < 1
            or type(profile['rules'].get('excluded_score')) is not int or not 0 <= profile['rules']['excluded_score'] < 40):
        raise ValueError('Reglas de exclusión no válidas')
    if set(profile['roles']) != {'development','systems','support','qa','other_it'}:
        raise ValueError('Categorías de puesto no válidas')
    for key in ('locations', 'education', 'technologies', 'junior_terms'):
        if not isinstance(profile[key], list) or not all(isinstance(v, str) and v.strip() for v in profile[key]):
            raise ValueError(f'Lista de perfil no válida: {key}')
    prefs = profile.get('search_preferences')
    if prefs is not None:
        for key, allowed in [('modalities', MODALITIES), ('categories', SEARCH_ROLES)]:
            if not isinstance(prefs.get(key), list) or not prefs[key] or any(v not in allowed for v in prefs[key]):
                raise ValueError('Selecciona al menos una modalidad y una categoría válidas')
        for key in ('seville', 'remote_spain', 'exclude_university'):
            if type(prefs.get(key)) is not bool:
                raise ValueError('Preferencia de búsqueda no válida')
        if not prefs['seville'] and not (prefs['remote_spain'] and 'remote' in prefs['modalities']):
            raise ValueError('Selecciona Sevilla/provincia o remoto España con modalidad remota')
        if type(prefs.get('max_age_days')) is not int or not 1 <= prefs['max_age_days'] <= 60:
            raise ValueError('Antigüedad permitida: de 1 a 60 días')


def profile_hash(profile: dict) -> str:
    return hashlib.sha256(json.dumps(profile, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
