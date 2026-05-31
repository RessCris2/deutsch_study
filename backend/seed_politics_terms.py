from __future__ import annotations

from sqlalchemy import select

from backend.app.db import Base, SessionLocal, engine
from backend.app.main import (
    WRITE_LOCK,
    apply_payload,
    create_search_index,
    normalize_lemma,
    sync_entry_search,
)
from backend.app.models import EntryForm, EntryTag, ExampleSentence, Meaning, VocabularyEntry
from backend.app.schemas import EntryCreate


NOUNS = [
    ("die Politik", "die Politiken", "政治；政策", "general"),
    ("der Staat", "die Staaten", "国家", "government"),
    ("die Regierung", "die Regierungen", "政府", "government"),
    ("das Parlament", "die Parlamente", "议会", "government"),
    ("der Bundestag", "die Bundestage", "联邦议院", "government"),
    ("der Bundesrat", "die Bundesräte", "联邦参议院", "government"),
    ("das Ministerium", "die Ministerien", "部；部门", "government"),
    ("der Minister", "die Minister", "部长", "government"),
    ("die Ministerin", "die Ministerinnen", "女部长", "government"),
    ("der Kanzler", "die Kanzler", "总理", "government"),
    ("die Kanzlerin", "die Kanzlerinnen", "女总理", "government"),
    ("der Präsident", "die Präsidenten", "总统；主席", "government"),
    ("die Präsidentin", "die Präsidentinnen", "女总统；女主席", "government"),
    ("die Behörde", "die Behörden", "政府机关；行政部门", "government"),
    ("die Verwaltung", "die Verwaltungen", "行政管理；管理机构", "government"),
    ("die Demokratie", "die Demokratien", "民主", "system"),
    ("die Diktatur", "die Diktaturen", "独裁", "system"),
    ("die Republik", "die Republiken", "共和国", "system"),
    ("die Verfassung", "die Verfassungen", "宪法", "system"),
    ("der Föderalismus", "die Föderalismen", "联邦制", "system"),
    ("die Gewaltenteilung", "die Gewaltenteilungen", "三权分立", "system"),
    ("die Opposition", "die Oppositionen", "反对派", "party"),
    ("die Koalition", "die Koalitionen", "联合执政；联盟", "party"),
    ("die Fraktion", "die Fraktionen", "议会党团", "party"),
    ("die Partei", "die Parteien", "政党", "party"),
    ("der Abgeordnete", "die Abgeordneten", "议员", "party"),
    ("die Abgeordnete", "die Abgeordneten", "女议员", "party"),
    ("der Kandidat", "die Kandidaten", "候选人", "election"),
    ("die Kandidatin", "die Kandidatinnen", "女候选人", "election"),
    ("die Wahl", "die Wahlen", "选举", "election"),
    ("der Wahlkampf", "die Wahlkämpfe", "竞选活动", "election"),
    ("die Stimme", "die Stimmen", "选票；声音", "election"),
    ("der Wähler", "die Wähler", "选民", "election"),
    ("die Wählerin", "die Wählerinnen", "女选民", "election"),
    ("die Mehrheit", "die Mehrheiten", "多数", "election"),
    ("die Minderheit", "die Minderheiten", "少数", "election"),
    ("die Umfrage", "die Umfragen", "民意调查", "election"),
    ("das Wahlergebnis", "die Wahlergebnisse", "选举结果", "election"),
    ("die Abstimmung", "die Abstimmungen", "投票表决", "election"),
    ("das Referendum", "die Referenden", "公民投票", "election"),
    ("das Gesetz", "die Gesetze", "法律", "law_policy"),
    ("der Gesetzentwurf", "die Gesetzentwürfe", "法案草案", "law_policy"),
    ("die Reform", "die Reformen", "改革", "law_policy"),
    ("die Verordnung", "die Verordnungen", "条例；法令", "law_policy"),
    ("die Regelung", "die Regelungen", "规定；安排", "law_policy"),
    ("die Entscheidung", "die Entscheidungen", "决定", "law_policy"),
    ("der Beschluss", "die Beschlüsse", "决议", "law_policy"),
    ("die Maßnahme", "die Maßnahmen", "措施", "law_policy"),
    ("die Sanktion", "die Sanktionen", "制裁；处罚", "law_policy"),
    ("die Steuer", "die Steuern", "税", "law_policy"),
    ("der Haushalt", "die Haushalte", "预算；财政", "law_policy"),
    ("die Subvention", "die Subventionen", "补贴", "law_policy"),
    ("die Migration", "die Migrationen", "移民；迁移", "society"),
    ("die Integration", "die Integrationen", "融合；一体化", "society"),
    ("die Bildung", "die Bildungen", "教育", "society"),
    ("die Gesundheit", "die Gesundheiten", "健康；医疗", "society"),
    ("die Sicherheit", "die Sicherheiten", "安全", "society"),
    ("die Rente", "die Renten", "养老金", "society"),
    ("die Armut", "die Armuten", "贫困", "society"),
    ("die Ungleichheit", "die Ungleichheiten", "不平等", "society"),
    ("der Klimaschutz", "die Klimaschutzmaßnahmen", "气候保护", "society"),
    ("die Energiepolitik", "die Energiepolitiken", "能源政策", "society"),
    ("die Außenpolitik", "die Außenpolitiken", "外交政策", "international"),
    ("die Innenpolitik", "die Innenpolitiken", "国内政治", "general"),
    ("die Europäische Union", "die Europäischen Unionen", "欧盟", "international"),
    ("die NATO", "die NATOs", "北约", "international"),
    ("die Grenze", "die Grenzen", "边界；国境", "international"),
    ("der Konflikt", "die Konflikte", "冲突", "international"),
    ("der Krieg", "die Kriege", "战争", "international"),
    ("der Frieden", "die Frieden", "和平", "international"),
    ("der Vertrag", "die Verträge", "条约；合同", "international"),
    ("die Verhandlung", "die Verhandlungen", "谈判", "international"),
    ("der Botschafter", "die Botschafter", "大使", "international"),
    ("die Botschafterin", "die Botschafterinnen", "女大使", "international"),
    ("die Presse", "die Pressen", "媒体；新闻界", "media"),
    ("die Pressekonferenz", "die Pressekonferenzen", "新闻发布会", "media"),
    ("die Nachricht", "die Nachrichten", "消息；新闻", "media"),
    ("die Debatte", "die Debatten", "辩论", "media"),
    ("die Kritik", "die Kritiken", "批评", "media"),
    ("der Skandal", "die Skandale", "丑闻", "media"),
    ("die Transparenz", "die Transparenzen", "透明度", "media"),
    ("die Korruption", "die Korruptionen", "腐败", "media"),
    ("die Menschenrechte", "die Menschenrechte", "人权", "rights"),
    ("die Freiheit", "die Freiheiten", "自由", "rights"),
    ("die Gleichberechtigung", "die Gleichberechtigungen", "平等权利", "rights"),
    ("die Meinungsfreiheit", "die Meinungsfreiheiten", "言论自由", "rights"),
    ("der Datenschutz", "die Datenschutzregelungen", "数据保护", "rights"),
    ("das Asyl", "die Asyle", "庇护", "rights"),
]


