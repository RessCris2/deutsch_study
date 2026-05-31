from __future__ import annotations

from sqlalchemy import select

from backend.app.db import Base, SessionLocal, engine
from backend.app.main import create_search_index, normalize_lemma, sync_entry_search
from backend.app.models import EntryTag, VocabularyEntry


SOURCE_TYPE = "driving_theory_pdf"
SOURCE_REF = "data/驾考理论单词.pdf"


TERMS = """
Abbiegeassistent
Abbiegen
Abblendlicht
ABS
Abschleppen
Abstand
Abstellen
AGR
Airbag
Alkohol
Allee
Alter des Fahrers
Ampel
Andreaskreuz
Anfahren
Anhalteweg
Anhängelast
Anhänger
Anlieger
Antiblockiersystem
Antriebs-Schlupf-Regelung
Anwohner
Anzünden
Aquaplaning
Arbeitsstelle
ASR
Aufbauseminar
Auffahrunfall
Auflaufbremse
Aus- und Einsteigen
Auspuff
Außenspiegel
Aussteigen
Autobahn
Automatik
Bahnübergang
Baustelle
Baustellenfahrzeug
Be- und Entladen
Begleitperson
Begrenzungslicht
Behinderung
Beifahrer
Beladen
Beleuchtung
Bereich
Beschleunigungsstreifen
Betrieb
Blendung
Blinken
Blinker
Bordstein
Bremsbeläge
Bremsen
Bremsflüssigkeit
Bremsleuchte
Bremsprobe
Bremsweg
Brücke
Bundesstraße
Bus
Cannabis
Crystal Meth
Dachgepäck
Dauerlichtzeichen
Dokumente
Dreipunktgurt
Drogen
Drängeln
Dunkelheit
Einbahnstraße
Einfahren
Einmündung
Einordnung
Einspritzanlage
Elektrofahrzeug
Elektroroller
Engstelle
Entladen
Ermüdung
Erste Hilfe
Erste-Hilfe-Station
ESC
Fahrbahn
Fahrbahnrand
Fahrbetrieb
Fahreignungsregister
Fahrrad
Fahrradzone
Fahrstreifen
Fahrzeugschein
Fahrzeugsicherung
Faustformel
Feinstaub-Plakette
Fernlicht
Feuer
Fliehkraft
Fluglärm
Freisprechanlage
Frontairbag
Frontantrieb
Fußgänger
Fußgängerzone
Fußgängerüberweg
Fähre
Führerschein
Gefahrenbremsung
Gefahrenlehre
Gefahrguttransport
Gefahrstelle
Gefahrzeichen
Gefälle
Gegenverkehr
Gehweg
Gepäck
Geradeausfahren
Geschwindigkeit
Glätte
Grundstücksausfahrt
Grünpfeilschild
Haftpflichtversicherung
Halten
Haltestelle
Haltestellenschild
Halteverbot
Haltverbot
Handbremshebel
Hauptuntersuchung
Helm
Helmvisier
Hindernis
Hinterradantrieb
Hupe
Hupen
Jugendliche
Katalysator
Kennzeichen
Kick down
Kinder
Kindersitz
Kleidung
Kleintransporter
Kolonne
Kontrolle
Kopfsteinpflaster
Kopfstütze
Kugelkupplung
Ladung
Landstraße
Langsamfahrer
Linksabbiegen
Lärmbelästigung
Mitfahrer
Mittellinie
Mobiltelefon
Mofa
Motor
Motorrad
Musik
Mähdrescher
Müdigkeit
Navigationssystem
Nebel
Nebelscheinwerfer
Nebelschlussleuchte
Notrad
Notruf
Notrufsäule
Nässe
Ortschaft
Ortschaft, geschlossene
Panne
Parken
Parkscheibe
Parkschein
Parkuhr
Probezeit
Profiltiefe
Radfahrer
Rauschmittel
Regen
Reh
Reifen
Reifendruck
Reißverschluss
Reitweg
Rettungswagen
Richtgeschwindigkeit
Richtzeichen
Rollsplitt
Rollstuhl
Rückhalteeinrichtung
Rücksichtnahme
Rückspiegel
Rückwärtsfahren
Sackgasse
Schadstoffausstoß
Schaltgetriebe
Scheibenwaschanlage
Schieben
Schlagloch
Schleudergefahr
Schlusslicht
Schnee
Schneefall
Schneekette
Schulbus
Schule
Schutzkleidung
Schutzstreifen
Schwerbehinderte
Sehbehinderung
Seitenstreifen
Seitenwind
Sicherheitsabstand
Sicherheitsgurt
Sicht
Sichtverhältnisse
Sonnenbrille
Sonntagsfahrverbot
Sorgfaltspflichten
Soziusbetrieb
Spurhalte-Assistent
Spurverhalten
Spurwechsel-Assistent
Standlicht
Stau
Steine
Stoppschild
Straßenbahn
Straßenbeleuchtung
Straßenbenutzung
Störung
Störungen
Stützlast
Tankstelle
Technik
Telefonieren
Tempomat
Tieferlegung
Tiefgarage
Trommelbremse
Tunnel
Ufer
Umbauten
Umleitung
Umweltbelastung
Umweltschutz
Umweltzone
Unfall
Unterführung
Unterschreitung
Verbotsschild
Vergaser
Verhalten
Verhalten im Straßenverkehr
Verkehrseinrichtungen
Verkehrshelfer
Verkehrshindernis
Verkehrsinsel
Verkehrssituationen
Verkehrsunfall
Verkehrszeichen
Versicherungskennzeichen
Vorbeifahren
Vorderradbremse
Vorfahrt
Vorfahrtstraße
Vorrang
Vorschriftzeichen
Warnblinklicht
Warnzeichen
Wartung
Wechsellichtzeichen
Weidetier
Wenden
Wild
Winterreifen
Wintersport
Witterungsverhältnisse
Zollstelle
Zone
Zulassung
Zurrgurt
Zusatzzeichen
ältere Menschen
Ölverlust
Überfahren
Überholen
Übermüdung
""".strip().splitlines()

