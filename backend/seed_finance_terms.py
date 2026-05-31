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
    ("das Konto", "die Konten", "账户", "banking"),
    ("das Girokonto", "die Girokonten", "活期账户", "banking"),
    ("das Sparkonto", "die Sparkonten", "储蓄账户", "banking"),
    ("die Bank", "die Banken", "银行", "banking"),
    ("die Filiale", "die Filialen", "分行；网点", "banking"),
    ("der Geldautomat", "die Geldautomaten", "自动取款机", "banking"),
    ("die Bankkarte", "die Bankkarten", "银行卡", "banking"),
    ("die Kreditkarte", "die Kreditkarten", "信用卡", "banking"),
    ("die EC-Karte", "die EC-Karten", "借记卡", "banking"),
    ("die IBAN", "die IBANs", "国际银行账号", "banking"),
    ("die BIC", "die BICs", "银行识别码", "banking"),
    ("die TAN", "die TANs", "交易验证码", "banking"),
    ("die PIN", "die PINs", "密码；个人识别码", "banking"),
    ("der Kontostand", "die Kontostände", "账户余额", "banking"),
    ("der Kontoauszug", "die Kontoauszüge", "银行流水；账户对账单", "banking"),
    ("die Gebühr", "die Gebühren", "手续费；费用", "banking"),
    ("die Kontoführungsgebühr", "die Kontoführungsgebühren", "账户管理费", "banking"),
    ("die Überweisung", "die Überweisungen", "转账", "payment"),
    ("der Dauerauftrag", "die Daueraufträge", "定期转账指令", "payment"),
    ("die Lastschrift", "die Lastschriften", "直接扣款", "payment"),
    ("die Zahlung", "die Zahlungen", "支付", "payment"),
    ("die Rechnung", "die Rechnungen", "账单；发票", "payment"),
    ("der Betrag", "die Beträge", "金额", "payment"),
    ("der Empfänger", "die Empfänger", "收款人", "payment"),
    ("der Verwendungszweck", "die Verwendungszwecke", "付款用途；备注", "payment"),
    ("die Mahnung", "die Mahnungen", "催款通知", "payment"),
    ("die Rate", "die Raten", "分期款；还款额", "credit"),
    ("der Kredit", "die Kredite", "贷款；信用", "credit"),
    ("das Darlehen", "die Darlehen", "借款；贷款", "credit"),
    ("die Hypothek", "die Hypotheken", "抵押贷款", "credit"),
    ("der Zinssatz", "die Zinssätze", "利率", "credit"),
    ("der Zins", "die Zinsen", "利息", "credit"),
    ("die Tilgung", "die Tilgungen", "还本；偿还", "credit"),
    ("die Laufzeit", "die Laufzeiten", "期限", "credit"),
    ("die Bonität", "die Bonitäten", "信用资质", "credit"),
    ("die Schufa", "die Schufa-Auskünfte", "德国信用记录机构；信用报告", "credit"),
    ("die Sicherheit", "die Sicherheiten", "抵押物；担保", "credit"),
    ("die Schulden", "die Schulden", "债务", "credit"),
    ("die Aktie", "die Aktien", "股票", "investment"),
    ("der Fonds", "die Fonds", "基金", "investment"),
    ("der ETF", "die ETFs", "交易型开放式指数基金", "investment"),
    ("die Anleihe", "die Anleihen", "债券", "investment"),
    ("das Wertpapier", "die Wertpapiere", "证券", "investment"),
    ("das Depot", "die Depots", "证券账户", "investment"),
    ("die Börse", "die Börsen", "证券交易所；股市", "investment"),
    ("der Kurs", "die Kurse", "价格；行情", "investment"),
    ("die Rendite", "die Renditen", "收益率", "investment"),
    ("das Risiko", "die Risiken", "风险", "investment"),
    ("die Dividende", "die Dividenden", "股息", "investment"),
    ("der Gewinn", "die Gewinne", "利润；收益", "investment"),
    ("der Verlust", "die Verluste", "亏损；损失", "investment"),
    ("das Portfolio", "die Portfolios", "投资组合", "investment"),
    ("die Steuer", "die Steuern", "税", "tax"),
    ("die Einkommensteuer", "die Einkommensteuern", "所得税", "tax"),
    ("die Mehrwertsteuer", "die Mehrwertsteuern", "增值税", "tax"),
    ("die Kapitalertragsteuer", "die Kapitalertragsteuern", "资本利得税", "tax"),
    ("die Steuererklärung", "die Steuererklärungen", "报税申报", "tax"),
    ("der Steuerbescheid", "die Steuerbescheide", "税务通知书", "tax"),
    ("die Abgabe", "die Abgaben", "税费；缴费", "tax"),
    ("die Versicherung", "die Versicherungen", "保险", "insurance"),
    ("die Krankenversicherung", "die Krankenversicherungen", "医疗保险", "insurance"),
    ("die Haftpflichtversicherung", "die Haftpflichtversicherungen", "责任保险", "insurance"),
    ("die Lebensversicherung", "die Lebensversicherungen", "人寿保险", "insurance"),
    ("der Beitrag", "die Beiträge", "保费；缴费", "insurance"),
    ("die Prämie", "die Prämien", "保费；奖金", "insurance"),
    ("der Schaden", "die Schäden", "损失；损害", "insurance"),
    ("die Selbstbeteiligung", "die Selbstbeteiligungen", "自付额；免赔额", "insurance"),
    ("das Einkommen", "die Einkommen", "收入", "income"),
    ("das Gehalt", "die Gehälter", "工资；薪水", "income"),
    ("der Lohn", "die Löhne", "工资", "income"),
    ("die Einnahme", "die Einnahmen", "收入；进项", "income"),
    ("die Ausgabe", "die Ausgaben", "支出", "income"),
    ("das Budget", "die Budgets", "预算", "income"),
    ("die Ersparnis", "die Ersparnisse", "积蓄；节省额", "income"),
    ("das Vermögen", "die Vermögen", "资产；财富", "income"),
    ("die Liquidität", "die Liquiditäten", "流动性", "company"),
    ("der Umsatz", "die Umsätze", "营业额", "company"),
    ("der Gewinn", "die Gewinne", "利润", "company"),
    ("die Bilanz", "die Bilanzen", "资产负债表", "company"),
    ("die Gewinn- und Verlustrechnung", "die Gewinn- und Verlustrechnungen", "损益表", "company"),
    ("der Jahresabschluss", "die Jahresabschlüsse", "年度财报", "company"),
    ("die Forderung", "die Forderungen", "应收款；债权", "company"),
    ("die Verbindlichkeit", "die Verbindlichkeiten", "负债；应付款", "company"),
    ("das Eigenkapital", "die Eigenkapitale", "所有者权益；自有资本", "company"),
    ("die Inflation", "die Inflationen", "通货膨胀", "macro"),
    ("die Deflation", "die Deflationen", "通货紧缩", "macro"),
    ("die Währung", "die Währungen", "货币", "macro"),
    ("der Wechselkurs", "die Wechselkurse", "汇率", "macro"),
    ("die Zentralbank", "die Zentralbanken", "中央银行", "macro"),
    ("der Leitzins", "die Leitzinsen", "基准利率", "macro"),
]


