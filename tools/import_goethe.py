from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.app.db import SessionLocal
from backend.app.main import create_search_index, normalize_lemma, sync_entry_search
from backend.app.models import EntryTag, VocabularyEntry


BASE_DIR = Path(__file__).resolve().parents[1]
GOETHE_DIR = BASE_DIR / "data" / "Goethe"

POS_MAP = {
    "Adjektiv": "adjective",
    "Adverb": "adverb",
    "Affix": "affix",
    "Artikel": "article",
    "Interjektion": "interjection",
    "Konjunktion": "conjunction",
    "Präposition": "preposition",
    "Pronomen": "pronoun",
    "Substantiv": "noun",
    "Symbol": "symbol",
    "Verb": "verb",
    "Zahlwort": "numeral",
}

GENDER_MAP = {
    "mask.": "masculine",
    "fem.": "feminine",
    "neutr.": "neuter",
}


def first_text(items: list[str] | None) -> str | None:
    if not items:
        return None
    value = str(items[0]).strip()
    return value or None


def entry_lemma(item: dict) -> str | None:
    for candidate in item.get("sch") or []:
        lemma = str(candidate.get("lemma") or "").strip()
        if lemma:
            return lemma
    return None


def make_searchable_text(entry: VocabularyEntry) -> str:
    tags = " ".join(tag.name for tag in entry.tags)
    pieces = [
        entry.lemma,
        entry.part_of_speech or "",
        entry.article or "",
        entry.gender or "",
        entry.cefr_level or "",
        tags,
    ]
    return " ".join(piece for piece in pieces if piece).strip()


def add_tag(entry: VocabularyEntry, name: str, tag_type: str) -> bool:
    if any(tag.name == name for tag in entry.tags):
        return False
    entry.tags.append(EntryTag(name=name, tag_type=tag_type))
    return True


def import_file(path: Path) -> dict[str, int]:
    level = path.stem.upper()
    goethe_tag = f"Goethe {level}"
    items = json.loads(path.read_text(encoding="utf-8"))
    created = 0
    updated = 0
    skipped = 0

    with SessionLocal() as session:
        create_search_index()
        for item in items:
            lemma = entry_lemma(item)
            if not lemma:
                skipped += 1
                continue

            normalized = normalize_lemma(lemma)
            entry = session.scalars(
                select(VocabularyEntry)
                .options(selectinload(VocabularyEntry.tags))
                .where(VocabularyEntry.normalized_lemma == normalized)
            ).first()

            if entry is None:
                pos = POS_MAP.get(str(item.get("pos") or "").strip(), str(item.get("pos") or "").strip() or None)
                article = first_text(item.get("articles"))
                gender = GENDER_MAP.get(first_text(item.get("genera")) or "")
                raw_payload = {"goethe": {level: item}}
                entry = VocabularyEntry(
                    lemma=lemma,
                    normalized_lemma=normalized,
                    language="de",
                    part_of_speech=pos,
                    gender=gender,
                    article=article,
                    cefr_level=level,
                    source_type="goethe",
                    source_ref=str(item.get("url") or ""),
                    extra_data={"goethe_levels": [level]},
                    raw_payload=raw_payload,
                )
                session.add(entry)
                created += 1
            else:
                changed = False
                extra_data = dict(entry.extra_data or {})
                goethe_levels = list(extra_data.get("goethe_levels") or [])
                if level not in goethe_levels:
                    goethe_levels.append(level)
                    extra_data["goethe_levels"] = sorted(goethe_levels)
                    entry.extra_data = extra_data
                    changed = True
                raw_payload = dict(entry.raw_payload or {})
                goethe_payload = dict(raw_payload.get("goethe") or {})
                if level not in goethe_payload:
                    goethe_payload[level] = item
                    raw_payload["goethe"] = goethe_payload
                    entry.raw_payload = raw_payload
                    changed = True
                if not entry.cefr_level:
                    entry.cefr_level = level
                    changed = True
                if not entry.source_ref and item.get("url"):
                    entry.source_ref = str(item["url"])
                    changed = True
                if changed:
                    updated += 1

            if add_tag(entry, goethe_tag, "Goethe"):
                updated += 1

            add_tag(entry, "Goethe", "source")
            entry.searchable_text = make_searchable_text(entry)
            session.flush()
            sync_entry_search(session, entry)

        session.commit()

    return {"created": created, "updated": updated, "skipped": skipped, "total": len(items)}


def main() -> None:
    totals = {"created": 0, "updated": 0, "skipped": 0, "total": 0}
    for path in sorted(GOETHE_DIR.glob("*.json")):
        result = import_file(path)
        for key, value in result.items():
            totals[key] += value
        print(f"{path.name}: {result}")
    print(f"TOTAL: {totals}")


if __name__ == "__main__":
    main()
