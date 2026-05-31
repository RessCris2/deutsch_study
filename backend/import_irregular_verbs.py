from __future__ import annotations

from sqlalchemy import select

from backend.app.db import Base, SessionLocal, engine
from backend.app.main import create_search_index, normalize_lemma, sync_entry_search
from backend.app.models import EntryForm, EntryTag, IrregularVerb, Meaning, VocabularyEntry


ROWS = [
    ("befehlen", "befiehlst, befiehlt", "befahl", "befohlen", "befiehl", "beföhle / befähle", None, "命令"),
    ("beginnen", "beginnst, beginnt", "begann", "begonnen", "beginn(e)", "begänne / begönne", None, "开始"),
    ("beweisen", "beweist, beweist", "bewies", "bewiesen", "beweis(e)", "bewiese", None, "证明"),
    ("biegen", "biegst, biegt", "bog", "gebogen", "bieg(e)", "böge", "haben/sein", "弯曲；转弯"),
    ("bieten", "bietest, bietet", "bot", "geboten", "biet(e)", "böte", None, "提供"),
    ("bitten", "bittest, bittet", "bat", "gebeten", "bitt(e)", "bäte", None, "请求"),
    ("bleiben", "bleibst, bleibt", "blieb", "geblieben", "bleib(e)", "bliebe", "sein", "停留"),
    ("brechen", "brichst, bricht", "brach", "gebrochen", "brich", "bräche", "haben/sein", "打破；折断"),
    ("brennen", "brennst, brennt", "brannte", "gebrannt", "brenn(e)", "brennte", None, "燃烧"),
    ("bringen", "bringst, bringt", "brachte", "gebracht", "bring(e)", "brächte", None, "带来"),
    ("denken", "denkst, denkt", "dachte", "gedacht", "denk(e)", "dächte", None, "想；认为"),
    ("dürfen", "darfst, darf", "durfte", "gedurft", None, "dürfte", None, "允许"),
    ("empfehlen", "empfiehlst, empfiehlt", "empfahl", "empfohlen", "empfiehl", "empföhle / empfähle", None, "推荐"),
    ("entscheiden", "entscheidest, entscheidet", "entschied", "entschieden", "entscheid(e)", "entschiede", None, "决定"),
    ("erwerben", "erwirbst, erwirbt", "erwarb", "erworben", "erwirb", "erwürbe", None, "获得"),
    ("essen", "isst, isst", "aß", "gegessen", "iss", "äße", None, "吃"),
    ("fahren", "fährst, fährt", "fuhr", "gefahren", "fahr(e)", "führe", "sein", "行驶；乘车"),
    ("fallen", "fällst, fällt", "fiel", "gefallen", "fall(e)", "fiele", "sein", "掉落"),
    ("fangen", "fängst, fängt", "fing", "gefangen", "fang(e)", "finge", None, "抓住"),
    ("finden", "findest, findet", "fand", "gefunden", "find(e)", "fände", None, "找到"),
    ("fliegen", "fliegst, fliegt", "flog", "geflogen", "flieg(e)", "flöge", "sein", "飞"),
    ("fließen", "fließt, fließt", "floss", "geflossen", "fließ(e)", "flösse", "sein", "流动"),
    ("fressen", "frisst, frisst", "fraß", "gefressen", "friss", "fräße", None, "吃（动物）"),
    ("geben", "gibst, gibt", "gab", "gegeben", "gib", "gäbe", None, "给"),
    ("gehen", "gehst, geht", "ging", "gegangen", "geh(e)", "ginge", "sein", "走"),
    ("gelten", "giltst, gilt", "galt", "gegolten", "gilt", "gölte / gälte", None, "适用；有效"),
    ("genießen", "genießt, genießt", "genoss", "genossen", "genieß(e)", "genösse", None, "享受"),
    ("geschehen", "es geschieht", "geschah", "geschehen", None, "geschähe", "sein", "发生"),
    ("gewinnen", "gewinnst, gewinnt", "gewann", "gewonnen", "gewinn(e)", "gewönne / gewänne", None, "赢得"),
    ("gleichen", "gleichst, gleicht", "glich", "geglichen", "gleich(e)", "gliche", None, "相似"),
    ("haben", "hast, hat", "hatte", "gehabt", "hab(e)", "hätte", None, "有"),
    ("halten", "hältst, hält", "hielt", "gehalten", "halt(e)", "hielte", None, "保持；停"),
    ("hängen", "hängst, hängt", "hing", "gehangen", "häng(e)", "hinge", None, "悬挂"),
    ("hauen", "haust, haut", "hieb / haute", "gehauen", "hau(e)", "hiebe", None, "打；砍"),
    ("heben", "hebst, hebt", "hob", "gehoben", "heb(e)", "höbe / hübe", None, "举起"),
    ("heißen", "heißt, heißt", "hieß", "geheißen", "heiß(e)", "hieße", None, "叫做"),
    ("helfen", "hilfst, hilft", "half", "geholfen", "hilf", "hülfe / hälfe", None, "帮助"),
    ("kennen", "kennst, kennt", "kannte", "gekannt", "kenn(e)", "kennte", None, "认识"),
    ("klingen", "klingst, klingt", "klang", "geklungen", "kling(e)", "klänge", None, "听起来"),
    ("kommen", "kommst, kommt", "kam", "gekommen", "komm(e)", "käme", "sein", "来"),
    ("können", "kannst, kann", "konnte", "gekonnt", None, "könnte", None, "能够"),
    ("laden", "lädst, lädt", "lud", "geladen", "lad(e)", "lüde", None, "装载；邀请"),
    ("lassen", "lässt, lässt", "ließ", "gelassen", "lass(e)", "ließe", None, "让；留下"),
    ("laufen", "läufst, läuft", "lief", "gelaufen", "lauf(e)", "liefe", "sein", "跑；行走"),
    ("leiden", "leidest, leidet", "litt", "gelitten", "leid(e)", "litte", None, "忍受；患病"),
    ("leihen", "leihst, leiht", "lieh", "geliehen", "leih(e)", "liehe", None, "借"),
    ("lesen", "liest, liest", "las", "gelesen", "lies", "läse", None, "阅读"),
    ("liegen", "liegst, liegt", "lag", "gelegen", "lieg(e)", "läge", None, "躺；位于"),
    ("müssen", "musst, muss", "musste", "gemusst", None, "müsste", None, "必须"),
    ("nehmen", "nimmst, nimmt", "nahm", "genommen", "nimm", "nähme", None, "拿"),
    ("riechen", "riechst, riecht", "roch", "gerochen", "riech(e)", "röche", None, "闻"),
    ("rufen", "rufst, ruft", "rief", "gerufen", "ruf(e)", "riefe", None, "叫喊"),
    ("schaffen", "schaffst, schafft", "schuf", "geschaffen", "schaff(e)", "schüfe", None, "创造"),
    ("scheinen", "scheinst, scheint", "schien", "geschienen", "schein(e)", "schiene", None, "照耀；似乎"),
    ("schlafen", "schläfst, schläft", "schlief", "geschlafen", "schlaf(e)", "schliefe", None, "睡觉"),
    ("schließen", "schließt, schließt", "schloss", "geschlossen", "schließ(e)", "schlösse", None, "关闭"),
    ("schneiden", "schneidest, schneidet", "schnitt", "geschnitten", "schneid(e)", "schnitte", None, "切"),
    ("schreiben", "schreibst, schreibt", "schrieb", "geschrieben", "schreib(e)", "schriebe", None, "写"),
    ("schreien", "schreist, schreit", "schrie", "geschrien", "schrei(e)", "schriee", None, "喊叫"),
    ("schweigen", "schweigst, schweigt", "schwieg", "geschwiegen", "schweig(e)", "schwiege", None, "沉默"),
    ("sehen", "siehst, sieht", "sah", "gesehen", "sieh(e)", "sähe", None, "看见"),
    ("sein", "bist, ist", "war", "gewesen", "sei; seid", "wäre", "sein", "是"),
    ("singen", "singst, singt", "sang", "gesungen", "sing(e)", "sänge", None, "唱"),
    ("sinken", "sinkst, sinkt", "sank", "gesunken", "sink(e)", "sänke", "sein", "下沉"),
    ("sitzen", "sitzt, sitzt", "saß", "gesessen", "sitz(e)", "säße", None, "坐"),
    ("sollen", "sollst, soll", "sollte", "gesollt", None, "sollte", None, "应该"),
    ("sprechen", "sprichst, spricht", "sprach", "gesprochen", "sprich", "spräche", None, "说"),
    ("stehen", "stehst, steht", "stand", "gestanden", "steh(e)", "stünde / stände", None, "站；位于"),
    ("steigen", "steigst, steigt", "stieg", "gestiegen", "steig(e)", "stiege", "sein", "上升"),
    ("sterben", "stirbst, stirbt", "starb", "gestorben", "stirb", "stürbe", "sein", "死亡"),
    ("streiten", "streitest, streitet", "stritt", "gestritten", "streit(e)", "stritte", None, "争吵"),
    ("tragen", "trägst, trägt", "trug", "getragen", "trag(e)", "trüge", None, "携带；穿"),
    ("treffen", "triffst, trifft", "traf", "getroffen", "triff", "träfe", None, "遇见；击中"),
    ("treiben", "treibst, treibt", "trieb", "getrieben", "treib(e)", "triebe", None, "驱动；从事"),
    ("treten", "trittst, tritt", "trat", "getreten", "tritt", "träte", "haben/sein", "踏；踢"),
    ("trinken", "trinkst, trinkt", "trank", "getrunken", "trink(e)", "tränke", None, "喝"),
    ("tun", "tust, tut", "tat", "getan", "tu(e)", "täte", None, "做"),
    ("unterbrechen", "unterbrichst, unterbricht", "unterbrach", "unterbrochen", "unterbrich", "unterbräche", None, "打断"),
    ("verbinden", "verbindest, verbindet", "verband", "verbunden", "verbind(e)", "verbände", None, "连接"),
    ("vergessen", "vergisst, vergisst", "vergaß", "vergessen", "vergiss", "vergäße", None, "忘记"),
    ("vergießen", "vergießt, vergießt", "vergoss", "vergossen", "vergieß(e)", "vergösse", None, "洒出"),
    ("verlieren", "verlierst, verliert", "verlor", "verloren", "verlier(e)", "verlöre", None, "失去"),
    ("vermeiden", "vermeidest, vermeidet", "vermied", "vermieden", "vermeid(e)", "vermiede", None, "避免"),
    ("verschwinden", "verschwindest, verschwindet", "verschwand", "verschwunden", "verschwind(e)", "verschwände", "sein", "消失"),
    ("waschen", "wäschst, wäscht", "wusch", "gewaschen", "wasch(e)", "wüsche", None, "洗"),
    ("werden", "wirst, wird", "wurde", "geworden", "werd(e)", "würde", "sein", "成为"),
    ("werfen", "wirfst, wirft", "warf", "geworfen", "wirf", "würfe", None, "扔"),
    ("wiegen", "wiegst, wiegt", "wog", "gewogen", "wieg(e)", "wöge", None, "称重"),
    ("wissen", "weißt, weiß", "wusste", "gewusst", "wisse", "wüsste", None, "知道"),
    ("wollen", "willst, will", "wollte", "gewollt", "wolle", "wollte", None, "想要"),
    ("ziehen", "ziehst, zieht", "zog", "gezogen", "zieh(e)", "zöge", "haben/sein", "拉；搬迁"),
    ("abschneiden", None, "schnitt ab", "abgeschnitten", None, None, None, "剪下"),
    ("abwenden", None, "wendete/wandte ab", "abgewendet/abgewandt", None, None, None, "转开；避免"),
    ("angeben", None, "gab an", "angegeben", None, None, None, "说明；吹嘘"),
    ("angreifen", None, "griff an", "angegriffen", None, None, None, "攻击"),
    ("ankommen", None, "kam an", "angekommen", None, None, "sein", "到达"),
    ("anschließen", None, "schloss an", "angeschlossen", None, None, None, "连接"),
    ("ansteigen", None, "stieg an", "angestiegen", None, None, None, "上升"),
    ("anschwellen", None, "schwoll an", "angeschwollen", None, None, "sein", "肿胀；上涨"),
    ("ansprechen", None, "sprach an", "angesprochen", None, None, None, "搭话；提及"),
    ("anwenden", None, "wendete/wandte an", "angewendet/angewandt", None, None, None, "应用"),
    ("aufladen", None, "lud auf", "aufgeladen", None, None, None, "充电；装载"),
    ("aufblasen", None, "blies auf", "aufgeblasen", None, None, None, "吹起；充气"),
    ("auskennen", None, "kannte aus", "ausgekannt", None, None, None, "熟悉"),
    ("aussprechen", None, "sprach aus", "ausgesprochen", None, None, None, "发音；说出"),
    ("ausschneiden", None, "schnitt aus", "ausgeschnitten", None, None, None, "剪出"),
    ("ausschließen", None, "schloss aus", "ausgeschlossen", None, None, None, "排除"),
    ("bestehen", None, "bestand", "bestanden", None, None, None, "存在；通过"),
    ("bewegen", None, "bewog/bewegte", "bewogen/bewegt", None, None, None, "促使；移动"),
    ("einlassen", None, "ließ ein", "eingelassen", None, None, None, "让进入；参与"),
    ("einschließen", None, "schloss ein", "eingeschlossen", None, None, None, "包含；锁入"),
    ("entwerfen", None, "entwarf", "entworfen", None, None, None, "设计；起草"),
    ("erbringen", None, "erbrachte", "erbracht", None, None, None, "提供；完成"),
    ("ergeben", None, "ergab", "ergeben", None, None, None, "产生；得出"),
    ("erschrecken", None, "erschrak/erschreckte", "erschrocken/erschreckt", None, None, "haben/sein", "受惊；吓到"),
    ("nachlassen", None, "ließ nach", "nachgelassen", None, None, None, "减弱"),
    ("stechen", None, "stach", "gestochen", None, None, None, "刺"),
    ("streichen", None, "strich", "gestrichen", None, None, None, "涂；删除"),
    ("überfliegen", None, "überflog", "überflogen", None, None, None, "飞越；浏览"),
    ("übernehmen", None, "übernahm", "übernommen", None, None, None, "接管；承担"),
    ("unterhalten", None, "unterhielt", "unterhalten", None, None, None, "交谈；娱乐"),
    ("versenden", None, "versandte/versendete", "versandt/versendet", None, None, None, "寄送"),
    ("versinken", None, "versank", "versunken", None, None, "sein", "沉没"),
    ("vorkommen", None, "kam vor", "vorgekommen", None, None, "sein", "出现"),
    ("wahrnehmen", None, "nahm wahr", "wahrgenommen", None, None, None, "察觉；履行"),
    ("werben", None, "warb", "geworben", None, None, None, "宣传；招揽"),
    ("zugeben", None, "gab zu", "zugegeben", None, None, None, "承认"),
    ("zuschreien", None, "schrie zu", "zugeschrien", None, None, None, "朝某人喊"),
    ("zuweisen", None, "wies zu", "zugewiesen", None, None, None, "分配"),
    ("zwingen", None, "zwang", "gezwungen", None, None, None, "强迫"),
]


