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
    ("das Auto", "die Autos", "汽车", "vehicle"),
    ("der Pkw", "die Pkw", "小汽车；乘用车", "vehicle"),
    ("der Lkw", "die Lkw", "卡车", "vehicle"),
    ("das Motorrad", "die Motorräder", "摩托车", "vehicle"),
    ("das Fahrrad", "die Fahrräder", "自行车", "vehicle"),
    ("der Anhänger", "die Anhänger", "挂车；拖车", "vehicle"),
    ("der Fahrer", "die Fahrer", "驾驶员", "person"),
    ("der Fußgänger", "die Fußgänger", "行人", "person"),
    ("der Radfahrer", "die Radfahrer", "骑自行车的人", "person"),
    ("das Kind", "die Kinder", "儿童", "person"),
    ("der Fahranfänger", "die Fahranfänger", "新手驾驶员", "person"),
    ("der Verkehr", "die Verkehre", "交通", "traffic"),
    ("der Gegenverkehr", "die Gegenverkehre", "对向交通；迎面来车", "traffic"),
    ("der Querverkehr", "die Querverkehre", "横向交通", "traffic"),
    ("der Kreisverkehr", "die Kreisverkehre", "环岛", "traffic"),
    ("der Stau", "die Staus", "堵车", "traffic"),
    ("die Kreuzung", "die Kreuzungen", "十字路口", "road"),
    ("die Einmündung", "die Einmündungen", "丁字路口；汇入口", "road"),
    ("die Fahrbahn", "die Fahrbahnen", "车行道", "road"),
    ("der Fahrstreifen", "die Fahrstreifen", "车道", "road"),
    ("die Spur", "die Spuren", "车道；轨迹", "road"),
    ("der Seitenstreifen", "die Seitenstreifen", "路肩；应急停车带", "road"),
    ("der Gehweg", "die Gehwege", "人行道", "road"),
    ("der Radweg", "die Radwege", "自行车道", "road"),
    ("der Zebrastreifen", "die Zebrastreifen", "斑马线", "road"),
    ("der Bahnübergang", "die Bahnübergänge", "铁路道口", "road"),
    ("die Autobahn", "die Autobahnen", "高速公路", "road"),
    ("die Landstraße", "die Landstraßen", "乡间公路；国道", "road"),
    ("die Baustelle", "die Baustellen", "施工路段", "road"),
    ("die Kurve", "die Kurven", "弯道", "road"),
    ("die Steigung", "die Steigungen", "上坡", "road"),
    ("das Gefälle", "die Gefälle", "下坡；坡度", "road"),
    ("das Verkehrszeichen", "die Verkehrszeichen", "交通标志", "sign"),
    ("das Gefahrzeichen", "die Gefahrzeichen", "警告标志", "sign"),
    ("das Vorschriftzeichen", "die Vorschriftzeichen", "禁令/指令标志", "sign"),
    ("das Richtzeichen", "die Richtzeichen", "指示标志", "sign"),
    ("das Stoppschild", "die Stoppschilder", "停车让行标志", "sign"),
    ("die Ampel", "die Ampeln", "红绿灯", "sign"),
    ("das Blinklicht", "die Blinklichter", "闪光灯", "sign"),
    ("die Geschwindigkeitsbegrenzung", "die Geschwindigkeitsbegrenzungen", "限速", "rule"),
    ("die Vorfahrt", "die Vorfahrten", "优先通行权", "rule"),
    ("die Vorfahrtsregel", "die Vorfahrtsregeln", "优先通行规则", "rule"),
    ("die Wartepflicht", "die Wartepflichten", "等待/让行义务", "rule"),
    ("der Sicherheitsabstand", "die Sicherheitsabstände", "安全距离", "rule"),
    ("der Bremsweg", "die Bremswege", "制动距离", "rule"),
    ("der Reaktionsweg", "die Reaktionswege", "反应距离", "rule"),
    ("der Anhalteweg", "die Anhaltewege", "停车距离", "rule"),
    ("die Geschwindigkeit", "die Geschwindigkeiten", "速度", "rule"),
    ("die Höchstgeschwindigkeit", "die Höchstgeschwindigkeiten", "最高速度", "rule"),
    ("die Richtgeschwindigkeit", "die Richtgeschwindigkeiten", "建议速度", "rule"),
    ("das Überholverbot", "die Überholverbote", "禁止超车", "rule"),
    ("die Umweltzone", "die Umweltzonen", "环保区", "rule"),
    ("die Rettungsgasse", "die Rettungsgassen", "救援通道", "emergency"),
    ("der Unfall", "die Unfälle", "事故", "emergency"),
    ("die Unfallstelle", "die Unfallstellen", "事故现场", "emergency"),
    ("die Panne", "die Pannen", "故障；抛锚", "emergency"),
    ("das Warndreieck", "die Warndreiecke", "三角警示牌", "emergency"),
    ("die Warnblinkanlage", "die Warnblinkanlagen", "双闪警示灯", "emergency"),
    ("der Notruf", "die Notrufe", "紧急呼叫", "emergency"),
    ("die Erste Hilfe", "die Erste-Hilfe-Maßnahmen", "急救", "emergency"),
    ("der Verbandskasten", "die Verbandskästen", "急救箱", "emergency"),
    ("die Gefahr", "die Gefahren", "危险", "hazard"),
    ("die Sicht", "die Sichten", "视野；能见度", "hazard"),
    ("der Nebel", "die Nebel", "雾", "hazard"),
    ("die Glätte", "die Glätten", "路滑；结冰", "hazard"),
    ("das Aquaplaning", "die Aquaplanings", "水滑", "hazard"),
    ("der Wildwechsel", "die Wildwechsel", "野生动物穿行", "hazard"),
    ("der tote Winkel", "die toten Winkel", "盲区", "hazard"),
    ("die Ablenkung", "die Ablenkungen", "分心", "hazard"),
    ("die Müdigkeit", "die Müdigkeiten", "疲劳", "hazard"),
    ("der Alkohol", "die Alkohole", "酒精", "hazard"),
    ("das Handy", "die Handys", "手机", "hazard"),
    ("der Gurt", "die Gurte", "安全带", "vehicle_part"),
    ("der Sicherheitsgurt", "die Sicherheitsgurte", "安全带", "vehicle_part"),
    ("der Airbag", "die Airbags", "安全气囊", "vehicle_part"),
    ("der Spiegel", "die Spiegel", "后视镜；镜子", "vehicle_part"),
    ("der Blinker", "die Blinker", "转向灯", "vehicle_part"),
    ("das Abblendlicht", "die Abblendlichter", "近光灯", "vehicle_part"),
    ("das Fernlicht", "die Fernlichter", "远光灯", "vehicle_part"),
    ("das Bremslicht", "die Bremslichter", "刹车灯", "vehicle_part"),
    ("der Reifen", "die Reifen", "轮胎", "vehicle_part"),
    ("der Reifendruck", "die Reifendrücke", "胎压", "vehicle_part"),
    ("die Bremse", "die Bremsen", "刹车", "vehicle_part"),
    ("die Kupplung", "die Kupplungen", "离合器", "vehicle_part"),
    ("das Lenkrad", "die Lenkräder", "方向盘", "vehicle_part"),
    ("der Motor", "die Motoren", "发动机", "vehicle_part"),
    ("der Kraftstoff", "die Kraftstoffe", "燃料", "vehicle_part"),
    ("der Führerschein", "die Führerscheine", "驾照", "law"),
    ("die Probezeit", "die Probezeiten", "实习期", "law"),
    ("der Bußgeldbescheid", "die Bußgeldbescheide", "罚款通知", "law"),
    ("das Bußgeld", "die Bußgelder", "罚款", "law"),
    ("der Punkt", "die Punkte", "扣分；分数", "law"),
    ("das Fahrverbot", "die Fahrverbote", "禁驾", "law"),
    ("die Versicherung", "die Versicherungen", "保险", "law"),
    ("die Zulassung", "die Zulassungen", "车辆注册；上牌", "law"),
    ("die Hauptuntersuchung", "die Hauptuntersuchungen", "车辆年检", "law"),
    ("die Plakette", "die Plaketten", "贴标；检验标", "law"),
]