OTHER_WORDS = [
    ("bezahlen", "verb", "支付；付款", "payment"),
    ("überweisen", "verb", "转账", "payment"),
    ("abbuchen", "verb", "扣款", "payment"),
    ("einzahlen", "verb", "存入", "banking"),
    ("abheben", "verb", "取款", "banking"),
    ("sparen", "verb", "储蓄；节省", "income"),
    ("anlegen", "verb", "投资；配置资金", "investment"),
    ("investieren", "verb", "投资", "investment"),
    ("kaufen", "verb", "买入", "investment"),
    ("verkaufen", "verb", "卖出", "investment"),
    ("steigen", "verb", "上涨", "investment"),
    ("fallen", "verb", "下跌", "investment"),
    ("leihen", "verb", "借出；借给", "credit"),
    ("ausleihen", "verb", "借入；借用", "credit"),
    ("zurückzahlen", "verb", "偿还", "credit"),
    ("kündigen", "verb", "终止；取消合同", "insurance"),
    ("versichern", "verb", "投保；保险保障", "insurance"),
    ("versteuern", "verb", "纳税；按税法申报", "tax"),
    ("absetzen", "verb", "税前抵扣", "tax"),
    ("brutto", "adjective", "税前的；总额的", "income"),
    ("netto", "adjective", "税后的；净额的", "income"),
    ("fällig", "adjective", "到期应付的", "payment"),
    ("gebührenfrei", "adjective", "免手续费的", "banking"),
    ("zinsfrei", "adjective", "免息的", "credit"),
    ("riskant", "adjective", "有风险的", "investment"),
    ("sicher", "adjective", "安全的；稳健的", "investment"),
    ("monatlich", "adverb", "每月", "payment"),
    ("jährlich", "adverb", "每年", "tax"),
    ("steuerfrei", "adjective", "免税的", "tax"),
    ("gesetzlich", "adjective", "法定的", "insurance"),
    ("privat", "adjective", "私人的；私营的", "insurance"),
]


CATEGORY_LABELS = {
    "banking": "银行账户",
    "payment": "支付转账",
    "credit": "贷款信用",
    "investment": "投资证券",
    "tax": "税务",
    "insurance": "保险",
    "income": "收入预算",
    "company": "公司财务",
    "macro": "宏观金融",
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
        source_type="finance_seed",
        meanings=[{"language": "zh", "gloss": zh}],
        forms=[{"label": "plural", "value": plural}],
        examples=[
            {
                "german_text": f"{example_head} ist im Finanzalltag wichtig.",
                "chinese_text": f"{zh}在金融场景中很常见。",
            }
        ],
        tags=[
            {"name": "金融场景", "tag_type": "经济金融"},
            {"name": CATEGORY_LABELS[category], "tag_type": "经济金融"},
            {"name": "名词", "tag_type": "语言属性"},
        ],
        extra_data={"domains": ["finance", category]},
    )


def word_entry(lemma: str, part_of_speech: str, zh: str, category: str) -> EntryCreate:
    return EntryCreate(
        lemma=lemma,
        part_of_speech=part_of_speech,
        cefr_level="B1",
        source_type="finance_seed",
        meanings=[{"language": "zh", "gloss": zh}],
        examples=[
            {
                "german_text": f"Man sollte {lemma} im Finanzkontext verstehen.",
                "chinese_text": f"金融语境中需要理解“{zh}”。",
            }
        ],
        tags=[
            {"name": "金融场景", "tag_type": "经济金融"},
            {"name": CATEGORY_LABELS[category], "tag_type": "经济金融"},
            {"name": part_of_speech, "tag_type": "语言属性"},
        ],
        extra_data={"domains": ["finance", category]},
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
    print(f"Inserted {inserted} and enriched {merged} finance entries.")


if __name__ == "__main__":
    main()