SOURCE_REF = "data/irregular/3.pdf; data/irregular/4.pdf"


def add_tag(entry: VocabularyEntry, name: str, tag_type: str) -> bool:
    if any(tag.name == name for tag in entry.tags):
        return False
    entry.tags.append(EntryTag(name=name, tag_type=tag_type))
    return True


def add_form(entry: VocabularyEntry, label: str, value: str | None, note: str | None = None) -> bool:
    if not value:
        return False
    if any(form.label == label and form.value == value for form in entry.forms):
        return False
    entry.forms.append(EntryForm(label=label, value=value, note=note))
    return True


def add_meaning(entry: VocabularyEntry, meaning: str | None) -> bool:
    if not meaning:
        return False
    if any(item.language == "zh" and item.gloss == meaning for item in entry.meanings):
        return False
    entry.meanings.append(Meaning(sort_order=len(entry.meanings), language="zh", gloss=meaning))
    return True


def irregular_note(
    infinitive: str,
    present: str | None,
    preterite: str,
    participle: str,
    imperative: str | None,
    subjunctive: str | None,
    auxiliary: str | None,
) -> str:
    parts = [
        f"不规则动词：{infinitive}",
        f"过去式：{preterite}",
        f"第二分词：{participle}",
    ]
    if present:
        parts.append(f"现在时变位：{present}")
    if auxiliary:
        parts.append(f"助动词：{auxiliary}")
    if imperative:
        parts.append(f"命令式：{imperative}")
    if subjunctive:
        parts.append(f"第二虚拟式：{subjunctive}")
    return "；".join(parts) + "。"


