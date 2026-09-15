"""Typed validation models for assessment rule configurations."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)


def _decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError(f"{field} muss eine Zahl sein")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{field} muss eine Zahl sein") from error
    if not result.is_finite():
        raise ValueError(f"{field} muss endlich sein")
    return result


def _points(value: object, field: str) -> Decimal:
    points = _decimal(value, field)
    if points < 0 or points > 100:
        raise ValueError(f"{field} muss zwischen 0 und 100 liegen")
    return points


def _percentage(value: object, field: str, *, allow_zero: bool = False) -> Decimal:
    percentage = _decimal(value, field)
    minimum = Decimal(0) if allow_zero else Decimal("0.0000001")
    if percentage < minimum or percentage > 100:
        raise ValueError(f"{field} muss zwischen {minimum} und 100 liegen")
    return percentage


def _text(value: object, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} ist erforderlich")
    normalized = value.strip()
    if len(normalized) > maximum:
        raise ValueError(f"{field} ist zu lang")
    return normalized


def _list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{field} muss eine Liste sein")
    return value


def _mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} muss ein Objekt sein")
    return value


class _RuleModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CriterionRules(_RuleModel):
    key: StrictStr
    label: StrictStr
    raw_min: Decimal
    raw_max: Decimal
    weight: Decimal

    @field_validator("key")
    @classmethod
    def key_text(cls, value: str) -> str:
        return _text(value, "criterion key", 100)

    @field_validator("label")
    @classmethod
    def label_text(cls, value: str) -> str:
        return _text(value, "label", 300)

    @field_validator("raw_min", "raw_max", mode="before")
    @classmethod
    def decimal_value(cls, value: object, info) -> Decimal:
        return _decimal(value, info.field_name)

    @field_validator("weight", mode="before")
    @classmethod
    def percentage_value(cls, value: object) -> Decimal:
        return _percentage(value, "criterion weight")

    @model_validator(mode="after")
    def validate_interval(self) -> CriterionRules:
        if self.raw_max <= self.raw_min:
            raise ValueError("Eine Rohpunkteskala benötigt ein echtes Intervall")
        return self


class ComponentRules(_RuleModel):
    key: StrictStr
    label: StrictStr
    mode: Literal["committee", "independent"]
    weight: Decimal
    day_scoped: StrictBool
    required_assessors: StrictInt
    max_deviation: Decimal
    additional_assessor_on_deviation: StrictBool
    criteria: list[CriterionRules]

    @field_validator("key")
    @classmethod
    def key_text(cls, value: str) -> str:
        return _text(value, "component key", 100)

    @field_validator("label")
    @classmethod
    def label_text(cls, value: str) -> str:
        return _text(value, "label", 300)

    @field_validator("criteria", mode="before")
    @classmethod
    def criteria_list(cls, value: object) -> list[object]:
        return _list(value, "criteria")

    @field_validator("weight", mode="before")
    @classmethod
    def percentage_value(cls, value: object) -> Decimal:
        return _percentage(value, "component weight")

    @field_validator("max_deviation", mode="before")
    @classmethod
    def deviation_value(cls, value: object) -> Decimal:
        return _percentage(value, "max_deviation", allow_zero=True)

    @field_validator("required_assessors")
    @classmethod
    def assessor_count(cls, value: int) -> int:
        if value < 1:
            raise ValueError("required_assessors muss eine ganze Zahl ab 1 sein")
        return value

    @model_validator(mode="after")
    def validate_criteria(self) -> ComponentRules:
        keys = [criterion.key for criterion in self.criteria]
        if not keys:
            raise ValueError("Eine Komponente benötigt Kriterien")
        if len(keys) != len(set(keys)):
            raise ValueError("Kriterienschlüssel müssen eindeutig sein")
        if sum((criterion.weight for criterion in self.criteria), Decimal(0)) != Decimal(100):
            raise ValueError("Direkte Gewichte der Ebene Kriterien müssen 100 Prozent ergeben")
        return self


class ExternalAreaRules(_RuleModel):
    key: StrictStr
    label: StrictStr
    weight: Decimal
    required: StrictBool

    @field_validator("key")
    @classmethod
    def key_text(cls, value: str) -> str:
        return _text(value, "external area key", 100)

    @field_validator("label")
    @classmethod
    def label_text(cls, value: str) -> str:
        return _text(value, "label", 300)

    @field_validator("weight", mode="before")
    @classmethod
    def percentage_value(cls, value: object) -> Decimal:
        return _percentage(value, "external weight", allow_zero=True)


class RoundingStage(_RuleModel):
    mode: Literal["none", "half_up"]
    digits: StrictInt | None

    @model_validator(mode="after")
    def validate_digits(self) -> RoundingStage:
        if self.mode == "none" and self.digits is not None:
            raise ValueError("Ohne Rundung dürfen keine Nachkommastellen angegeben werden")
        if self.digits is not None and not 0 <= self.digits <= 6:
            raise ValueError("digits darf höchstens 6 sein")
        return self


class RoundingRules(_RuleModel):
    intermediate: RoundingStage
    overall: RoundingStage
    threshold_basis: Literal["unrounded", "rounded"]


class GradeRule(_RuleModel):
    label: StrictStr
    min_points: Decimal

    @field_validator("label")
    @classmethod
    def label_text(cls, value: str) -> str:
        return _text(value, "grade label", 100)

    @field_validator("min_points", mode="before")
    @classmethod
    def points_value(cls, value: object) -> Decimal:
        return _points(value, "min_points")


class PassingRules(_RuleModel):
    overall_min: Decimal
    component_minima: dict[str, Decimal]
    external_minima: dict[str, Decimal]

    @field_validator("overall_min", mode="before")
    @classmethod
    def overall_points(cls, value: object) -> Decimal:
        return _points(value, "overall_min")

    @field_validator("component_minima", "external_minima", mode="before")
    @classmethod
    def minima_mapping(cls, value: object, info) -> dict[str, object]:
        mapping = _mapping(value, info.field_name)
        return {key: _points(item, key) for key, item in mapping.items()}

    @field_validator("component_minima", "external_minima", mode="after")
    @classmethod
    def minima_points(cls, value: dict[str, Decimal], info) -> dict[str, Decimal]:
        return {key: _points(item, key) for key, item in value.items()}


class QuorumRules(_RuleModel):
    minimum_members: StrictInt
    majority: Literal["simple"]

    @field_validator("minimum_members")
    @classmethod
    def member_count(cls, value: int) -> int:
        if value < 1:
            raise ValueError("minimum_members muss eine ganze Zahl ab 1 sein")
        return value


class AssessmentRules(_RuleModel):
    components: list[ComponentRules]
    external_areas: list[ExternalAreaRules]
    rounding: RoundingRules
    grades: list[GradeRule]
    passing: PassingRules
    quorum: QuorumRules

    @field_validator("components", "external_areas", "grades", mode="before")
    @classmethod
    def collection_list(cls, value: object, info) -> list[object]:
        return _list(value, info.field_name)

    @model_validator(mode="after")
    def validate_cross_references(self) -> AssessmentRules:
        if not self.components:
            raise ValueError("Mindestens eine bewertete Komponente ist erforderlich")
        component_keys = [component.key for component in self.components]
        external_keys = [area.key for area in self.external_areas]
        if len(component_keys) != len(set(component_keys)):
            raise ValueError("Komponentenschlüssel müssen eindeutig sein")
        occupied = set(component_keys)
        if occupied.intersection(external_keys) or len(external_keys) != len(set(external_keys)):
            raise ValueError("Prüfungsbereichsschlüssel müssen eindeutig sein")
        weights = [component.weight for component in self.components] + [
            area.weight for area in self.external_areas
        ]
        if sum(weights, Decimal(0)) != Decimal(100):
            raise ValueError(
                "Direkte Gewichte der Ebene Komponenten und Prüfungsbereiche "
                "müssen 100 Prozent ergeben"
            )
        if not self.grades:
            raise ValueError("Mindestens eine Notenzuordnung ist erforderlich")
        previous = Decimal(101)
        for grade in self.grades:
            if grade.min_points >= previous:
                raise ValueError("Notengrenzen müssen streng absteigend sortiert sein")
            previous = grade.min_points
        if self.grades[-1].min_points != Decimal(0):
            raise ValueError("Die Notenzuordnung muss die gesamte Skala bis 0 abdecken")
        if set(self.passing.component_minima) - set(component_keys) or set(
            self.passing.external_minima
        ) - set(external_keys):
            raise ValueError("Eine Bestehensgrenze verweist auf einen unbekannten Bereich")
        return self

    def as_json_data(self) -> dict[str, object]:
        return self.model_dump(mode="json")
