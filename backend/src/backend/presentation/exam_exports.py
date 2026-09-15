"""Render human-readable exam exports from already authorized view data."""

from __future__ import annotations

from typing import Any, TypedDict


class ResultExportPresentation(TypedDict):
    """The explicit result fields needed by the human renderer."""

    id: int
    state: str
    model_version: dict[str, Any]
    candidate: dict[str, Any]
    external_results: list[dict[str, Any]]
    committee_assessments: list[dict[str, Any]]
    current_calculation: dict[str, Any] | None
    current_determination: dict[str, Any] | None
    correction_open: bool
    communications: list[dict[str, Any]]


class ProtocolExportPresentation(TypedDict):
    """The explicit protocol fields needed by the human renderer."""

    id: int
    state: str
    closing_ready: bool
    current_revision: dict[str, Any]
    open_correction: bool


class ProtocolReferencesPresentation(TypedDict):
    """The explicit protocol references needed by the human renderer."""

    candidate: dict[str, Any]
    slot: dict[str, Any]
    location: dict[str, Any]
    participants: list[dict[str, Any]]


class DayClosurePresentation(TypedDict):
    """The explicit day closure fields needed by the human renderer."""

    status: str
    revision: int
    evaluation: dict[str, Any]
    history: list[dict[str, Any]]


class RoundLifecyclePresentation(TypedDict):
    """The explicit round lifecycle fields needed by the human renderer."""

    status: str
    revision: int
    history: list[dict[str, Any]]
    retention: dict[str, Any]
    ihk_statuses: list[dict[str, Any]]


class RoundSnapshotPresentation(TypedDict):
    """The explicit round snapshot fields needed by the human renderer."""

    round: dict[str, Any]
    half_year: dict[str, Any]
    committee: dict[str, Any]
    candidates: list[dict[str, Any]]
    roles: list[dict[str, Any]]
    days: list[dict[str, Any]]
    results: list[dict[str, Any]]


def render_result_export(result: ResultExportPresentation) -> str:
    """Render an assessment result without accessing or mutating persistence."""
    calculation = result["current_calculation"]
    determination = result["current_determination"]
    candidate = result["candidate"]
    marker = "FESTGESTELLT" if determination else "ENTWURF"
    lines = [
        f"Ergebnisniederschrift {result['id']} – {marker}",
        "Kein amtliches IHK-Dokument",
        f"Prüfling: {candidate['first_name']} {candidate['last_name']}",
        f"IHK-Prüfungsnummer: {candidate['ihk_exam_number']}",
        f"Bewertungsmodell: {result['model_version']['model_key']} "
        f"v{result['model_version']['version']}",
        f"Zustand: {result['state']}",
        "",
        "Bestätigte externe Eingangsergebnisse:",
    ]
    confirmed_external = [
        item for item in result["external_results"] if item["status"] == "confirmed"
    ]
    lines.extend(
        f"- {item['area_key']}: {item['points']} Punkte ({item['source_reference']})"
        for item in confirmed_external
    )
    if not confirmed_external:
        lines.append("- keine")
    lines.extend(["", "Festgestellte Komponentenbewertungen:"])
    lines.extend(
        f"- {item['component_key']}: {item['points']} Punkte"
        for item in result["committee_assessments"]
        if item["status"] == "current"
    )
    if calculation:
        lines.extend(
            [
                "",
                "Berechnungsweg:",
                *[
                    f"- {item['kind']} {item['key']}: {item['points']} × {item['weight']} %"
                    for item in calculation["path"]["inputs"]
                ],
                f"Gesamtergebnis: {calculation['total_points']} Punkte, "
                f"{calculation['grade']}, "
                f"{'bestanden' if calculation['passed'] else 'nicht bestanden'}",
            ]
        )
    if determination:
        lines.extend(
            [
                "",
                f"Feststellung: Version {determination['revision']} am "
                f"{determination['determined_at']}",
                "Mitwirkende: "
                + ", ".join(str(item) for item in determination["participant_member_ids"]),
                "Bestätigungen: "
                + ", ".join(str(item) for item in determination["confirmation_member_ids"]),
            ]
        )
        if determination["dissent"]:
            lines.append("Abweichende Voten: " + str(determination["dissent"]))
    if result["correction_open"]:
        lines.append("Korrekturvorgang: offen")
    if result["communications"]:
        current = next(
            (item for item in result["communications"] if item["status"] == "current"), None
        )
        if current:
            lines.append(f"Ergebnismitteilung: {current['communicated_at']} ({current['method']})")
    return "\n".join(lines) + "\n"


