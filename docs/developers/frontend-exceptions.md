# Frontend: verbleibende Taiga-UI-Ausnahmen

Issue #65 migriert produktive Controls auf Taiga UI, wo eine passende und semantisch tragfähige Komponente vorhanden ist. Die folgenden Ausnahmen bleiben bewusst bestehen:

| Bereich  | Ausnahme                                                        | Begründung                                                                                                                                                                                             |
| -------- | --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Planung  | `input[type="week"]` für ISO-Kalenderwochen                     | Taiga UI bietet keine gleichwertige ISO-Kalenderwochen-Eingabe. Der Wert und der bestehende ISO-Hinweis bleiben unverändert.                                                                           |
| Selects  | natives `select` mit `tuiSelect`                                | `tuiSelect` ist die Taiga-Direktive auf dem nativen Select-Element. Dynamische Items, `null`-/ID-Werte und bestehende Modellbindungen bleiben dadurch stabil.                                          |
| Icons    | `AppIconDirective` mit vorhandenen SVG-Pfaden                   | Die Anwendung besitzt bereits einen kleinen, getesteten SVG-Icon-Datensatz. Der Adapter ergänzt den erforderlichen `viewBox`; ein gleichwertiger Taiga-Icon-Datensatz für diese Pfade existiert nicht. |
| Layout   | `app-page-grid`, Formular- und Tabellen-Grid/Flex-Regeln        | Taiga UI bietet kein responsives 1:1-Grid für die bisherige Seitenstruktur. Die App-CSS-Schicht stellt Desktop-Spalten, Feldbreiten und mobile Stapelung ohne weiteres CSS-Framework her.              |
| Tabellen | `table`/`tuiTable` mit App-CSS für Scroll- und Spaltenverhalten | Taiga liefert die Tabellenkomponente, aber nicht die anwendungsspezifische responsive Scroll- und Aktionsspalten-Logik.                                                                                |

Nicht mehr verwendete Bootstrap-/CoreUI-nahe Badge-, Alert-, Button-, Tabellen- und native Dialog-Regeln wurden aus `frontend/src/styles.scss` entfernt.
