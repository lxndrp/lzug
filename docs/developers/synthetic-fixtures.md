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

neu erzeugt. Die Aktualität der erzeugten Adapter wird bei einer Änderung der
Quelle gemeinsam mit den betroffenen Tests geprüft. Browserberichte und
Playwright-Traces werden nicht nach Testdatenmustern ausgewertet.