OTHER_WORDS = [
    ("fahren", "verb", "驾驶；行驶", "action"),
    ("bremsen", "verb", "刹车", "action"),
    ("anhalten", "verb", "停车；停下", "action"),
    ("halten", "verb", "停靠；停住", "action"),
    ("parken", "verb", "停车泊车", "action"),
    ("einparken", "verb", "驶入车位", "action"),
    ("ausparken", "verb", "驶出车位", "action"),
    ("abbiegen", "verb", "转弯", "action"),
    ("wenden", "verb", "掉头", "action"),
    ("überholen", "verb", "超车", "action"),
    ("einscheren", "verb", "并回车道；插入车流", "action"),
    ("ausweichen", "verb", "避让", "action"),
    ("beschleunigen", "verb", "加速", "action"),
    ("verlangsamen", "verb", "减速", "action"),
    ("blinken", "verb", "打转向灯", "action"),
    ("hupen", "verb", "按喇叭", "action"),
    ("anschnallen", "verb", "系安全带", "action"),
    ("beachten", "verb", "注意；遵守", "action"),
    ("missachten", "verb", "无视；违反", "action"),
    ("gefährden", "verb", "危及；造成危险", "hazard"),
    ("behindern", "verb", "妨碍", "hazard"),
    ("verzichten", "verb", "放弃；不做", "action"),
    ("reagieren", "verb", "反应", "action"),
    ("sichern", "verb", "确保安全；固定", "action"),
    ("abschleppen", "verb", "拖车", "emergency"),
    ("übermüdet", "adjective", "过度疲劳的", "hazard"),
    ("betrunken", "adjective", "醉酒的", "hazard"),
    ("rutschig", "adjective", "湿滑的", "hazard"),
    ("glatt", "adjective", "光滑的；结冰打滑的", "hazard"),
    ("nass", "adjective", "湿的", "hazard"),
    ("eng", "adjective", "狭窄的", "road"),
    ("unübersichtlich", "adjective", "视线不清的；难以看清的", "hazard"),
    ("verkehrsberuhigt", "adjective", "交通宁静化的；限速慢行的", "rule"),
    ("zulässig", "adjective", "允许的；合法的", "law"),
    ("verboten", "adjective", "禁止的", "law"),
    ("pflichtig", "adjective", "有义务的", "law"),
    ("rechts", "adverb", "右侧；向右", "direction"),
    ("links", "adverb", "左侧；向左", "direction"),
    ("geradeaus", "adverb", "直行", "direction"),
    ("rückwärts", "adverb", "倒车；向后", "direction"),
    ("innerorts", "adverb", "市区内", "rule"),
    ("außerorts", "adverb", "市区外", "rule"),
]


