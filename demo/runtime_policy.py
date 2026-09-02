"""Public-demo routes and the server-side default-deny mutation policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from pathlib import Path
from zoneinfo import ZoneInfo

from backend.application import ForbiddenRequestError
from backend.auth import AuthContext, AuthenticationError
from backend.transport import RequestContext

from .artifacts import load_runtime_manifests, load_runtime_status
from .synthetic_fixtures_generated import DEMO_MATRIX_VERSION, DEMO_ROLES


@dataclass(frozen=True)
class DemoPathContract:
    """One testable link between UI, capability, HTTP boundary, and domain guard."""

    name: str
    roles: frozenset[str]
    scenario: str
    seed_state: str
    ui_action: str
    capability: str
    method: str
    path_pattern: str
    domain_authorization: str
    visible: bool
    allowed: bool

    def matches(self, method: str, path_parts: list[str]) -> bool:
        if method != self.method:
            return False
        expected_parts = self.path_pattern.strip("/").split("/")
        if len(expected_parts) != len(path_parts):
            return False
        return all(
            (
                actual.isdigit()
                if expected.startswith("{") and expected.endswith("}")
                else actual == expected
            )
            for expected, actual in zip(expected_parts, path_parts, strict=True)
        )


DEMO_READ_MATRIX = (
    DemoPathContract(
        "exam-half-years-read",
        frozenset(DEMO_ROLES),
        "Prüfungskontext",
        "synthetic-exam-half-year",
        "Prüfungshalbjahre und Prüfungsrunden lesen",
        "exam-half-years:read",
        "GET",
        "/exam-half-years",
        "AuthorizationScope.can_read_committee",
        True,
        True,
    ),
    DemoPathContract(
        "exam-round-lifecycle-read",
        frozenset(DEMO_ROLES),
        "Prüfungsrundenabschluss",
        "synthetic-exam-round-lifecycle-matrix",
        "Voraussetzungsmatrix und Historie lesen",
        "exam-round-lifecycle:read",
        "GET",
        "/exam-rounds/{id}/lifecycle",
        "ExamRoundLifecycleService.get",
        True,
        True,
    ),
    DemoPathContract(
        "exam-round-lifecycle-export",
        frozenset(DEMO_ROLES),
        "Prüfungsrundenabschluss",
        "synthetic-exam-round-lifecycle-matrix",
        "Revisionsgebundenen Rundennachweis exportieren",
        "exam-round-lifecycle:export",
        "GET",
        "/exam-rounds/{id}/lifecycle/export.json",
        "ExamRoundLifecycleService.machine_export",
        True,
        True,
    ),
    DemoPathContract(
        "exam-round-lifecycle-human-export",
        frozenset(DEMO_ROLES),
        "Prüfungsrundenabschluss",
        "synthetic-exam-round-lifecycle-matrix",
        "Lesbaren Rundennachweis exportieren",
        "exam-round-lifecycle:export",
        "GET",
        "/exam-rounds/{id}/lifecycle/export.txt",
        "ExamRoundLifecycleService.human_export",
        True,
        True,
    ),
    DemoPathContract(
        "notifications-read-own",
        frozenset(DEMO_ROLES),
        "Persönliche Hinweise",
        "synthetic-own-notifications",
        "Eigene Benachrichtigungen lesen",
        "notifications:read-own",
        "GET",
        "/notifications",
        "NotificationService.list_own",
        True,
        True,
    ),
    DemoPathContract(
        "calendar-read-own",
        frozenset(DEMO_ROLES),
        "Persönlicher Kalender",
        "synthetic-own-calendar-events",
        "Eigene Kalenderereignisse lesen und einzeln laden",
        "calendar:read-own",
        "GET",
        "/calendar/events",
        "CalendarService.list_events",
        True,
        True,
    ),
    DemoPathContract(
        "absence-read-own",
        frozenset(DEMO_ROLES),
        "Ausfall und Ersatz",
        "synthetic-visible-absence-state",
        "Zugängliche Ausfallprozesse read-only lesen",
        "absence:read-own",
        "GET",
        "/absence-reports",
        "AbsenceService.list",
        True,
        True,
    ),
    DemoPathContract(
        "exam-protocol-read",
        frozenset(DEMO_ROLES),
        "Prüfungsprotokoll",
        "synthetic-started-exam",
        "Gemeinsames Prüfungsprotokoll und Versionshistorie lesen",
        "exam-protocol:read",
        "GET",
        "/exam-protocols/{id}",
        "ExamProtocolService.get",
        True,
        True,
    ),
    DemoPathContract(
        "exam-protocol-export",
        frozenset(DEMO_ROLES),
        "Prüfungsprotokoll",
        "synthetic-started-exam",
        "Protokoll vollständig exportieren",
        "exam-protocol:export",
        "GET",
        "/exam-protocols/{id}/export.json",
        "ExamProtocolService.machine_export",
        True,
        True,
    ),
    DemoPathContract(
        "exam-result-read",
        frozenset(DEMO_ROLES),
        "Bewertung und Ergebnis",
        "synthetic-result-process",
        "Eigenen beziehungsweise offengelegten Ergebnisstand lesen",
        "exam-result:read",
        "GET",
        "/exam-results/{id}",
        "ExamResultService.get",
        True,
        True,
    ),
    DemoPathContract(
        "exam-result-export",
        frozenset(DEMO_ROLES),
        "Bewertung und Ergebnis",
        "synthetic-result-process",
        "Entwurf oder Ergebnisniederschrift exportieren",
        "exam-result:export",
        "GET",
        "/exam-results/{id}/export.json",
        "ExamResultService.machine_export",
        True,
        True,
    ),
    DemoPathContract(
        "exam-day-closure-read",
        frozenset(DEMO_ROLES),
        "Prüfungstagsabschluss",
        "synthetic-exam-day-closure-matrix",
        "Abschlussmatrix, Aufgaben und Historie lesen",
        "exam-day-closure:read",
        "GET",
        "/confirmed-plan-days/{day_id}/closure",
        "ExamDayClosureService.get",
        True,
        True,
    ),
    DemoPathContract(
        "exam-day-closure-export",
        frozenset(DEMO_ROLES),
        "Prüfungstagsabschluss",
        "synthetic-exam-day-closure-matrix",
        "Abschlussnachweis exportieren",
        "exam-day-closure:export",
        "GET",
        "/confirmed-plan-days/{day_id}/closure/export.json",
        "ExamDayClosureService.machine_export",
        True,
        True,
    ),
)


DEMO_MUTATION_MATRIX = (
    DemoPathContract(
        "committee-bootstrap-disabled",
        frozenset(DEMO_ROLES),
        "Ausschuss-Bootstrap",
        "operator-only-local-contract",
        "Ausschuss administrativ bootstrapen",
        "committee:bootstrap",
        "POST",
        "/committees",
        "CommitteeAdminService.bootstrap",
        False,
        False,
    ),
    DemoPathContract(
        "committee-deactivate-disabled",
        frozenset(DEMO_ROLES),
        "Ausschuss-Lebenszyklus",
        "operator-only-local-contract",
        "Ausschuss technisch deaktivieren",
        "committee:deactivate",
        "POST",
        "/committees/{id}/deactivate",
        "CommitteeAdminService.deactivate",
        False,
        False,
    ),
    DemoPathContract(
        "committee-reactivate-disabled",
        frozenset(DEMO_ROLES),
        "Ausschuss-Lebenszyklus",
        "operator-only-local-contract",
        "Ausschuss technisch reaktivieren",
        "committee:reactivate",
        "POST",
        "/committees/{id}/reactivate",
        "CommitteeAdminService.reactivate",
        False,
        False,
    ),
    DemoPathContract(
        "planning-settings-create",
        frozenset({"chair"}),
        "Terminorganisation",
        "draft-round",
        "Planungsrahmen speichern",
        "planning-settings:write",
        "POST",
        "/planning-settings",
        "LzugHandler.authorize_resource_action",
        True,
        True,
    ),
    DemoPathContract(
        "planning-settings-update",
        frozenset({"chair"}),
        "Terminorganisation",
        "draft-round-with-settings",
        "Planungsrahmen aktualisieren",
        "planning-settings:write",
        "PATCH",
        "/planning-settings/{id}",
        "LzugHandler.authorize_resource_action",
        True,
        True,
    ),
    DemoPathContract(
        "round-update",
        frozenset({"chair"}),
        "Terminorganisation",
        "draft-round",
        "Prüfungsrunde speichern",
        "round:write",
        "PATCH",
        "/exam-rounds/{id}",
        "LzugHandler.authorize_resource_action",
        True,
        True,
    ),
    DemoPathContract(
        "availability-request",
        frozenset({"chair"}),
        "Terminorganisation",
        "configured-draft-round",
        "Verfügbarkeiten anfragen",
        "availability:coordinate",
        "POST",
        "/exam-rounds/{id}/request-availabilities",
        "LzugHandler.require_round_access(manage=True)",
        True,
        True,
    ),
    DemoPathContract(
        "candidate-days-generate",
        frozenset({"chair"}),
        "Terminorganisation",
        "configured-draft-round",
        "Mögliche Prüfungstage berechnen",
        "candidate-days:generate",
        "POST",
        "/candidate-exam-days/generate",
        "LzugHandler.require_round_access(manage=True)",
        True,
        True,
    ),
    DemoPathContract(
        "availability-create-chair",
        frozenset({"chair"}),
        "Terminorganisation",
        "availability-requested-round",
        "Verfügbarkeit koordinieren",
        "availability:coordinate",
        "POST",
        "/member-availabilities",
        "LzugHandler.authorize_resource_action",
        True,
        True,
    ),
    DemoPathContract(
        "availability-create-own",
        frozenset({"examiner"}),
        "Eigene Verfügbarkeit",
        "availability-requested-round",
        "Eigene Verfügbarkeit speichern",
        "availability:write-own",
        "POST",
        "/member-availabilities",
        "AuthorizationScope.can_edit_member",
        True,
        True,
    ),
    DemoPathContract(
        "availability-update-chair",
        frozenset({"chair"}),
        "Terminorganisation",
        "existing-availability",
        "Verfügbarkeit koordinieren",
        "availability:coordinate",
        "PATCH",
        "/member-availabilities/{id}",
        "LzugHandler.authorize_resource_action",
        True,
        True,
    ),
    DemoPathContract(
        "availability-update-own",
        frozenset({"examiner"}),
        "Eigene Verfügbarkeit",
        "existing-own-availability",
        "Eigene Verfügbarkeit aktualisieren",
        "availability:write-own",
        "PATCH",
        "/member-availabilities/{id}",
        "AuthorizationScope.can_edit_member",
        True,
        True,
    ),
    DemoPathContract(
        "planning-proposal-generate",
        frozenset({"chair"}),
        "Terminorganisation",
        "complete-availability-state",
        "Planungsvorschlag erzeugen",
        "planning-proposal:generate",
        "POST",
        "/planning-proposals",
        "LzugHandler.require_round_access(manage=True)",
        True,
        True,
    ),
    DemoPathContract(
        "planning-proposal-replace",
        frozenset({"chair"}),
        "Terminorganisation",
        "generated-planning-proposal",
        "Planungsvorschlag bearbeiten",
        "planning-proposal:replace",
        "PUT",
        "/exam-rounds/{id}/planning-proposal",
        "LzugHandler.require_round_access(manage=True)",
        True,
        True,
    ),
    DemoPathContract(
        "planning-proposal-confirm",
        frozenset({"chair"}),
        "Terminorganisation",
        "valid-planning-proposal",
        "Plan bestätigen",
        "planning-proposal:confirm",
        "POST",
        "/exam-rounds/{id}/confirm-plan",
        "LzugHandler.require_round_access(manage=True)",
        True,
        True,
    ),
    DemoPathContract(
        "candidate-attendance-coordinate",
        frozenset({"chair"}),
        "Prüfungstag",
        "confirmed-exam-day",
        "Anwesenheit des Prüflings speichern",
        "attendance:coordinate",
        "PATCH",
        "/confirmed-plan-days/{day_id}/slots/{slot_id}/attendance",
        "LzugHandler.require_day_access(manage=True)",
        True,
        True,
    ),
    DemoPathContract(
        "member-attendance-coordinate",
        frozenset({"chair"}),
        "Prüfungstag",
        "confirmed-exam-day",
        "Anwesenheit der Besetzung speichern",
        "attendance:coordinate",
        "PATCH",
        "/confirmed-plan-days/{day_id}/assignments/{assignment_id}/attendance",
        "LzugHandler.require_day_access",
        True,
        True,
    ),
    DemoPathContract(
        "member-attendance-own",
        frozenset({"examiner"}),
        "Eigene Anwesenheit",
        "own-confirmed-assignment",
        "Eigene Anwesenheit speichern",
        "attendance:write-own",
        "PATCH",
        "/confirmed-plan-days/{day_id}/assignments/{assignment_id}/attendance",
        "AuthorizationScope.can_edit_member",
        True,
        True,
    ),
    DemoPathContract(
        "exam-slot-start",
        frozenset({"chair"}),
        "Prüfungstag",
        "ready-confirmed-slot",
        "Prüfung starten",
        "exam-status:write",
        "POST",
        "/confirmed-plan-days/{day_id}/slots/{slot_id}/start",
        "LzugHandler.require_day_access(manage=True)",
        True,
        True,
    ),
    DemoPathContract(
        "exam-slot-status",
        frozenset({"chair"}),
        "Prüfungstag",
        "started-confirmed-slot",
        "Durchführungsstatus speichern",
        "exam-status:write",
        "PATCH",
        "/confirmed-plan-days/{day_id}/slots/{slot_id}/status",
        "LzugHandler.require_day_access(manage=True)",
        True,
        True,
    ),
    DemoPathContract(
        "exam-day-close",
        frozenset({"chair", "deputy"}),
        "Prüfungstagsabschluss",
        "synthetic-ready-or-exception-day",
        "Prüfungstag regulär oder mit zulässiger Ausnahme abschließen",
        "exam-day-closure:close",
        "POST",
        "/confirmed-plan-days/{day_id}/closure",
        "ExamDayClosureService.close",
        True,
        True,
    ),
    DemoPathContract(
        "exam-day-reopening-impact",
        frozenset({"chair", "deputy"}),
        "Prüfungstagsabschluss",
        "synthetic-closed-exam-day",
        "Auswirkungen einer zielgerichteten Wiederöffnung prüfen",
        "exam-day-closure:preview-reopening",
        "POST",
        "/confirmed-plan-days/{day_id}/reopening-impact",
        "ExamDayClosureService.reopening_impact",
        True,
        True,
    ),
    DemoPathContract(
        "exam-day-reopen",
        frozenset({"chair", "deputy"}),
        "Prüfungstagsabschluss",
        "synthetic-closed-exam-day",
        "Prüfungstag zielgerichtet zur Korrektur wieder öffnen",
        "exam-day-closure:reopen",
        "POST",
        "/confirmed-plan-days/{day_id}/reopenings",
        "ExamDayClosureService.reopen",
        True,
        True,
    ),
    DemoPathContract(
        "exam-protocol-update",
        frozenset(DEMO_ROLES),
        "Prüfungsprotokoll",
        "synthetic-started-exam",
        "Sachverhalt als neuen Protokollstand speichern",
        "exam-protocol:write",
        "PATCH",
        "/exam-protocols/{id}",
        "ExamProtocolService.update_content",
        True,
        True,
    ),
    DemoPathContract(
        "exam-protocol-submit",
        frozenset(DEMO_ROLES),
        "Prüfungsprotokoll",
        "synthetic-protocol-draft",
        "Protokollstand zur Bestätigung vorlegen",
        "exam-protocol:submit",
        "POST",
        "/exam-protocols/{id}/submit",
        "ExamProtocolService.submit",
        True,
        True,
    ),
    DemoPathContract(
        "exam-protocol-respond",
        frozenset(DEMO_ROLES),
        "Prüfungsprotokoll",
        "synthetic-submitted-protocol",
        "Eigenen Protokollstand bestätigen oder mit Vorbehalt versehen",
        "exam-protocol:respond",
        "POST",
        "/exam-protocols/{id}/responses",
        "ExamProtocolService.respond",
        True,
        True,
    ),
    DemoPathContract(
        "exam-protocol-correction-request",
        frozenset(DEMO_ROLES),
        "Prüfungsprotokoll",
        "synthetic-complete-protocol",
        "Ergänzungsbedarf melden",
        "exam-protocol:request-correction",
        "POST",
        "/exam-protocols/{id}/correction-requests",
        "ExamProtocolService.request_correction",
        True,
        True,
    ),
    DemoPathContract(
        "exam-protocol-open-correction",
        frozenset({"chair"}),
        "Prüfungsprotokoll",
        "synthetic-correction-request",
        "Korrekturvorgang koordinieren",
        "exam-protocol:coordinate-correction",
        "POST",
        "/exam-protocols/{id}/open-correction",
        "ExamProtocolService.open_correction",
        True,
        True,
    ),
    DemoPathContract(
        "exam-protocol-retention-disabled",
        frozenset(DEMO_ROLES),
        "Prüfungsprotokoll",
        "runtime-legal-rule-not-configured",
        "Aufbewahrungsregel ändern",
        "exam-protocol:retention",
        "PUT",
        "/exam-protocols/{id}/retention",
        "ExamProtocolService.set_retention",
        False,
        False,
    ),
    DemoPathContract(
        "exam-result-assess-own",
        frozenset(DEMO_ROLES),
        "Bewertung und Ergebnis",
        "synthetic-result-process",
        "Eigene kriterienspezifische Bewertung speichern oder abgeben",
        "exam-result:assess-own",
        "POST",
        "/exam-results/{id}/individual-assessments",
        "ExamResultService.save_individual",
        True,
        True,
    ),
    DemoPathContract(
        "exam-result-withdraw-own",
        frozenset(DEMO_ROLES),
        "Bewertung und Ergebnis",
        "synthetic-hidden-assessment",
        "Eigene Bewertung vor Offenlegung zurückziehen",
        "exam-result:assess-own",
        "POST",
        "/exam-results/{id}/individual-assessments/{assessment_id}/withdraw",
        "ExamResultService.withdraw_individual",
        True,
        True,
    ),
    DemoPathContract(
        "exam-result-disclose",
        frozenset({"chair", "deputy"}),
        "Bewertung und Ergebnis",
        "synthetic-complete-individual-assessments",
        "Vollständige Einzelbewertungen kontrolliert offenlegen",
        "exam-result:disclose",
        "POST",
        "/exam-results/{id}/disclosures",
        "ExamResultService.disclose",
        True,
        True,
    ),
    DemoPathContract(
        "exam-result-determine-component",
        frozenset({"chair", "deputy"}),
        "Bewertung und Ergebnis",
        "synthetic-disclosed-assessments",
        "Gemeinsame Ausschussbewertung feststellen",
        "exam-result:determine-component",
        "POST",
        "/exam-results/{id}/committee-assessments",
        "ExamResultService.determine_component",
        True,
        True,
    ),
    DemoPathContract(
        "exam-result-record-external",
        frozenset({"chair", "deputy"}),
        "Bewertung und Ergebnis",
        "synthetic-result-process",
        "Externes Eingangsergebnis erfassen",
        "exam-result:external-record",
        "POST",
        "/exam-results/{id}/external-results",
        "ExamResultService.record_external",
        True,
        True,
    ),
    DemoPathContract(
        "exam-result-confirm-external",
        frozenset({"chair", "deputy"}),
        "Bewertung und Ergebnis",
        "synthetic-unconfirmed-external-result",
        "Fremd erfasstes Eingangsergebnis bestätigen",
        "exam-result:external-confirm",
        "POST",
        "/exam-results/{id}/external-results/{external_id}/confirm",
        "ExamResultService.confirm_external",
        True,
        True,
    ),
    DemoPathContract(
        "exam-result-determine",
        frozenset({"chair", "deputy"}),
        "Bewertung und Ergebnis",
        "synthetic-calculation-ready-result",
        "Gesamtergebnis ordnungsgemäß feststellen",
        "exam-result:determine",
        "POST",
        "/exam-results/{id}/determine",
        "ExamResultService.determine_result",
        True,
        True,
    ),
    DemoPathContract(
        "exam-result-confirm-record",
        frozenset(DEMO_ROLES),
        "Bewertung und Ergebnis",
        "synthetic-determined-result",
        "Ergebnisniederschrift bestätigen",
        "exam-result:confirm-record",
        "POST",
        "/exam-results/{id}/record-confirmations",
        "ExamResultService.confirm_record",
        True,
        True,
    ),
    DemoPathContract(
        "exam-result-correction",
        frozenset({"chair", "deputy"}),
        "Bewertung und Ergebnis",
        "synthetic-determined-result",
        "Begründeten Korrekturvorgang eröffnen",
        "exam-result:coordinate-correction",
        "POST",
        "/exam-results/{id}/corrections",
        "ExamResultService.open_correction",
        True,
        True,
    ),
    DemoPathContract(
        "exam-result-communicate",
        frozenset({"chair", "deputy"}),
        "Bewertung und Ergebnis",
        "synthetic-confirmed-result-record",
        "Ergebnismitteilung dokumentieren",
        "exam-result:communicate",
        "POST",
        "/exam-results/{id}/communications",
        "ExamResultService.communicate",
        True,
        True,
    ),
    DemoPathContract(
        "exam-result-retention-disabled",
        frozenset(DEMO_ROLES),
        "Bewertung und Ergebnis",
        "runtime-legal-rule-not-configured",
        "Aufbewahrungsregel ändern",
        "exam-result:retention",
        "PUT",
        "/exam-results/{id}/retention",
        "ExamResultService.set_retention",
        False,
        False,
    ),
    DemoPathContract(
        "candidate-day-create-read-only",
        frozenset(DEMO_ROLES),
        "Terminorganisation",
        "candidate-day-list",
        "Prüfungstag manuell anlegen",
        "candidate-days:create",
        "POST",
        "/candidate-exam-days",
        "LzugHandler.authorize_resource_action",
        False,
        False,
    ),
    DemoPathContract(
        "candidate-day-toggle-read-only",
        frozenset(DEMO_ROLES),
        "Terminorganisation",
        "candidate-day-list",
        "Prüfungstag aktivieren oder deaktivieren",
        "candidate-days:toggle",
        "PATCH",
        "/candidate-exam-days/{id}",
        "LzugHandler.authorize_resource_action",
        False,
        False,
    ),
    DemoPathContract(
        "exam-half-year-create-read-only",
        frozenset(DEMO_ROLES),
        "Prüfungskontext",
        "synthetic-exam-half-year",
        "Prüfungshalbjahr anlegen",
        "exam-half-years:write",
        "POST",
        "/exam-half-years",
        "LzugHandler.authorize_resource_action",
        False,
        False,
    ),
    DemoPathContract(
        "exam-half-year-update-read-only",
        frozenset(DEMO_ROLES),
        "Prüfungskontext",
        "synthetic-exam-half-year",
        "Prüfungshalbjahr bearbeiten oder abschließen",
        "exam-half-years:write",
        "PATCH",
        "/exam-half-years/{id}",
        "LzugHandler.authorize_resource_action",
        False,
        False,
    ),
    DemoPathContract(
        "exam-round-create",
        frozenset({"chair", "deputy"}),
        "Prüfungskontext",
        "synthetic-empty-exam-round",
        "Prüfungsrunde mit Halbjahreskontext anlegen",
        "exam-round:create",
        "POST",
        "/exam-rounds",
        "LzugHandler.authorize_resource_action",
        True,
        True,
    ),
    DemoPathContract(
        "exam-round-delete-empty",
        frozenset({"chair", "deputy"}),
        "Prüfungsrundenabschluss",
        "synthetic-empty-exam-round",
        "Vollständig leere Entwurfsrunde löschen",
        "exam-round:delete-empty",
        "DELETE",
        "/exam-rounds/{id}",
        "ExamRoundLifecycleService.delete_empty_draft",
        True,
        True,
    ),
    DemoPathContract(
        "exam-round-close",
        frozenset({"chair", "deputy"}),
        "Prüfungsrundenabschluss",
        "synthetic-closable-exam-round",
        "Prüfungsrunde nach vollständiger Matrix abschließen",
        "exam-round:close",
        "POST",
        "/exam-rounds/{id}/closure",
        "ExamRoundLifecycleService.close",
        True,
        True,
    ),
    DemoPathContract(
        "exam-round-cancel",
        frozenset({"chair", "deputy"}),
        "Prüfungsrundenabschluss",
        "synthetic-cancellable-exam-round",
        "Noch nicht begonnene Prüfungsrunde vollständig absagen",
        "exam-round:cancel",
        "POST",
        "/exam-rounds/{id}/cancellation",
        "ExamRoundLifecycleService.cancel",
        True,
        True,
    ),
    DemoPathContract(
        "exam-round-reopen",
        frozenset({"chair", "deputy"}),
        "Prüfungsrundenabschluss",
        "synthetic-closed-exam-round",
        "Beendete Prüfungsrunde gezielt wieder öffnen",
        "exam-round:reopen",
        "POST",
        "/exam-rounds/{id}/reopenings",
        "ExamRoundLifecycleService.reopen",
        True,
        True,
    ),
    DemoPathContract(
        "exam-round-reopening-impact",
        frozenset({"chair", "deputy"}),
        "Prüfungsrundenabschluss",
        "synthetic-closed-exam-round",
        "Auswirkungen einer gezielten Wiederöffnung prüfen",
        "exam-round:reopen",
        "POST",
        "/exam-rounds/{id}/reopening-impact",
        "ExamRoundLifecycleService.reopening_impact",
        True,
        True,
    ),
    DemoPathContract(
        "exam-round-terminal-status",
        frozenset({"chair", "deputy"}),
        "Prüfungsrundenabschluss",
        "synthetic-exam-round-candidates",
        "Abschließenden Prüflingsstatus dokumentieren",
        "exam-round:candidate-terminal",
        "PUT",
        "/exam-rounds/{id}/candidates/{candidate_id}/terminal-status",
        "ExamRoundLifecycleService.set_candidate_terminal_status",
        True,
        True,
    ),
    DemoPathContract(
        "exam-round-ihk-status",
        frozenset({"chair", "deputy"}),
        "Prüfungsrundenabschluss",
        "synthetic-result-process",
        "Späteren förmlichen IHK-Status dokumentieren",
        "exam-round:document-ihk-status",
        "PUT",
        "/exam-rounds/{id}/results/{result_id}/ihk-status",
        "ExamRoundLifecycleService.document_ihk_status",
        True,
        True,
    ),
    DemoPathContract(
        "push-subscribe-disabled",
        frozenset(DEMO_ROLES),
        "Persönliche Hinweise",
        "external-delivery-disabled",
        "Browser-Benachrichtigungen aktivieren",
        "push:manage-own",
        "POST",
        "/push-subscriptions",
        "NotificationService.register_push",
        False,
        False,
    ),
    DemoPathContract(
        "calendar-feed-activate-disabled",
        frozenset(DEMO_ROLES),
        "Persönlicher Kalender",
        "feed-management-disabled",
        "Persönlichen Feed aktivieren oder neu erzeugen",
        "calendar:feed-manage-own",
        "POST",
        "/calendar/feed",
        "CalendarService.activate",
        False,
        False,
    ),
    DemoPathContract(
        "calendar-feed-revoke-disabled",
        frozenset(DEMO_ROLES),
        "Persönlicher Kalender",
        "feed-management-disabled",
        "Persönlichen Feed widerrufen",
        "calendar:feed-manage-own",
        "DELETE",
        "/calendar/feed",
        "CalendarService.revoke",
        False,
        False,
    ),
    DemoPathContract(
        "absence-report-disabled",
        frozenset(DEMO_ROLES),
        "Ausfall und Ersatz",
        "absence-scenario-not-released",
        "Eigenen Ausfall melden",
        "absence:write-own",
        "POST",
        "/absence-reports",
        "AbsenceService.report",
        False,
        False,
    ),
    DemoPathContract(
        "absence-response-disabled",
        frozenset(DEMO_ROLES),
        "Ausfall und Ersatz",
        "absence-scenario-not-released",
        "Eigene Ersatzanfrage beantworten",
        "absence:respond-own",
        "PATCH",
        "/replacement-responses/{id}",
        "AbsenceService.respond",
        False,
        False,
    ),
)


ROLE_CAPABILITIES = {
    role: frozenset(
        contract.capability
        for contract in (*DEMO_READ_MATRIX, *DEMO_MUTATION_MATRIX)
        if contract.allowed and role in contract.roles
    )
    for role in DEMO_ROLES
}


class DemoRuntimePolicy:
    """Expose only the explicitly approved public-demo behavior."""

    def __init__(self, app_manifest_path: Path, seed_manifest_path: Path):
        self.app_manifest, self.seed_manifest = load_runtime_manifests(
            app_manifest_path, seed_manifest_path
        )
        self.runtime_status = load_runtime_status(seed_manifest_path.parent, self.seed_manifest)

    def handle_public_get(self, handler: RequestContext, path_parts: list[str]) -> bool:
        if path_parts != ["demo", "status"]:
            return False
        next_reset = self._next_reset()
        handler.respond(
            {
                "mode": "demo",
                "product_version": self.app_manifest["product"]["version"],
                "product_commit": self.app_manifest["product"]["commit"],
                "runtime_contract": self.app_manifest["runtime_contract"],
                "demo_matrix_version": DEMO_MATRIX_VERSION,
                "fixture_catalog_version": self.seed_manifest["fixture_catalog"]["version"],
                "fixture_catalog_revision": self.seed_manifest["fixture_catalog"]["revision"],
                "seed_revision": self.seed_manifest["seed_revision"],
                "schema_fingerprint": self.seed_manifest["schema"]["fingerprint"],
                "initialized": self.runtime_status["initialized"],
                "initialization_status": self.runtime_status["initialization_status"],
                "initialized_at": self.runtime_status["initialized_at"],
                "last_reset_at": self.runtime_status["last_reset_at"],
                "reset_status": "scheduled",
                "next_reset_at": next_reset.isoformat(),
                "reset_timezone": "Europe/Berlin",
                "notices": [
                    "Alle Eingaben sind flüchtig und werden beim Reset verworfen.",
                    "Keine realen personenbezogenen Daten eingeben.",
                    "Laufende Sitzungen enden beim Reset.",
                ],
            }
        )
        return True

    def handle_public_post(self, handler: RequestContext, path_parts: list[str]) -> bool:
        if path_parts != ["demo", "session"]:
            return False
        if not handler.allow_public_auth_request(path_parts):
            return True
        payload = handler.read_json()
        role_name = payload.get("role")
        role = DEMO_ROLES.get(role_name) if isinstance(role_name, str) else None
        if role is None:
            handler.respond({"error": "Unknown demo role."}, HTTPStatus.BAD_REQUEST)
            return True
        try:
            credentials = handler.authentication_repository.create_session(
                role["account_id"], ttl=handler.session_ttl
            )
        except AuthenticationError:
            handler.respond({"error": "Demo role is unavailable."}, HTTPStatus.SERVICE_UNAVAILABLE)
            return True
        handler.issue_session_cookies(credentials)
        handler.respond(
            {
                "authenticated": True,
                "role": role_name,
                "display_name": role["display_name"],
                "expires_at": credentials.expires_at,
            },
            HTTPStatus.CREATED,
        )
        return True

    def allow_product_auth(self) -> bool:
        return False

    def session_view(self, context: AuthContext) -> dict:
        role_name = self._role_name(context)
        role = DEMO_ROLES[role_name]
        return {
            "demo_role": role_name,
            "display_name": role["display_name"],
            "capabilities": sorted(ROLE_CAPABILITIES[role_name]),
            "demo_matrix_version": DEMO_MATRIX_VERSION,
        }

    def authorize_mutation(
        self,
        handler: RequestContext,
        method: str,
        path_parts: list[str],
        context: AuthContext,
    ) -> None:
        role = self._role_name(context)
        path = "/".join(path_parts)
        if method == "POST" and path in {"session/rotate", "session/logout"}:
            return
        if any(
            contract.allowed and role in contract.roles and contract.matches(method, path_parts)
            for contract in DEMO_MUTATION_MATRIX
        ):
            return
        message = (
            "This write operation is disabled for this demo role."
            if role == "examiner"
            else "This write operation is disabled in the demo."
        )
        raise ForbiddenRequestError(message)

    @staticmethod
    def _role_name(context: AuthContext) -> str:
        for name, role in DEMO_ROLES.items():
            if context.person_id == role["person_id"] and context.account_id == role["account_id"]:
                return name
        raise ForbiddenRequestError("This account is not available in the demo.")

    @staticmethod
    def _next_reset() -> datetime:
        timezone = ZoneInfo("Europe/Berlin")
        now = datetime.now(UTC).astimezone(timezone)
        candidate = now.replace(hour=3, minute=0, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate
