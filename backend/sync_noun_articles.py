from __future__ import annotations

from sqlalchemy import select

from backend.app.db import Base, SessionLocal, engine
from backend.app.main import create_search_index, sync_entry_search
from backend.app.models import VocabularyEntry


ARTICLE_BY_GENDER = {
    "der": "der",
    "die": "die",
    "das": "das",
    "masculine": "der",
    "feminine": "die",
    "neuter": "das",
    "mask.": "der",
    "fem.": "die",
    "neutr.": "das",
    "der/die": "der/die",
}


def article_from_raw_payload(entry: VocabularyEntry) -> str | None:
    raw = entry.raw_payload or {}
    article = raw.get("article")
    if article in {"der", "die", "das"}:
        return article

    gender = raw.get("gender")
    if gender in ARTICLE_BY_GENDER:
        return ARTICLE_BY_GENDER[gender]

    articles = raw.get("articles")
    if isinstance(articles, list):
        for item in articles:
            if item in {"der", "die", "das"}:
                return item

    goethe = raw.get("goethe")
    if isinstance(goethe, dict):
        for payload in goethe.values():
            if not isinstance(payload, dict):
                continue
            if payload.get("onlypl"):
                return "die"
            articles = payload.get("articles")
            if isinstance(articles, list):
                for item in articles:
                    if item in {"der", "die", "das"}:
                        return item
            genera = payload.get("genera")
            if isinstance(genera, list):
                for item in genera:
                    if item in ARTICLE_BY_GENDER:
                        return ARTICLE_BY_GENDER[item]
    return None


def article_for_entry(entry: VocabularyEntry) -> str | None:
    article = (entry.article or "").strip().lower()
    if article in {"der", "die", "das"}:
        return article

    gender = (entry.gender or "").strip().lower()
    if gender in ARTICLE_BY_GENDER:
        return ARTICLE_BY_GENDER[gender]

    lemma_start = entry.lemma.strip().split(" ", 1)[0].lower()
    if lemma_start in {"der", "die", "das"}:
        return lemma_start

    return article_from_raw_payload(entry)


def main() -> None:
    Base.metadata.create_all(bind=engine)
    create_search_index()
    updated = 0
    with SessionLocal() as session:
        entries = session.scalars(
            select(VocabularyEntry).where(VocabularyEntry.part_of_speech == "noun")
        ).all()
        changed_entries: list[VocabularyEntry] = []
        for entry in entries:
            article = article_for_entry(entry)
            if not article:
                continue
            changed = False
            if entry.article != article:
                entry.article = article
                changed = True
            if (entry.gender or "").strip().lower() in {"masculine", "feminine", "neuter", "mask.", "fem.", "neutr."}:
                entry.gender = article
                changed = True
            if changed:
                changed_entries.append(entry)
                updated += 1
        session.flush()
        for entry in changed_entries:
            sync_entry_search(session, entry)
        session.commit()
    print(f"Updated {updated} noun articles.")


if __name__ == "__main__":
    main()
