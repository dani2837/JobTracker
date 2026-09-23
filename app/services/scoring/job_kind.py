"""Distingue vacantes de candidaturas generales y excluye becas/prácticas solicitadas."""
import re
from app.services.scoring.models import Component
from app.services.scoring.requirements import normalize


def assess(job, profile):
    if job.get('general_application'):
        return Component(0, exclusions=['Candidatura espontánea general; no es una vacante concreta.'])
    kind = normalize(' '.join(str(job.get(k) or '') for k in ('title','employment_type','experience_level','professional_profile')))
    if re.search(r'\b(beca|becas|becario|becaria|practicas|internship|internships)\b', kind):
        return Component(0, exclusions=['Beca o prácticas: el perfil busca empleo, no prácticas.'])
    return Component(0)