def sync_vocabulary_entry(row: tuple[str, ...], session) -> VocabularyEntry:
    infinitive, present, preterite, participle, imperative, subjunctive, auxiliary, meaning = row
    normalized = normalize_lemma(infinitive)
    entry = session.scalars(
        select(VocabularyEntry).where(VocabularyEntry.normalized_lemma == normalized)
    ).first()
    if entry is None:
        entry = VocabularyEntry(
            lemma=infinitive,
            normalized_lemma=normalized,
            language="de",
            part_of_speech="verb",
            cefr_level="B1",
            source_type="irregular_verbs",
            source_ref=SOURCE_REF,
            extra_data={},
            raw_payload={},
        )
        session.add(entry)
    elif not entry.part_of_speech:
        entry.part_of_speech = "verb"

    add_meaning(entry, meaning)
    add_form(entry, "present", present, "不规则动词现在时变位")
    add_form(entry, "preterite", preterite, "不规则动词过去式")
    add_form(entry, "participle_ii", participle, "不规则动词第二分词")
    add_form(entry, "imperative", imperative, "不规则动词命令式")
    add_form(entry, "subjunctive_ii", subjunctive, "不规则动词第二虚拟式")
    add_form(entry, "auxiliary", auxiliary, "完成时助动词")
    add_tag(entry, "不规则动词", "语法")
    add_tag(entry, "动词", "语言属性")

    note = irregular_note(infinitive, present, preterite, participle, imperative, subjunctive, auxiliary)
    if entry.notes:
        if "不规则动词：" not in entry.notes:
            entry.notes = f"{entry.notes.rstrip()}\n{note}"
    else:
        entry.notes = note

    extra_data = dict(entry.extra_data or {})
    extra_data["irregular_verb"] = {
        "present": present,
        "preterite": preterite,
        "participle_ii": participle,
        "imperative": imperative,
        "subjunctive_ii": subjunctive,
        "auxiliary": auxiliary,
        "meaning_zh": meaning,
        "source_ref": SOURCE_REF,
    }
    domains = set(extra_data.get("domains") or [])
    domains.add("irregular_verbs")
    extra_data["domains"] = sorted(domains)
    entry.extra_data = extra_data

    raw_payload = dict(entry.raw_payload or {})
    source_refs = list(raw_payload.get("source_refs") or [])
    if SOURCE_REF not in source_refs:
        raw_payload["source_refs"] = [*source_refs, SOURCE_REF]
    entry.raw_payload = raw_payload

    if not entry.source_ref:
        entry.source_ref = SOURCE_REF

    return entry


def main() -> None:
    Base.metadata.create_all(bind=engine)
    create_search_index()
    imported = 0
    changed_entries: list[VocabularyEntry] = []
    with SessionLocal() as session:
        for row in ROWS:
            infinitive, present, preterite, participle, imperative, subjunctive, auxiliary, meaning = row
            existing = session.scalars(
                session.query(IrregularVerb).filter(IrregularVerb.infinitive == infinitive).statement
            ).first()
            verb = existing or IrregularVerb(infinitive=infinitive, preterite=preterite, participle_ii=participle)
            verb.present = present
            verb.preterite = preterite
            verb.participle_ii = participle
            verb.imperative = imperative
            verb.subjunctive_ii = subjunctive
            verb.auxiliary = auxiliary
            verb.meaning_zh = meaning
            verb.source_ref = SOURCE_REF
            session.add(verb)
            changed_entries.append(sync_vocabulary_entry(row, session))
            imported += 1
        session.flush()
        for entry in changed_entries:
            sync_entry_search(session, entry)
        session.commit()
    print(f"Imported or updated {imported} irregular verbs and synced them to vocabulary.")


if __name__ == "__main__":
    main()