def render_protocol_export(
    protocol: ProtocolExportPresentation,
    references: ProtocolReferencesPresentation,
) -> str:
    """Render a protocol without accessing or mutating persistence."""
    current = protocol["current_revision"]
    marker = "VOLLSTÄNDIG" if protocol["closing_ready"] else "UNVOLLSTÄNDIG"
    candidate_name = (
        f"{references['candidate']['first_name']} {references['candidate']['last_name']}"
    )
    actual_completed_at = references["slot"]["actual_completed_at"] or "nicht erfasst"
    lines = [
        f"Prüfungsprotokoll {protocol['id']} – {marker}",
        f"Status: {protocol['state']}",
        f"Prüfling: {candidate_name}",
        f"IHK-Prüfungsnummer: {references['candidate']['ihk_exam_number']}",
        f"Prüfungsslot: {references['slot']['starts_at']} bis {references['slot']['ends_at']}",
        f"Tatsächlicher Beginn: {references['slot']['actual_started_at']}",
        f"Tatsächlicher Abschluss: {actual_completed_at}",
        f"Ort: {references['location']['name']} / {references['location']['room']}",
        "",
        "Tatsächlich beteiligte Prüfer:",
    ]
    lines.extend(
        f"- {person['first_name']} {person['last_name']} ({person['attendance']['status']})"
        for person in references["participants"]
    )
    lines.extend(["", f"Verlauf: {current['declaration'] or 'noch nicht festgestellt'}"])
    if current["entries"]:
        lines.append("Besonderheiten:")
        lines.extend(
            f"- [{entry['category']}] {entry['occurred_from']}"
            f"{(' bis ' + entry['occurred_to']) if entry['occurred_to'] else ''}: "
            f"{entry['statement']}"
            for entry in current["entries"]
        )
    lines.append("Reaktionen:")
    if current["responses"]:
        lines.extend(
            f"- Mitglied {response['committee_member_id']}: {response['response']}"
            f"{(': ' + response['statement']) if response['statement'] else ''}"
            for response in current["responses"]
        )
    else:
        lines.append("- keine")
    if protocol["open_correction"]:
        lines.append("Korrekturvorgang: offen")
    return "\n".join(lines) + "\n"


def render_day_closure_export(day: dict[str, Any], closure: DayClosurePresentation) -> str:
    """Render a day closure without accessing or mutating persistence."""
    lines = [
        f"Abschlussnachweis Prüfungstag {day['id']}",
        f"Datum: {day['date']}",
        f"Status: {closure['status']}",
        f"Tagesrevision: {closure['revision']}",
        "",
        "Abschlussvoraussetzungen:",
    ]
    lines.extend(
        f"- {'erfüllt' if item['ok'] else 'nicht erfüllt'}: {item['label']}"
        for item in closure["evaluation"]["items"]
    )
    if closure["history"]:
        lines.extend(["", "Abschluss- und Wiederöffnungshistorie:"])
        lines.extend(
            f"- {item['kind']} · Revision {item['revision']} · {item['created_at']}"
            for item in closure["history"]
        )
    return "\n".join(lines) + "\n"


def render_round_lifecycle_export(
    round_id: int,
    lifecycle: RoundLifecyclePresentation,
    snapshot: RoundSnapshotPresentation,
) -> str:
    """Render a round lifecycle without accessing or mutating persistence."""
    lines = [
        f"Prüfungsrundennachweis {round_id}",
        f"Runde: {snapshot['round']['name']}",
        f"Zeitraum: {snapshot['half_year']['season']} {snapshot['half_year']['year']}",
        f"Ausschuss: {snapshot['committee']['name']}",
        f"Status: {lifecycle['status']}",
        f"Revision: {lifecycle['revision']}",
        "",
        "Kandidaten:",
    ]
    lines.extend(
        f"- {item['first_name']} {item['last_name']}: {item['terminal_status']}"
        for item in snapshot["candidates"]
    )
    lines.extend(["", "Ausschussrollen:"])
    lines.extend(
        f"- {item['first_name']} {item['last_name']}: {item['committee_role']}"
        for item in snapshot["roles"]
    )
    lines.extend(["", "Prüfungstage und tatsächliche Durchführung:"])
    lines.extend(
        f"- {item['date']}: {item['status']} / {item['closure_status']}"
        for item in snapshot["days"]
    )
    lines.extend(["", "Ergebnisse und Mitteilungen:"])
    lines.extend(
        f"- Ergebnis {item['id']}: {item['state']}, " f"Mitteilungen {len(item['communications'])}"
        for item in snapshot["results"]
    )
    lines.extend(["", "Abschluss-, Absage- und Wiederöffnungshistorie:"])
    lines.extend(
        f"- Revision {item['round_revision']}: {item['event_type']} ({item['created_at']})"
        for item in lifecycle["history"]
    )
    lines.extend(
        [
            "",
            "Aufbewahrung:",
            f"- bis: {lifecycle['retention']['retain_until'] or 'nicht festgelegt'}",
            f"- Sperre: {'ja' if lifecycle['retention']['legal_hold'] else 'nein'}",
            "",
            "Nachträgliche förmliche IHK-Status:",
        ]
    )
    lines.extend(
        f"- Ergebnis {item['exam_result_id']}: {item['document_status']} "
        f"({item['document_reference']})"
        for item in lifecycle["ihk_statuses"]
    )
    return "\n".join(lines) + "\n"
