from app.services.scoring.models import Component
from app.services.scoring.requirements import contains, job_text


def assess(job: dict, profile: dict) -> Component:
    text = job_text(job)
    found = [term for term in profile['technologies'] if contains(text, term)]
    return Component(5 if found else 3 if any(contains(text, t) for t in ('it', 'tecnologia', 'informatico')) else 1,
                     facts={'technologies': found})
