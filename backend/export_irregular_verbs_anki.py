from __future__ import annotations

import html
from pathlib import Path

from sqlalchemy import select

from backend.app.db import SessionLocal
from backend.app.main import normalize_lemma
from backend.app.models import IrregularVerb, Meaning, VocabularyEntry


BASE_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = BASE_DIR / "data" / "anki"
OUTPUT_PATH = OUTPUT_DIR / "irregular_verbs_anki.tsv"


def clean(value: str | None) -> str:
    return html.escape(value or "").replace("\t", " ").replace("\n", "<br>")


def unique_join(values: list[str]) -> str:
    seen = set()
    result = []
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return " / ".join(result)


def vocabulary_meanings_by_infinitive(session, verbs: list[IrregularVerb]) -> dict[str, str]:
    normalized_values = sorted({normalize_lemma(verb.infinitive) for verb in verbs})
    if not normalized_values:
        return {}

    rows = session.execute(
        select(VocabularyEntry.normalized_lemma, Meaning.gloss)
        .join(Meaning, Meaning.entry_id == VocabularyEntry.id)
        .where(
            VocabularyEntry.normalized_lemma.in_(normalized_values),
            VocabularyEntry.part_of_speech == "verb",
            Meaning.language == "zh",
        )
        .order_by(VocabularyEntry.id, Meaning.sort_order)
    ).all()

    meanings: dict[str, list[str]] = {}
    for normalized, gloss in rows:
        meanings.setdefault(normalized, []).append(gloss)
    return {normalized: unique_join(items) for normalized, items in meanings.items()}


def back_html(verb: IrregularVerb, meaning: str | None = None) -> str:
    rows = [
        ("中文", meaning or verb.meaning_zh),
        ("现在时", verb.present),
        ("过去式", verb.preterite),
        ("第二分词", verb.participle_ii),
        ("助动词", verb.auxiliary),
        ("命令式", verb.imperative),
        ("第二虚拟式", verb.subjunctive_ii),
    ]
    table_rows = "".join(
        f"<tr><th>{clean(label)}</th><td>{clean(value)}</td></tr>"
        for label, value in rows
        if value
    )
    return (
        "<div class=\"irregular-verb-card\">"
        f"<h3>{clean(verb.infinitive)}</h3>"
        "<table>"
        f"{table_rows}"
        "</table>"
        "</div>"
    )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as session:
        verbs = session.scalars(
            select(IrregularVerb).order_by(IrregularVerb.infinitive)
        ).all()
        vocabulary_meanings = vocabulary_meanings_by_infinitive(session, verbs)

    lines = [
        "#separator:tab",
        "#html:true",
        "#notetype:Basic",
        "#deck:Deutsch::不规则动词",
        "#tags column:3",
    ]
    for verb in verbs:
        front = clean(verb.infinitive)
        back = back_html(verb, vocabulary_meanings.get(normalize_lemma(verb.infinitive)))
        tags = "不规则动词 irregular_verbs Deutsch"
        lines.append("\t".join([front, back, tags]))

    OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Exported {len(verbs)} Anki cards to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
