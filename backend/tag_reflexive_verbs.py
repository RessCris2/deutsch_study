from __future__ import annotations

import re

from sqlalchemy import select

from backend.app.db import SessionLocal
from backend.app.main import WRITE_LOCK, normalize_lemma, sync_entry_search
from backend.app.models import EntryTag, VocabularyEntry


REFLEXIVE_TAG = "反身动词"
NON_REFLEXIVE_TAG = "非反身动词"
TAG_TYPE = "语言属性"

REFLEXIVE_LEMMAS = {
    "abkühlen",
    "abmelden",
    "absprechen",
    "abzeichnen",
    "ändern",
    "anmelden",
    "aneignen",
    "anfühlen",
    "anhören",
    "ankündigen",
    "anpassen",
    "anschauen",
    "ansehen",
    "anstrengen",
    "anziehen",
    "ärgern",
    "aufhalten",
    "aufregen",
    "auskennen",
    "ausruhen",
    "ausschlafen",
    "auswirken",
    "bedanken",
    "beeilen",
    "befassen",
    "befinden",
    "begeben",
    "begeistern",
    "beklagen",
    "bemühen",
    "benehmen",
    "beraten",
    "beruhigen",
    "beschäftigen",
    "beschweren",
    "bewerben",
    "beziehen",
    "decken",
    "drehen",
    "eignen",
    "einbilden",
    "einigen",
    "einleben",
    "einmischen",
    "einschreiben",
    "einsetzen",
    "entscheiden",
    "entschließen",
    "entschuldigen",
    "entspannen",
    "entwickeln",
    "ergeben",
    "erholen",
    "erinnern",
    "erkälten",
    "erkundigen",
    "ernähren",
    "erschrecken",
    "fühlen",
    "fürchten",
    "gedulden",
    "gewöhnen",
    "handeln",
    "interessieren",
    "irren",
    "kümmern",
    "melden",
    "merken",
    "nähern",
    "rechnen",
    "schämen",
    "setzen",
    "spezialisieren",
    "streiten",
    "täuschen",
    "treffen",
    "umdrehen",
    "umsehen",
    "umziehen",
    "unterhalten",
    "unterscheiden",
    "verabreden",
    "verabschieden",
    "verändern",
    "verhalten",
    "verirren",
    "verlieben",
    "verlassen",
    "verlaufen",
    "verletzen",
    "verschlechtern",
    "verschreiben",
    "verspäten",
    "verstehen",
    "vertragen",
    "verwandeln",
    "vorbereiten",
    "vornehmen",
    "vorstellen",
    "wenden",
    "wundern",
    "zurückziehen",
}

REFLEXIVE_PATTERN = re.compile(r"\bsich\b", re.IGNORECASE)


def base_lemma(value: str) -> str:
    normalized = normalize_lemma(value)
    normalized = re.sub(r"^sich\s+", "", normalized)
    normalized = re.sub(r"\s+sich$", "", normalized)
    return normalized.strip()


def is_reflexive(entry: VocabularyEntry) -> bool:
    lemma = base_lemma(entry.lemma)
    if lemma in REFLEXIVE_LEMMAS:
        return True
    chunks = [
        entry.lemma or "",
        entry.searchable_text or "",
        " ".join(item.value for item in entry.forms),
        " ".join(item.phrase for item in entry.collocations),
        " ".join(item.german_text for item in entry.examples),
    ]
    return bool(REFLEXIVE_PATTERN.search(" ".join(chunks)))


def set_reflexive_tag(entry: VocabularyEntry, reflexive: bool) -> bool:
    wanted = REFLEXIVE_TAG if reflexive else NON_REFLEXIVE_TAG
    unwanted = NON_REFLEXIVE_TAG if reflexive else REFLEXIVE_TAG
    changed = False

    before = len(entry.tags)
    entry.tags = [tag for tag in entry.tags if tag.name != unwanted]
    if len(entry.tags) != before:
        changed = True

    existing = next((tag for tag in entry.tags if tag.name == wanted), None)
    if existing:
        if existing.tag_type != TAG_TYPE:
            existing.tag_type = TAG_TYPE
            changed = True
        return changed

    entry.tags.append(EntryTag(name=wanted, tag_type=TAG_TYPE))
    return True


def main() -> None:
    with WRITE_LOCK:
        with SessionLocal() as session:
            verbs = session.scalars(
                select(VocabularyEntry).where(VocabularyEntry.part_of_speech == "verb")
            ).unique().all()
            reflexive_count = 0
            non_reflexive_count = 0
            changed_entries = []
            for entry in verbs:
                reflexive = is_reflexive(entry)
                if reflexive:
                    reflexive_count += 1
                else:
                    non_reflexive_count += 1
                if set_reflexive_tag(entry, reflexive):
                    changed_entries.append(entry)
            session.flush()
            for entry in changed_entries:
                sync_entry_search(session, entry)
            session.commit()
    print(
        f"Tagged {len(verbs)} verbs: {reflexive_count} reflexive, "
        f"{non_reflexive_count} non-reflexive; changed {len(changed_entries)} entries."
    )


if __name__ == "__main__":
    main()