OTHER_WORDS = [
    ("regieren", "verb", "执政；治理", "government"),
    ("wählen", "verb", "选举；投票", "election"),
    ("abstimmen", "verb", "投票表决", "election"),
    ("kandidieren", "verb", "参选", "election"),
    ("gewinnen", "verb", "赢得", "election"),
    ("verlieren", "verb", "失去；输掉", "election"),
    ("beschließen", "verb", "决定；通过决议", "law_policy"),
    ("verabschieden", "verb", "通过法律；告别", "law_policy"),
    ("fordern", "verb", "要求", "media"),
    ("kritisieren", "verb", "批评", "media"),
    ("unterstützen", "verb", "支持", "party"),
    ("ablehnen", "verb", "拒绝；反对", "party"),
    ("verhandeln", "verb", "谈判", "international"),
    ("vereinbaren", "verb", "约定；达成协议", "international"),
    ("reformieren", "verb", "改革", "law_policy"),
    ("fördern", "verb", "促进；资助", "law_policy"),
    ("verbieten", "verb", "禁止", "law_policy"),
    ("erlauben", "verb", "允许", "law_policy"),
    ("schützen", "verb", "保护", "rights"),
    ("verletzen", "verb", "侵犯；违反", "rights"),
    ("demokratisch", "adjective", "民主的", "system"),
    ("autoritär", "adjective", "威权的", "system"),
    ("konservativ", "adjective", "保守的", "party"),
    ("liberal", "adjective", "自由主义的", "party"),
    ("sozial", "adjective", "社会的；社会福利的", "society"),
    ("rechts", "adjective", "右翼的；右边的", "party"),
    ("links", "adjective", "左翼的；左边的", "party"),
    ("umstritten", "adjective", "有争议的", "media"),
    ("öffentlich", "adjective", "公开的；公共的", "media"),
    ("staatlich", "adjective", "国家的；政府的", "government"),
    ("international", "adjective", "国际的", "international"),
    ("innenpolitisch", "adjective", "国内政治的", "general"),
    ("außenpolitisch", "adjective", "外交政策的", "international"),
]


CATEGORY_LABELS = {
    "general": "政治通用",
    "government": "政府机构",
    "system": "政治制度",
    "party": "政党议会",
    "election": "选举投票",
    "law_policy": "法律政策",
    "society": "社会议题",
    "international": "国际关系",
    "media": "政治新闻",
    "rights": "权利自由",
}