SMALL_TERMS = """
mehrspuriges
auf der Landstraße
bei Tage
Tunnel
unbeleuchtete Straße
bei Anhänger
Kontrollleuchte
Abbau
Fahrtüchtigkeit
mit schmaler Fahrbahn
stockender Verkehr
zulässiger
Faustformel
Parkausweis
Anfang
Ausfahrt
Ausfahrtnummer
Fahrstreifenbenutzung
Nummer
Reifenpanne
Rettungsfahrzeug
Steigung
Kick down
Losfahren
Motor abstellen
besondere Vorsicht
defekte
Kreisverkehr
Überholvorgang
Vorfahrtstraße folgen
abgesenkter
Kurve
Berechnung
bewegliche
Vereisung
Sonderfahrstreifen
Fahrverhalten
Fahrtauglichkeit
auf Kraftfahrstraßen
Verbotsschild
Vorfahrtsschild
irrtümliche
Markierung
Beförderung
Berechnung Anhalteweg
Abblenden
blaue Kontrollleuchte
Gefahren
im Tunnel
fehlende
im Zusammenhang mit
Anhänger außerhalb der Begrenzung
Einschätzung
Ende der Beschränkung
Ende der Zone
geschlossene Ortschaft
Linkskurve
Lkw
bei Schneeketten
bei Wasserlache
vor Zeichen
zweite Reihe
Halten und Parken
Feuerwehrzufahrt
nächtliche Freizeitfahrt
quengelnde Kinder
Sitzerhöhung
Vorsicht
Erleichterungen
Schleudern
auf dem Dach
herabfallende Ladung
Höhe
Pedelecs
schlechte Sicht
Anbaugerät
Personenbeförderung
Radwegnutzung
Schutzhelm
Luftfilter
Beiwagen
Beladung
Mittelständer
Pendelbewegung
Rucksack
sonstige Pflichten
Bremswirkung
Laub
auf der Autobahn
Höchstgeschwindigkeit
Ausparken
rechter Fahrstreifen
nicht laufende
Haltegebot
Wasserstofftankstelle
Erdgastankstelle
Autogastankstelle
Parkverbot
Fahrstreifenbegrenzung
Beenden
eines Busses
Einscheren
eines Elektrorollers
Lichthupe
Lkw mit Anhänger
mehrerer Lkw
eines Radfahrers
rechts
Verbotsende
Verbotsstrecke
Beteiligung
Disco-Unfall
Hilfeleistung
auf der Landstraße
Pflichten als Beteiligter
Wildunfall
schlecht beleuchtete
affektiv-emotionales
Beseitigung
ungültiges
Linienbus
Kreuzung oder Einmündung
überqueren
liegen gebliebenes Fahrzeug
im Fernlicht
""".strip().splitlines()


