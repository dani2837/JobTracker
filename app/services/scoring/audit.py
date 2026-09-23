"""Diagnóstico reproducible desde SQLite. Sin red; solo escribe scores con --recalculate."""
import argparse
import json
from collections import Counter
from pathlib import Path
from app.services.scoring import education
from app.services.scoring.engine import ScoringEngine, ENGINE_VERSION
from app.services.scoring.requirements import clauses

LABELS = ('Candidatura prioritaria', 'Muy interesante', 'Revisar', 'Baja prioridad', 'Ocultar', 'Excluida')


def diagnose(jobs, engine=None):
    engine = engine or ScoringEngine()
    records = []
    for job in sorted(jobs, key=lambda row: row['id']):
        if job['is_test_data'] or job['source_name'] != 'Sopra Steria':
            continue
        result = engine.evaluate(job)
        training = education.assess(job, engine.profile)
        items = clauses(job.get('description'))
        records.append({
            'id': job['id'], 'title': job['title'], 'company': job['company'],
            'location': job.get('location'), 'modality': job.get('modality'),
            'remote_original': job.get('remote'), 'experience_original': job.get('experience_level'),
            'education': training.facts.get('education_evidence', []) + training.positives + training.warnings,
            'required': list(dict.fromkeys(c.text for c in items if c.required)),
            'optional': list(dict.fromkeys(c.text for c in items if c.optional)),
            'result': result.to_dict(),
        })
    return records


def summary(records):
    distribution = Counter(r['result']['classification'] for r in records)
    categories = Counter(c for r in records for c in r['result']['facts']['exclusion_categories'])
    language_unmet = sum(any(c.startswith('language_') for c in r['result']['facts']['unmet_categories']) for r in records)
    return {'total': len(records), 'distribution': {key: distribution[key] for key in LABELS},
            'excluded_by_category': dict(categories), 'with_language_unmet': language_unmet}


def render_report(records, before=(), reviews=None, preserved=None):
    reviews = reviews or {}
    totals = summary(records)
    old = {j['id']: j for j in before if not j['is_test_data'] and j['source_name'] == 'Sopra Steria'}
    old_counts = Counter(j['classification'] for j in old.values())
    lines = ['# Fase 3.1 · Auditoría de ofertas almacenadas', '',
             'Generado por `python -m app.services.scoring.audit`. Datos locales; sin descarga del portal.',
             f'Motor {ENGINE_VERSION}. Total reales: **{len(records)}**.', '',
             '| Clasificación | Antes | Después |', '|---|---:|---:|']
    lines += [f'| {label} | {old_counts[label] if old else "—"} | {totals["distribution"][label]} |' for label in LABELS]
    lines += ['', '## Motivos agregados', '',
              'Los motivos se solapan: una oferta puede figurar en varias categorías.', '']
    for key, label in [('location', 'Ubicación'), ('experience', 'Experiencia/seniority'),
                       ('education', 'Universidad'), ('languages', 'Idiomas como parte de dos o más incumplimientos')]:
        lines.append(f'- {label}: **{totals["excluded_by_category"].get(key, 0)}**.')
    lines += [f'- Ofertas con algún idioma obligatorio no acreditado: **{totals["with_language_unmet"]}**.',
              '- Un idioma incumplido aislado penaliza; no es una línea roja por sí solo.', '']
    if preserved is not None:
        lines += [f'Conservación verificada: **{preserved}**. Solo se modificaron campos de scoring; historial de fuentes idéntico.', '']
    lines += ['## Las tres ofertas previamente no excluidas', '']
    for record in records:
        previous = old.get(record['id'])
        if previous and not previous['excluded']:
            value = record['result']
            lines += [f'- **{record["title"]}**: {previous["score"]} ({previous["classification"]}) → '
                      f'{value["score"]} ({value["classification"]}). {value["exclusion_reason"]}',
                      '  ' + reviews.get(str(record['id']), 'Ver diagnóstico individual.')]
    lines += ['', '## Muestra revisada sobre el texto almacenado', '',
              'Las notas siguientes son la revisión de evidencias; el diagnóstico automático aparece después.', '']
    for record in records:
        if str(record['id']) in reviews and old.get(record['id'], {}).get('excluded'):
            lines += [f'- **#{record["id"]} · {record["title"]}**: {reviews[str(record["id"])]}']
    lines += ['', '## Diagnóstico individual de todas las ofertas', '',
              '«Obligatorios» y «valorables» son cláusulas detectadas, no una afirmación de que todas estén incumplidas.',
              'Los extractos se limitan a 360 caracteres por cláusula; no se reproducen descripciones completas.', '']

    def short(value):
        if value is None or value == '':
            return 'No especificado'
        text = ' '.join(str(value).split()).replace('|', '\\|')
        return text if len(text) <= 360 else text[:357] + '…'

    def bullet_list(label, values, truncate=True):
        lines.extend(['', f'**{label}**', ''])
        lines.extend(['- ' + (short(v) if truncate else str(v)) for v in values] or ['- Ninguno detectado.'])

    for record in records:
        value, facts = record['result'], record['result']['facts']
        lines += [f'### #{record["id"]} · {record["title"]}', '',
                  f'- Empresa: {record["company"]}.', f'- Ubicación original: {short(record["location"])}.',
                  f'- Modalidad original: {short(record["modality"])}; remoto del portal: {record["remote_original"]}.',
                  f'- Remoto completo compatible detectado: {facts.get("remote_confirmed", False)}; ubicación: {facts["location_kind"]}.',
                  f'- Experiencia original: {short(record["experience_original"])}; detectada: {facts["experience_kind"]}; mínimo: {facts.get("minimum_years", "no detectado")}.',
                  f'- Score: **{value["score"]}**; clasificación: **{value["classification"]}**; excluded: **{value["excluded"]}**.']
        bullet_list('Motivos exactos de exclusión', facts['exclusion_reasons'], truncate=False)
        bullet_list('Evidencia de ubicación/remoto', facts.get('location_evidence', []))
        bullet_list('Formación detectada', record['education'])
        languages = facts['languages_detected']
        bullet_list('Idiomas obligatorios detectados', [f'{i["language"]}: {i["level"]} — {i["evidence"]}' for i in languages if i['required']])
        bullet_list('Señales junior', [p for p in value['positive_signals'] if p.startswith('Señal junior') or p.startswith('Puesto junior')])
        bullet_list('Requisitos obligatorios detectados', record['required'])
        bullet_list('Requisitos valorables detectados', record['optional'])
        bullet_list('Requisitos incumplidos', value['unmet_requirements'])
        lines += ['', '---', '']
    return '\n'.join(lines)


