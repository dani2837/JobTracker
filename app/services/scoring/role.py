from app.services.scoring.models import Component
from app.services.scoring.requirements import contains
from app.services.scoring.requirements import normalize
import re

COMMERCIAL = re.compile(r'\b(?:sales|(?:key\s+|technical\s+)?account\s+manager|business\s+development|comercial(?:es)?)\b')
NON_IT_TITLE = re.compile(
    r'\b(?:delineantes?|electricistas?|electromecanicos?)\b|'
    r'\binstalador(?:a|es|as)?(?:/a)?\b.{0,60}\b(?:fibra|telecomunicaciones?|antenas?|alarmas?|placas solares)\b|'
    r'\btecnic[oa](?:/a)?\b.{0,35}\b(?:electricidad|climatizacion|mantenimiento industrial|electromecanica)\b')
TELECOM_TECHNICIAN = re.compile(r'\b(?:tecnic[oa](?:/a)?|soporte|support)\b.{0,45}\btelecomunicacion(?:es)?\b')
FIELD_WORK = re.compile(
    r'\b(?:instalador(?:a|es|as)?|fusionador(?:a|es|as)?)\b.{0,45}\b(?:fibra|telecomunicaciones?)\b|'
    r'\b(?:instalacion|tendido|fusion|empalme|mantenimiento)\b.{0,80}\b(?:fibra|antenas?|torres|equipos de telecomunicaciones)\b|'
    r'\b(?:trabajos? en altura|prl telco|altura telco|dispositivos de teleasistencia)\b')
TECHNICAL_TASK = re.compile(
    r'^(?:(?:you will|you\x27ll|tus funciones incluyen|te encargaras de)\s+)?(?:'
    r'(?:desarrollar|programar|implementar|mantener|develop|build|implement|maintain)\b.{0,55}\b(?:software|apis?|microservicios|microservices|aplicaciones|applications|backend|frontend|codigo|code)\b|'
    r'(?:administrar|configurar|desplegar|monitorizar|administer|configure|deploy|monitor)\b.{0,55}\b(?:servidores|servers|linux|kubernetes|redes|networks|bases de datos|databases|infraestructura|infrastructure)\b|'
    r'(?:automatizar|disenar|ejecutar|automate|design|execute)\b.{0,40}\b(?:pruebas de software|software tests|tests automatizados|automated tests)\b)')


def technical_duties(description):
    """Exige tareas técnicas concretas; vender tecnología o citar un CRM no basta."""
    evidence = set()
    for fragment in re.split(r'[\n.;:]+', normalize(description)):
        fragment = fragment.strip(' •·-')
        if TECHNICAL_TASK.search(fragment):
            evidence.add(fragment)
    return len(evidence) >= 2


def assess(job: dict, profile: dict) -> Component:
    title = job.get('title') or ''
    normalized_title = normalize(title)
    # La categoría del portal y las herramientas citadas no convierten un oficio
    # de instalación, delineación o mantenimiento físico en un puesto informático.
    if (NON_IT_TITLE.search(normalized_title) or
            (TELECOM_TECHNICIAN.search(normalized_title) and
             FIELD_WORK.search(normalize(job.get('description'))) and
             not technical_duties(job.get('description')))):
        return Component(0, exclusions=['Puesto técnico no informático: instalación/campo u oficio ajeno al perfil IT.'],
                         facts={'role_kind': 'non_it_technical'})
    commercial = bool(COMMERCIAL.search(normalize(title)))
    if commercial and not technical_duties(job.get('description')):
        return Component(0, exclusions=['Puesto de venta comercial ajeno a las funciones IT del perfil.'],
                         facts={'role_kind': 'non_it_sales'})
    for category in ('qa', 'support', 'development', 'systems', 'other_it'):
        if any(contains(title, word) for word in profile['roles'][category]):
            points = {'development': 15, 'systems': 13, 'qa': 13, 'support': 12, 'other_it': 11}[category]
            if category == 'support' and any(contains(title, term) for term in ('helpdesk', 'help desk', 'soporte n1', 'microinformatica')):
                points = 9
            label = {'development': 'desarrollo', 'systems': 'sistemas', 'qa': 'QA y testing',
                     'support': 'soporte', 'other_it': 'otras funciones IT'}[category]
            return Component(points, positives=[f'Puesto IT: {label}'], facts={'role_kind': category})
    if commercial:
        return Component(11, positives=['Funciones técnicas IT concretas en la descripción'],
                         facts={'role_kind': 'other_it'})
    return Component(5, warnings=['Tipo de puesto no identificado claramente como IT'], facts={'role_kind': 'unknown'})