def unique_items() -> list[tuple[str, bool]]:
    seen: set[str] = set()
    terms: list[tuple[str, bool]] = []
    for raw_term in TERMS:
        term = " ".join(raw_term.strip().split())
        key = normalize_lemma(term)
        if term and key not in seen:
            terms.append((term, False))
            seen.add(key)
    for raw_term in SMALL_TERMS:
        term = " ".join(raw_term.strip().split())
        key = normalize_lemma(term)
        if term and key not in seen:
            terms.append((term, True))
            seen.add(key)
    return terms


def add_tag(entry: VocabularyEntry, name: str, tag_type: str) -> bool:
    if any(tag.name == name for tag in entry.tags):
        return False
    entry.tags.append(EntryTag(name=name, tag_type=tag_type))
    return True


def merge_source(entry: VocabularyEntry, *, is_small_term: bool = False) -> bool:
    changed = False
    extra_data = dict(entry.extra_data or {})
    domains = set(extra_data.get("domains") or [])
    if "driving_theory" not in domains or "driving_theory_pdf" not in domains:
        domains.update({"driving_theory", "driving_theory_pdf"})
        extra_data["domains"] = sorted(domains)
        entry.extra_data = extra_data
        changed = True
    raw_payload = dict(entry.raw_payload or {})
    sources = list(raw_payload.get("source_refs") or [])
    if SOURCE_REF not in sources:
        raw_payload["source_refs"] = [*sources, SOURCE_REF]
        entry.raw_payload = raw_payload
        changed = True
    changed |= add_tag(entry, "驾照理论", "交通出行")
    changed |= add_tag(entry, "驾考理论单词PDF", "来源")
    if is_small_term:
        changed |= add_tag(entry, "驾考理论小条目", "来源")
    return changed


def import_terms() -> tuple[int, int]:
    create_search_index()
    inserted = 0
    enriched = 0
    with SessionLocal() as session:
        changed_entries: list[VocabularyEntry] = []
        for term, is_small_term in unique_items():
            normalized = normalize_lemma(term)
            entry = session.scalars(
                select(VocabularyEntry).where(VocabularyEntry.normalized_lemma == normalized)
            ).first()
            if entry:
                if merge_source(entry, is_small_term=is_small_term):
                    enriched += 1
                    changed_entries.append(entry)
                continue

            entry = VocabularyEntry(
                lemma=term,
                normalized_lemma=normalized,
                language="de",
                cefr_level="B1",
                source_type=SOURCE_TYPE,
                source_ref=SOURCE_REF,
                notes=(
                    "从驾考理论单词 PDF 索引小条目导入，待补充释义。"
                    if is_small_term
                    else "从驾考理论单词 PDF 索引导入的主词条，待补充释义。"
                ),
                extra_data={"domains": ["driving_theory", "driving_theory_pdf"]},
                raw_payload={"source_refs": [SOURCE_REF]},
            )
            entry.tags.append(EntryTag(name="驾照理论", tag_type="交通出行"))
            entry.tags.append(EntryTag(name="驾考理论单词PDF", tag_type="来源"))
            if is_small_term:
                entry.tags.append(EntryTag(name="驾考理论小条目", tag_type="来源"))
            session.add(entry)
            changed_entries.append(entry)
            inserted += 1

        session.flush()
        for entry in changed_entries:
            sync_entry_search(session, entry)
        session.commit()
    return inserted, enriched


def main() -> None:
    Base.metadata.create_all(bind=engine)
    inserted, enriched = import_terms()
    print(f"Inserted {inserted} and enriched {enriched} driving theory PDF entries.")


if __name__ == "__main__":
    main()