def noun_entry(article_lemma: str, plural: str, zh: str, category: str) -> EntryCreate:
    article, lemma = article_lemma.split(" ", 1)
    example_head = f"{article.capitalize()} {lemma}"
    return EntryCreate(
        lemma=lemma,
        part_of_speech="noun",
        article=article,
        gender=article,
        plural_form=plural,
        cefr_level="B1",
        source_type="politics_seed",
        meanings=[{"language": "zh", "gloss": zh}],
        forms=[{"label": "plural", "value": plural}],
        examples=[
            {
                "german_text": f"{example_head} ist in politischen Nachrichten häufig.",
                "chinese_text": f"{zh}在政治新闻中很常见。",
            }
        ],
        tags=[
            {"name": "政治场景", "tag_type": "公共事务"},
            {"name": CATEGORY_LABELS[category], "tag_type": "公共事务"},
            {"name": "名词", "tag_type": "语言属性"},
        ],
        extra_data={"domains": ["politics", category]},
    )


def word_entry(lemma: str, part_of_speech: str, zh: str, category: str) -> EntryCreate:
    return EntryCreate(
        lemma=lemma,
        part_of_speech=part_of_speech,
        cefr_level="B1",
        source_type="politics_seed",
        meanings=[{"language": "zh", "gloss": zh}],
        examples=[
            {
                "german_text": f"Man sollte {lemma} im politischen Kontext verstehen.",
                "chinese_text": f"政治语境中需要理解“{zh}”。",
            }
        ],
        tags=[
            {"name": "政治场景", "tag_type": "公共事务"},
            {"name": CATEGORY_LABELS[category], "tag_type": "公共事务"},
            {"name": part_of_speech, "tag_type": "语言属性"},
        ],
        extra_data={"domains": ["politics", category]},
    )


def merge_payload(entry: VocabularyEntry, payload: EntryCreate) -> bool:
    changed = False
    if not entry.part_of_speech and payload.part_of_speech:
        entry.part_of_speech = payload.part_of_speech
        changed = True
    if not entry.article and payload.article:
        entry.article = payload.article
        changed = True
    if not entry.gender and payload.gender:
        entry.gender = payload.gender
        changed = True
    if not entry.plural_form and payload.plural_form:
        entry.plural_form = payload.plural_form
        changed = True
    if not entry.cefr_level and payload.cefr_level:
        entry.cefr_level = payload.cefr_level
        changed = True

    existing_meanings = {(item.language, item.gloss) for item in entry.meanings}
    for item in payload.meanings:
        key = (item.language, item.gloss)
        if key not in existing_meanings:
            entry.meanings.append(
                Meaning(
                    sort_order=len(entry.meanings),
                    language=item.language,
                    gloss=item.gloss,
                    detail=item.detail,
                )
            )
            existing_meanings.add(key)
            changed = True

    existing_forms = {(item.label, item.value) for item in entry.forms}
    for item in payload.forms:
        key = (item.label, item.value)
        if key not in existing_forms:
            entry.forms.append(EntryForm(label=item.label, value=item.value, note=item.note))
            existing_forms.add(key)
            changed = True

    existing_examples = {item.german_text for item in entry.examples}
    for item in payload.examples:
        if item.german_text not in existing_examples:
            entry.examples.append(
                ExampleSentence(
                    german_text=item.german_text,
                    chinese_text=item.chinese_text,
                    note=item.note,
                )
            )
            existing_examples.add(item.german_text)
            changed = True

    existing_tags = {item.name for item in entry.tags}
    for item in payload.tags:
        name = item.name.strip()
        if name and name not in existing_tags:
            entry.tags.append(EntryTag(name=name, tag_type=item.tag_type))
            existing_tags.add(name)
            changed = True

    extra_data = dict(entry.extra_data or {})
    domains = set(extra_data.get("domains") or [])
    payload_domains = set(payload.extra_data.get("domains") or [])
    if payload_domains - domains:
        extra_data["domains"] = sorted(domains | payload_domains)
        entry.extra_data = extra_data
        changed = True

    return changed


def import_entries(payloads: list[EntryCreate]) -> tuple[int, int]:
    create_search_index()
    with WRITE_LOCK:
        inserted = 0
        merged = 0
        with SessionLocal() as session:
            changed_entries: list[VocabularyEntry] = []
            for payload in payloads:
                existing = session.scalars(
                    select(VocabularyEntry).where(
                        VocabularyEntry.normalized_lemma == normalize_lemma(payload.lemma)
                    )
                ).first()
                if existing:
                    if merge_payload(existing, payload):
                        changed_entries.append(existing)
                        merged += 1
                    continue
                entry = VocabularyEntry(lemma="", normalized_lemma="")
                apply_payload(entry, payload, session=session)
                session.add(entry)
                changed_entries.append(entry)
                inserted += 1
            session.flush()
            for entry in changed_entries:
                sync_entry_search(session, entry)
            session.commit()
        return inserted, merged


def main() -> None:
    Base.metadata.create_all(bind=engine)
    payloads = [noun_entry(*item) for item in NOUNS]
    payloads.extend(word_entry(*item) for item in OTHER_WORDS)
    inserted, merged = import_entries(payloads)
    print(f"Inserted {inserted} and enriched {merged} politics entries.")


if __name__ == "__main__":
    main()
