# GitHub-Antwortstrukturen

Die Fixtures basieren auf am 25.09.2026 per `gh api` gelesenen Antworten:
Workflow-Run `34787732022` und erstes Objekt der Repository-Artefaktliste.
Beim Run sind ausschließlich die für die Auswahl relevanten Originalfelder enthalten.
Repository, IDs, SHA, Digest, Namen, Größen und Zeitpunkte sind anonymisiert
beziehungsweise für reproduzierbare Grenzwerttests normalisiert.
Die Tests vervielfältigen die Artefaktstruktur für die benötigten Nachweise.

Workflow-Runs besitzen `run_started_at`, `created_at` und `updated_at`,
aber kein `completed_at`.
Dieses Feld gehört zu Jobs; der Selektor verwendet stattdessen konservativ
das älteste `created_at` der benötigten Artefakte.
`updated_at` verlängert die Frist nicht.
