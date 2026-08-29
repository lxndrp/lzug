# Synthetische Testdaten

Demo- und Testidentitäten sind ausdrücklich fiktiv, kollisionsfrei und technisch nicht zustellbar.
Die kanonische Quelle ist `fixtures/synthetic-fixtures.json`.
Sie verwendet ausschließlich `example.invalid`, ungültige Testtelefonnummern, den fiktiven Ort Teststadt, die Postleitzahl `00000` sowie klar benannte Testpersonen, Prüflinge, Prüfungsorte und Ausbildungsbetriebe.

`scripts/generate_synthetic_fixtures.py` erzeugt daraus die Adapter für das
SQL-Demo-Seed, die zentralen Angular-Fixtures und den historischen statischen
Prototyp. Generierte Dateien tragen einen entsprechenden Kopf und werden nicht
direkt bearbeitet. Verhaltensspezifische Tests dürfen zusätzliche Werte
verwenden, wenn sie derselben erkennbar synthetischen Konvention folgen.
Der Demo-Artefaktbau ergänzt anschließend genau einen separaten, bestätigten und gestarteten synthetischen Slot mit offenem Protokoll sowie gebundenem, synthetischem Bewertungsmodell.
Damit bleiben die allgemeinen Planungsfixtures unverändert wiederverwendbar, während Vorsitz, prüfendes Mitglied und Stellvertretung als tatsächliche Beteiligte den Protokoll- und Ergebnisworkflow einschließlich Offenlegung und Vier-Augen-Bestätigung bis zum nächsten Reset ausführen können.

Nach einer Änderung an der kanonischen Quelle werden die Adapter mit

```sh
python3 scripts/generate_synthetic_fixtures.py
```

neu erzeugt.
Die Aktualität der erzeugten Adapter wird bei einer Änderung der Quelle oder eines Adapters mit dem folgenden Befehl geprüft:

```sh
task fixtures:check
```

Schlägt die Prüfung fehl, ist mindestens einer der drei Adapter veraltet oder fehlt.
Dann den Regenerierungsbefehl ausführen, ausschließlich dessen erwartete Änderungen prüfen und anschließend den Check erneut ausführen.
Der Check ist Teil von `task quality` und wird im Pull-Request- sowie im vollständigen Qualitätspfad für Änderungen an Quelle, Generator und jedem Adapter ausgeführt.
Browserberichte und Playwright-Traces werden nicht nach Testdatenmustern ausgewertet.
