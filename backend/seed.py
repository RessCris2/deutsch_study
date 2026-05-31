from backend.app.db import Base, SessionLocal, engine
from backend.app.main import upsert_entries
from backend.app.schemas import EntryCreate


SAMPLE_ENTRIES = [
    EntryCreate(
        lemma="der Antrag",
        part_of_speech="noun",
        word_category="formal",
        gender="masculine",
        article="der",
        plural_form="die Antraege",
        cefr_level="B1",
        source_type="seed",
        meanings=[
            {"language": "zh", "gloss": "申请"},
            {"language": "zh", "gloss": "请求"},
        ],
        collocations=[
            {"phrase": "einen Antrag stellen", "meaning": "提出申请"},
            {"phrase": "den Antrag genehmigen", "meaning": "批准申请"},
        ],
        examples=[
            {"german_text": "Ich moechte einen Antrag auf Verlaengerung stellen.", "chinese_text": "我想提交延期申请。"}
        ],
        tags=[{"name": "bureaucracy"}, {"name": "B1"}],
        extra_data={"domains": ["office", "paperwork"]},
    ),
    EntryCreate(
        lemma="beantragen",
        part_of_speech="verb",
        word_category="formal",
        source_type="seed",
        meanings=[{"language": "zh", "gloss": "申请"}],
        forms=[
            {"label": "past", "value": "beantragte"},
            {"label": "partizip_ii", "value": "beantragt"},
        ],
        collocations=[{"phrase": "einen Pass beantragen", "meaning": "申请护照"}],
        examples=[
            {"german_text": "Sie hat rechtzeitig ein Visum beantragt.", "chinese_text": "她及时申请了签证。"}
        ],
        tags=[{"name": "bureaucracy"}, {"name": "verb"}],
        extra_data={"valency": "etwas beantragen"},
    ),
]


def main() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        upsert_entries(session, SAMPLE_ENTRIES)


if __name__ == "__main__":
    main()
