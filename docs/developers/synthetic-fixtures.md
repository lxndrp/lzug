# Synthetische Testdaten

Demo- und Testidentitäten sind ausdrücklich fiktiv, kollisionsfrei und
technisch nicht zustellbar. Die kanonische Quelle ist
`fixtures/synthetic-fixtures.json`. Sie verwendet ausschließlich
`example.invalid`, ungültige Testtelefonnummern, den fiktiven Ort Teststadt,
die Postleitzahl `00000` sowie klar benannte Testpersonen, Prüflinge,
Prüfungsorte und Ausbildungsbetriebe.

`scripts/generate_synthetic_fixtures.py` erzeugt daraus die Adapter für das
SQL-Demo-Seed, die zentralen Angular-Fixtures und den historischen statischen
Prototyp. Generierte Dateien tragen einen entsprechenden Kopf und werden nicht
direkt bearbeitet. Verhaltensspezifische Tests dürfen zusätzliche Werte
verwenden, wenn sie derselben erkennbar synthetischen Konvention folgen.

Nach einer Änderung an der kanonischen Quelle werden die Adapter mit

```sh
python3 scripts/generate_synthetic_fixtures.py
```

neu erzeugt. `task quality:fixtures` prüft ihre Aktualität, reservierte
Demo-Domains, die Eindeutigkeit der kanonischen Identitäten und Fingerabdrücke
sanitisierter Altwertkategorien. Die Fingerabdrücke enthalten keine lesbaren
Altwerte. Der Guard läuft außerdem in den Backend-Tests und in der CI.

Generierte Dokumentation und Browserberichte sind nicht versioniert. Vor der
Veröffentlichung werden sie neu erzeugt und stichprobenartig auf dieselben
Konventionen geprüft; fehlgeschlagene Playwright-Läufe dürfen keine älteren
lokalen Traces oder Screenshots weiterverwenden. Nach diesen Erzeugungsläufen
prüft

```sh
python3 scripts/check_synthetic_fixtures.py --include-generated-artifacts
```

zusätzlich lokale Dokumentation, Playwright-Berichte und lesbare Trace-Inhalte.
Vorhandene Screenshots in den Testergebnissen erzwingen eine ausdrückliche
visuelle Prüfung.
