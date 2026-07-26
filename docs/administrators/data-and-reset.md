# Daten und Zurücksetzen

Für eine frische lokale Demo-Datenbank starten Sie das Backend mit:

```sh
.venv/bin/python -m backend.app --init --seed --reset
```

`--reset` ersetzt die lokale Datenbank und lädt `db/seed_demo.sql`. Verwenden Sie den Parameter nur, wenn die vorhandenen lokalen Daten ersetzt werden dürfen. Migrationen unter `db/migrations/` werden bei `--init` ausgeführt und in `schema_migration` protokolliert.

Eine produktive Datensicherung oder Wiederherstellung ist nicht Teil des aktuellen Produktumfangs.
