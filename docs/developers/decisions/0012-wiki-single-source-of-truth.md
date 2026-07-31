# ADR-0012: Redaktionelle Single Source of Truth im GitHub Wiki

## Status

Akzeptiert, ersetzt ADR-0011 am 30.07.2026.

## Kontext

ADR-0011 legt das GitHub Wiki als öffentliche redaktionelle
Handbuchoberfläche fest. Die erste Veröffentlichung hat jedoch gezeigt, dass
verschachtelte Wiki-Dateien und `.md`-Links auf Rohdateien führen können und
dass ausführliche Repository-Kopien neben einem gekürzten Wiki zwei
widersprüchliche Handbuchstände erzeugen.

## Entscheidung

- Jeder redaktionelle Inhalt besitzt genau eine kanonische Ablage.
- Vollständige Fachlichkeit sowie Nutzer- und Administratorhandbuch liegen im
  separaten GitHub Wiki.
- Das Wiki verwendet global eindeutige, flache Markdown-Dateinamen. Interne
  Wiki-Links sind extensionless und zeigen auf gerenderte Wiki-Seiten.
- Das Hauptrepository bleibt kanonisch für code-, CI-, API-, Schema-,
  release- und revisionsgebundene technische Inhalte.
- Gekürzte, ausführliche oder als „Arbeitskopie“ bezeichnete Parallelfassungen
  redaktioneller Inhalte sind ausgeschlossen.
- ADR-0011 bleibt als unveränderliche historische Entscheidung erhalten; diese
  ADR präzisiert und ersetzt ihre laufende Regelung.

## Konsequenzen

Die Wiki-Quelle wird separat geprüft und veröffentlicht. `_Sidebar.md` ist die
kanonische und vollständige Liste der öffentlichen Inhaltsseiten. Der
Hauptrepository-Validator prüft die bidirektionale Synchronität, Struktur und
sichere Routenform und erzeugt daraus nur für die Prüfung eine Sitemap. Lychee
prüft Quelllinks sowie nach Veröffentlichung die erwarteten gerenderten
Wiki-Routen; jede Weiterleitung ist dabei ein Fehler.

Technische Dokumente dürfen aus dem Wiki verlinkt werden, werden aber nicht
als zweite redaktionelle Fassung dorthin kopiert.

## Referenzen

- [ADR-0011: GitHub Wiki als redaktionelle Handbuchoberfläche](0011-github-wiki-handbuch.md)
- [Wiki-Publikation](../wiki-publishing.md)
- [GitHub Wiki](https://github.com/lxndrp/lzug/wiki)
