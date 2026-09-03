# ADR-0010: Vitest statt Karma und Jasmine für Frontend-Unit-Tests

## Datum

2026-07-27.

## Status

Akzeptiert.

## Kontext

Die Angular-Unit-Tests liefen bisher über Karma und Jasmine.
Deren Abhängigkeitskette zog die abgekündigten Pakete `inflight`, `glob@7` und `rimraf` nach sich.
Angular verwendet für neue Projekte Vitest als Standard-Unit-Test-Runner; die vorhandene Anwendung nutzt bereits das Application-Build-System, das diese Migration voraussetzt.

Die Migration ändert die Messmethode der Frontend-Coverage.
Die bisherigen Karma/Istanbul-Werte sind daher nicht direkt mit den V8-Werten von Vitest vergleichbar.
Zusätzliche Tests allein zum Ausgleich unterschiedlicher Instrumentierung würden keinen fachlichen Nutzen schaffen.

## Entscheidung

Das Frontend verwendet den Angular-Builder `@angular/build:unit-test` mit Vitest und dessen standardmäßigem V8-Coverage-Provider.
Karma, Jasmine und ihre zugehörigen Abhängigkeiten entfallen.
Bestehende Jasmine-Spezifikationen werden mit dem offiziellen Angular-Schematic nach Vitest übertragen und anschließend fachlich überprüft.

Die Coverage-Schwellen werden auf die mit der unveränderten Suite ermittelte V8-Basis kalibriert: 85 Prozent Statements und Lines, 65 Prozent Branches sowie 60 Prozent Functions.
Sie sichern die erreichte Abdeckung weiterhin ab, ohne Testfälle auf eine frühere, nicht vergleichbare Messmethode hin zu optimieren.

Vitest verwendet `jsdom`; das projektspezifische Setup ergänzt `matchMedia`, das Taiga UI in Tests benötigt.
Die Produktionsanwendung verwendet keine Legacy-Angular-Animationen und entfernt deshalb den bisherigen globalen Animationsprovider samt direkter `@angular/animations`-Abhängigkeit.

## Konsequenzen

`npm run test:ci` und `npm run test:coverage` behalten ihre öffentliche Semantik.
Der Testlauf benötigt keinen Chrome-Launcher mehr und läuft in der DOM-Emulation von Vitest.
Die Browser-Prüfung produktiver Abläufe bleibt getrennt über Playwright erhalten.

Der reguläre npm-Audit kann weiterhin moderate, ausschließlich die Entwicklungsabhängigkeit `@angular/cli` betreffende Befunde melden.
Das produktive Sicherheitsgate prüft ohne Entwicklungsabhängigkeiten und bleibt für die Auslieferung maßgeblich.
Erzwungene Audit-Fixes oder Versionsrückschritte werden nicht eingesetzt.

## Alternativen

- Karma und Jasmine beibehalten: vermeidet eine Migration, erhält aber die
abgekündigte und auditbelastete Testkette.
- Vitest mit Istanbul-Coverage: ist technisch möglich, bringt hier aber keine
vergleichbaren Altmesswerte und fügt eine unnötige Abhängigkeit hinzu.
- Zusätzliche Tests nur zur Erhöhung der neuen Kennzahlen schreiben: erhöht
die Messwerte ohne nachgewiesene fachliche Lücke.

## Referenzen

- [Angular: Migration von Karma zu Vitest](https://angular.dev/guide/testing/migrating-to-vitest)
- [Entwicklung](../development.md)
- [HTTP-Vertrag](0006-openapi-http-vertrag.md)