def main():
    from app.config.settings import DATABASE_PATH, ROOT
    from app.database.db import Database
    from app.database.repositories import JobRepository, SourceRunRepository
    from app.services.scoring.recalculate import recalculate_all_jobs
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=DATABASE_PATH)
    parser.add_argument('--output', type=Path, default=ROOT / 'FASE3_1_AUDIT.md')
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--reviews', type=Path)
    parser.add_argument('--recalculate', action='store_true')
    args = parser.parse_args()
    db = Database(args.database)
    repo = JobRepository(db)
    before = repo.get_all_jobs()
    source_runs = SourceRunRepository(db).get_runs()
    baseline = json.loads(args.baseline.read_text(encoding='utf-8')) if args.baseline else before
    reviews = json.loads(args.reviews.read_text(encoding='utf-8')) if args.reviews else {}
    if args.recalculate:
        from app.main import configure_logging
        configure_logging()
        recalculate_all_jobs(db)
    after = repo.get_all_jobs()
    score_fields = {'score', 'classification', 'excluded', 'exclusion_reason', 'score_details', 'scored_at'}
    def preserved(rows):
        return {r['id']: {k: v for k, v in r.items() if k not in score_fields} for r in rows}
    assert preserved(before) == preserved(after), 'Se modificaron campos ajenos a scoring'
    if args.baseline:
        assert preserved(baseline) == preserved(after), 'Los datos no coinciden con la instantánea inicial'
    assert source_runs == SourceRunRepository(db).get_runs(), 'Se alteró source_runs'
    records = diagnose(after)
    if args.recalculate:
        persisted = {r['id']: json.loads(r['score_details']) for r in after}
        assert all(persisted[r['id']] == r['result'] for r in records)
    args.output.write_text(render_report(records, baseline, reviews, len(after)), encoding='utf-8')
    print(json.dumps(summary(records), ensure_ascii=False))


if __name__ == '__main__':
    main()
