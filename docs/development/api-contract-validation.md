# OpenAPI- und API-Vertragsvalidierung

Die OpenAPI-Spezifikation in `backend/openapi.py` ist der verbindliche
HTTP-Vertrag. Der Test `backend/tests/test_openapi_contract.py` ruft die echte
HTTP-Handler-Schicht mit einer isolierten SQLite-Datenbank auf und validiert
jede geprüfte JSON-Antwort gegen die jeweils ausgelieferte Spezifikation.

Die Validierung prüft für dokumentierte Pfade, HTTP-Methoden und Statuscodes:

- dass die Operation und der tatsächliche Status in OpenAPI dokumentiert sind;
- Pflichtfelder, Grundtypen, Enum-Werte, Arrays, Objekte und lokale
  Schema-Referenzen der JSON-Response;
- alle lesbaren REST-Sammlungen und ihre Einzelressourcen aus den Seed-Daten;
- die im Angular-`PlanningApiService` verwendeten Lese- und Schreibpfade;
- die produktiven Schreibabläufe für Ausschüsse, Mitgliedschaften, Prüflinge,
  Orte, Planungsparameter, mögliche Prüfungstage, Verfügbarkeiten,
  Vorschlagsgenerierung und Planbestätigung;
- mindestens einen dokumentierten Fehlerfall (`400` für eine ungültige
  Vorschlagsanfrage).

Die Testklasse enthält außerdem einen Negativnachweis: Wird aus einer echten
Health-Response das erforderliche Feld `status` entfernt, löst der Validator
einen `ContractValidationError` aus. Ein vergleichbarer Vertragsbruch lässt
damit sowohl den lokalen Testlauf als auch den Backend-Job der CI fehlschlagen.

## Änderungen an Backend und Frontend

Bei einer neuen oder geänderten API-Operation sind in derselben Änderung
anzupassen:

1. Handler und fachliche Implementierung im Backend.
2. Pfad, Statuscodes sowie Response- und Request-Schemas in
   `backend/openapi.py`.
3. Ein echter Response-Fall in `test_openapi_contract.py`, einschließlich
   eines Fehlerfalls, wenn die Operation einen dokumentierten Fehlerstatus hat.
4. Der Angular-`PlanningApiService` und seine Typen. Der Vertragstest liest
   dessen Pfade und prüft, dass jede verwendete Operation in OpenAPI existiert.

Die vollständige Prüfung läuft mit `task quality`; der Backend-Abschnitt führt
den Vertragstest über `python -m unittest` aus. Der GitHub-Actions-Backend-Job
verwendet denselben Testbefehl, daher sind Vertragsbrüche lokal und in CI
blockierend.
