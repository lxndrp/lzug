from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .database import DEFAULT_DB_PATH, session_scope
from .models import (
    CANDIDATE,
    CANDIDATE_EXAM_DAY,
    COMMITTEE_MEMBER,
    EXAM_DAY,
    EXAM_DAY_ASSIGNMENT,
    EXAM_ROUND,
    EXAM_SLOT,
    MEMBER_AVAILABILITY,
    PLANNING_SETTINGS,
    ROUND_CANDIDATE,
)
from .store import Store


SIDES = ("employer", "employee", "school")


@dataclass(frozen=True)
class ShiftCrew:
    crew: tuple[int, int, int]
    fallback: int


class PlanningService:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path

    def generate_proposal(self, round_id: int) -> dict[str, Any]:
        with session_scope(self.db_path) as session:
            store = Store(session)
            context = self._load_context(store, round_id)
            if context["round"] is None:
                raise ValueError("Exam round not found")
            if context["settings"] is None:
                raise ValueError("Planning settings not found")
            if not context["candidate_days"]:
                raise ValueError("No active candidate exam days found")

            self._clear_existing_proposal(store, round_id)
            proposal = self._build_proposal(context)
            persisted = self._persist_proposal(store, context, proposal)
            store.update(EXAM_ROUND, round_id, {"status": "plan_proposed"})

            return {
                "round_id": round_id,
                "status": "plan_proposed",
                "exam_days": persisted,
                "validation": proposal["validation"],
                "counts": proposal["counts"],
            }

    def confirm_plan(self, round_id: int) -> dict[str, Any]:
        with session_scope(self.db_path) as session:
            store = Store(session)
            exam_round = store.get(EXAM_ROUND, round_id)
            if exam_round is None:
                raise ValueError("Exam round not found")

            exam_days = store.where(EXAM_DAY, exam_round_id=round_id)
            if not exam_days:
                raise ValueError("No planning proposal found")

            for exam_day in exam_days:
                if exam_day["status"] == "cancelled":
                    raise ValueError("Cancelled exam days cannot be confirmed")

            confirmed_days = []
            confirmed_slot_count = 0
            for exam_day in exam_days:
                confirmed_day = store.update(
                    EXAM_DAY,
                    exam_day["id"],
                    {"status": "confirmed"},
                )
                confirmed_days.append(confirmed_day)
                for slot in store.where(EXAM_SLOT, exam_day_id=exam_day["id"]):
                    store.update(EXAM_SLOT, slot["id"], {"status": "confirmed"})
                    confirmed_slot_count += 1
                for assignment in store.where(
                    EXAM_DAY_ASSIGNMENT,
                    exam_day_id=exam_day["id"],
                ):
                    if assignment["assignment_role"] == "fallback":
                        store.update(
                            EXAM_DAY_ASSIGNMENT,
                            assignment["id"],
                            {"fallback_status": "confirmed"},
                        )

            store.update(EXAM_ROUND, round_id, {"status": "plan_confirmed"})
            return {
                "round_id": round_id,
                "status": "plan_confirmed",
                "exam_days": confirmed_days,
                "counts": {
                    "confirmed_exam_days": len(confirmed_days),
                    "confirmed_slots": confirmed_slot_count,
                },
            }

    def _load_context(self, store: Store, round_id: int) -> dict[str, Any]:
        exam_round = store.get(EXAM_ROUND, round_id)
        settings = store.first(PLANNING_SETTINGS, exam_round_id=round_id)
        return {
            "round": exam_round,
            "settings": settings,
            "round_candidates": store.where(ROUND_CANDIDATE, exam_round_id=round_id),
            "candidates": {row["id"]: row for row in store.all(CANDIDATE)},
            "members": [
                row
                for row in store.where(
                    COMMITTEE_MEMBER,
                    committee_id=exam_round["committee_id"] if exam_round else -1,
                )
                if row["is_active"]
            ],
            "candidate_days": [
                row
                for row in store.where(CANDIDATE_EXAM_DAY, exam_round_id=round_id)
                if row["is_active"]
            ],
            "availability": store.where(MEMBER_AVAILABILITY, exam_round_id=round_id),
        }

    def _clear_existing_proposal(self, store: Store, round_id: int) -> None:
        for exam_day in store.where(EXAM_DAY, exam_round_id=round_id):
            if exam_day["status"] == "confirmed":
                raise ValueError("Confirmed exam days cannot be replaced")
            store.delete(EXAM_DAY, exam_day["id"])

    def _build_proposal(self, context: dict[str, Any]) -> dict[str, Any]:
        settings = context["settings"]
        if settings["default_location_id"] is None:
            raise ValueError("Planning settings need a default location")
        round_candidates = sorted(context["round_candidates"], key=lambda row: row["id"])
        regular_queue = list(round_candidates)
        mep_queue = [row for row in round_candidates if row["requires_mep"]]
        required_slots = len(regular_queue) + len(mep_queue)
        remaining_slots = required_slots
        load: dict[int, float] = defaultdict(float)
        days_by_week = self._days_by_week(context["candidate_days"])
        availability = self._availability_index(context["availability"])
        validation = {"passed": True, "messages": []}
        planned_days = []

        for week_key in sorted(days_by_week):
            used_days = 0
            week_days = sorted(days_by_week[week_key], key=lambda row: row["date"])
            options = []
            for day in week_days:
                morning = self._choose_shift_crew(
                    context,
                    availability,
                    day["id"],
                    "morning",
                    load,
                )
                if morning is None:
                    validation["messages"].append(
                        f"{day['date']}: keine vollstaendige Vormittagsbesetzung"
                    )
                    continue
                afternoon = self._choose_shift_crew(
                    context,
                    availability,
                    day["id"],
                    "afternoon",
                    load,
                )
                capacity = settings["exams_per_day"]
                if capacity > 4 and afternoon is None:
                    capacity = 4
                options.append(
                    {
                        "day": day,
                        "capacity": capacity,
                        "morning": morning,
                        "afternoon": afternoon,
                    }
                )

            options.sort(key=lambda option: (-option["capacity"], option["day"]["date"]))
            for option in options:
                if remaining_slots <= 0:
                    break
                if used_days >= settings["max_exam_days_per_week"]:
                    break
                exams = min(option["capacity"], remaining_slots)
                needs_afternoon = exams > 4
                morning = self._choose_shift_crew(
                    context,
                    availability,
                    option["day"]["id"],
                    "morning",
                    load,
                )
                afternoon = (
                    self._choose_shift_crew(
                        context,
                        availability,
                        option["day"]["id"],
                        "afternoon",
                        load,
                    )
                    if needs_afternoon
                    else None
                )
                if morning is None or (needs_afternoon and afternoon is None):
                    continue

                self._apply_load(load, morning)
                if afternoon:
                    self._apply_load(load, afternoon)
                planned_days.append(
                    {
                        "date": option["day"]["date"],
                        "candidate_exam_day_id": option["day"]["id"],
                        "exams": exams,
                        "morning": morning,
                        "afternoon": afternoon,
                        "regular_candidate_ids": [],
                        "mep_candidate_ids": [],
                    }
                )
                remaining_slots -= exams
                used_days += 1

        self._assign_candidates(planned_days, regular_queue, mep_queue)
        validation["passed"] = remaining_slots == 0 and not regular_queue and not mep_queue
        if remaining_slots:
            validation["messages"].append(
                f"Fuer {remaining_slots} Pruefungstermine fehlt Kapazitaet"
            )
        if regular_queue:
            validation["messages"].append(
                f"{len(regular_queue)} regulaere Pruefungen konnten nicht platziert werden"
            )
        if mep_queue:
            validation["messages"].append(
                f"{len(mep_queue)} MEP-Termine konnten nicht regelkonform platziert werden"
            )
        if not planned_days:
            validation["messages"].append("Es konnte kein Pruefungstag geplant werden")

        planned_slots = sum(day["exams"] for day in planned_days)
        return {
            "days": planned_days,
            "validation": validation,
            "counts": {
                "required_slots": required_slots,
                "planned_slots": planned_slots,
                "regular_slots": sum(len(day["regular_candidate_ids"]) for day in planned_days),
                "mep_slots": sum(len(day["mep_candidate_ids"]) for day in planned_days),
            },
        }

    def _persist_proposal(
        self,
        store: Store,
        context: dict[str, Any],
        proposal: dict[str, Any],
    ) -> list[dict[str, Any]]:
        settings = context["settings"]
        persisted_days = []
        for planned_day in proposal["days"]:
            exam_day = store.create(
                EXAM_DAY,
                {
                    "exam_round_id": context["round"]["id"],
                    "location_id": settings["default_location_id"],
                    "date": planned_day["date"],
                    "status": "proposed",
                    "lunch_break_enabled": settings["lunch_break_enabled"],
                    "created_from_proposal": 1,
                },
            )
            self._persist_assignments(store, exam_day["id"], planned_day["morning"], "morning")
            if planned_day["afternoon"]:
                self._persist_assignments(
                    store,
                    exam_day["id"],
                    planned_day["afternoon"],
                    "afternoon",
                )
            slots = self._persist_slots(store, exam_day["id"], settings, planned_day)
            persisted_days.append({**exam_day, "slots": slots})
        return persisted_days

    def _persist_assignments(
        self,
        store: Store,
        exam_day_id: int,
        shift: ShiftCrew,
        day_part: str,
    ) -> None:
        for member_id in shift.crew:
            store.create(
                EXAM_DAY_ASSIGNMENT,
                {
                    "exam_day_id": exam_day_id,
                    "committee_member_id": member_id,
                    "assignment_role": "examiner",
                    "day_part": day_part,
                    "fallback_status": None,
                },
            )
        store.create(
            EXAM_DAY_ASSIGNMENT,
            {
                "exam_day_id": exam_day_id,
                "committee_member_id": shift.fallback,
                "assignment_role": "fallback",
                "day_part": day_part,
                "fallback_status": "requested",
            },
        )

    def _persist_slots(
        self,
        store: Store,
        exam_day_id: int,
        settings: dict[str, Any],
        planned_day: dict[str, Any],
    ) -> list[dict[str, Any]]:
        slots = []
        sequence = 1
        for starts_at, ends_at in self._slot_times(
            planned_day["exams"],
            bool(settings["lunch_break_enabled"]),
        ):
            queue = (
                planned_day["regular_candidate_ids"]
                if planned_day["regular_candidate_ids"]
                else planned_day["mep_candidate_ids"]
            )
            round_candidate_id = queue.pop(0)
            slot_type = "regular" if queue is planned_day["regular_candidate_ids"] else "mep"
            slots.append(
                store.create(
                    EXAM_SLOT,
                    {
                        "exam_day_id": exam_day_id,
                        "round_candidate_id": round_candidate_id,
                        "slot_type": slot_type,
                        "starts_at": f"{planned_day['date']} {starts_at}:00",
                        "ends_at": f"{planned_day['date']} {ends_at}:00",
                        "sequence_number": sequence,
                        "status": "proposed",
                    },
                )
            )
            sequence += 1
        return slots

    def _choose_shift_crew(
        self,
        context: dict[str, Any],
        availability: dict[tuple[int, int], str],
        candidate_exam_day_id: int,
        day_part: str,
        load: dict[int, float],
    ) -> ShiftCrew | None:
        available_members = [
            member
            for member in context["members"]
            if self._available_for(
                availability.get((member["id"], candidate_exam_day_id), "pending"),
                day_part,
            )
        ]
        crew = []
        for side in SIDES:
            options = [
                member
                for member in available_members
                if member["representing_side"] == side and member["id"] not in crew
            ]
            options.sort(key=lambda member: (load[member["id"]], member["id"]))
            if not options:
                return None
            crew.append(options[0]["id"])
        fallback_options = [
            member for member in available_members if member["id"] not in set(crew)
        ]
        fallback_options.sort(key=lambda member: (load[member["id"]], member["id"]))
        if not fallback_options:
            return None
        return ShiftCrew(tuple(crew), fallback_options[0]["id"])

    def _available_for(self, availability: str, day_part: str) -> bool:
        if availability == "full_day":
            return True
        return availability == day_part

    def _apply_load(self, load: dict[int, float], shift: ShiftCrew) -> None:
        for member_id in shift.crew:
            load[member_id] += 1
        load[shift.fallback] += 0.35

    def _assign_candidates(
        self,
        planned_days: list[dict[str, Any]],
        regular_queue: list[dict[str, Any]],
        mep_queue: list[dict[str, Any]],
    ) -> None:
        mep_counts_by_index = [0 for _ in planned_days]
        for index in reversed(range(len(planned_days))):
            day = planned_days[index]
            mep_capacity = max(0, day["exams"] - 1)
            count = min(mep_capacity, len(mep_queue))
            mep_counts_by_index[index] = count
            for _ in range(count):
                day["mep_candidate_ids"].append(mep_queue.pop(0)["id"])

        for index, day in enumerate(planned_days):
            regular_count = day["exams"] - mep_counts_by_index[index]
            day["regular_candidate_ids"] = [
                regular_queue.pop(0)["id"]
                for _ in range(min(regular_count, len(regular_queue)))
            ]

    def _slot_times(self, count: int, lunch_break: bool) -> list[tuple[str, str]]:
        starts = []
        current = datetime.strptime("08:30", "%H:%M")
        lunch = datetime.strptime("12:30", "%H:%M")
        lunch_end = datetime.strptime("13:30", "%H:%M")
        for _ in range(count):
            if lunch_break and current == lunch:
                current = lunch_end
            end = current + timedelta(hours=1)
            starts.append((current.strftime("%H:%M"), end.strftime("%H:%M")))
            current = end
        return starts

    def _availability_index(
        self,
        rows: list[dict[str, Any]],
    ) -> dict[tuple[int, int], str]:
        return {
            (row["committee_member_id"], row["candidate_exam_day_id"]): row["availability"]
            for row in rows
        }

    def _days_by_week(
        self,
        candidate_days: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for day in candidate_days:
            week = datetime.strptime(day["date"], "%Y-%m-%d").isocalendar()
            grouped[f"{week.year}-W{week.week:02d}"].append(day)
        return grouped
