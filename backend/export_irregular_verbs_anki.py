from __future__ import annotations

import html
from pathlib import Path

from sqlalchemy import select

from backend.app.db import SessionLocal
from backend.app.models import IrregularVerb


BASE_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = BASE_DIR / "data" / "anki"
OUTPUT_PATH = OUTPUT_DIR / "irregular_verbs_anki.tsv"


def clean(value: str | None) -> str:
    return html.escape(value or "").replace("\t", " ").replace("\n", "<br>")


def back_html(verb: IrregularVerb) -> str:
    rows = [
        ("中文", verb.meaning_zh),
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

    lines = [
        "#separator:tab",
        "#html:true",
        "#notetype:Basic",
        "#deck:Deutsch::不规则动词",
        "#tags column:3",
    ]
    for verb in verbs:
        front = clean(verb.infinitive)
        back = back_html(verb)
        tags = "不规则动词 irregular_verbs Deutsch"
        lines.append("\t".join([front, back, tags]))

    OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Exported {len(verbs)} Anki cards to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
