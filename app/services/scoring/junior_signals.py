from app.services.scoring.models import Component
from app.services.scoring.requirements import contains


def assess(job: dict, profile: dict) -> Component:
    text = (job.get('title') or '') + '\n' + (job.get('description') or '')
    matches = [term for term in profile['junior_terms'] if contains(text, term)]
    entry = [term for term in matches if term not in ('plan de carrera', 'mentoring', 'formacion inicial')]
    return Component(min(10, len(matches) * 3), positives=[f'Señal junior: {term}' for term in matches],
                     facts={'junior': bool(entry)})