CATEGORY_LABELS = {
    "vehicle": "车辆类型",
    "person": "交通参与者",
    "traffic": "交通状况",
    "road": "道路场景",
    "sign": "交通标志",
    "rule": "交通规则",
    "emergency": "事故应急",
    "hazard": "危险因素",
    "vehicle_part": "车辆部件",
    "law": "驾照法规",
    "action": "驾驶动作",
    "direction": "方向位置",
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
        source_type="driving_theory_seed",
        meanings=[{"language": "zh", "gloss": zh}],
        forms=[{"label": "plural", "value": plural}],
        examples=[
            {
                "german_text": f"{example_head} ist in der Theorieprüfung wichtig.",
                "chinese_text": f"{zh}在理论考试中很重要。",
            }
        ],
        tags=[
            {"name": "驾照理论", "tag_type": "交通出行"},
            {"name": CATEGORY_LABELS[category], "tag_type": "交通出行"},
            {"name": "名词", "tag_type": "语言属性"},
        ],
        extra_data={"domains": ["driving_theory", category]},
    )


def word_entry(lemma: str, part_of_speech: str, zh: str, category: str) -> EntryCreate:
    return EntryCreate(
        lemma=lemma,
        part_of_speech=part_of_speech,
        cefr_level="B1",
        source_type="driving_theory_seed",
        meanings=[{"language": "zh", "gloss": zh}],
        examples=[
            {
                "german_text": f"Man muss {lemma} in der Theorieprüfung verstehen.",
                "chinese_text": f"理论考试中需要理解“{zh}”。",
            }
        ],
        tags=[
            {"name": "驾照理论", "tag_type": "交通出行"},
            {"name": CATEGORY_LABELS[category], "tag_type": "交通出行"},
            {"name": part_of_speech, "tag_type": "语言属性"},
        ],
        extra_data={"domains": ["driving_theory", category]},
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
                normalized = normalize_lemma(payload.lemma)
                existing = session.scalars(
                    select(VocabularyEntry).where(VocabularyEntry.normalized_lemma == normalized)
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
    print(f"Inserted {inserted} and enriched {merged} driving theory entries.")


if __name__ == "__main__":
    main()
