"""Typed validation models for assessment rule configurations."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
    ValidationInfo,
    model_validator,
)


def _decimal(value: object, info: ValidationInfo) -> Decimal:
    field = info.field_name or "Wert"
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError(f"{field} muss eine Zahl sein")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{field} muss eine Zahl sein") from error
    return result


class _RuleModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CriterionRules(_RuleModel):
    key: Annotated[
        str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=100)
    ]
    label: Annotated[
        str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=300)
    ]
    raw_min: Annotated[Decimal, BeforeValidator(_decimal), Field(allow_inf_nan=False)]
    raw_max: Annotated[Decimal, BeforeValidator(_decimal), Field(allow_inf_nan=False)]
    weight: Annotated[
        Decimal,
        BeforeValidator(_decimal),
        Field(allow_inf_nan=False, gt=Decimal("0.0000001"), le=100),
    ]

    @model_validator(mode="after")
    def validate_interval(self) -> CriterionRules:
        if self.raw_max <= self.raw_min:
            raise ValueError("Eine Rohpunkteskala benötigt ein echtes Intervall")
        return self


class ComponentRules(_RuleModel):
    key: Annotated[
        str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=100)
    ]
    label: Annotated[
        str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=300)
    ]
    mode: Literal["committee", "independent"]
    weight: Annotated[
        Decimal,
        BeforeValidator(_decimal),
        Field(allow_inf_nan=False, gt=Decimal("0.0000001"), le=100),
    ]
    day_scoped: StrictBool
    required_assessors: Annotated[StrictInt, Field(ge=1)]
    max_deviation: Annotated[
        Decimal, BeforeValidator(_decimal), Field(allow_inf_nan=False, ge=0, le=100)
    ]
    additional_assessor_on_deviation: StrictBool
    criteria: list[CriterionRules]

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
    key: Annotated[
        str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=100)
    ]
    label: Annotated[
        str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=300)
    ]
    weight: Annotated[Decimal, BeforeValidator(_decimal), Field(allow_inf_nan=False, ge=0, le=100)]
    required: StrictBool


class RoundingStage(_RuleModel):
    mode: Literal["none", "half_up"]
    digits: Annotated[StrictInt, Field(ge=0, le=6)] | None

    @model_validator(mode="after")
    def validate_digits(self) -> RoundingStage:
        if self.mode == "none" and self.digits is not None:
            raise ValueError("Ohne Rundung dürfen keine Nachkommastellen angegeben werden")
        return self


class RoundingRules(_RuleModel):
    intermediate: RoundingStage
    overall: RoundingStage
    threshold_basis: Literal["unrounded", "rounded"]


class GradeRule(_RuleModel):
    label: Annotated[
        str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=100)
    ]
    min_points: Annotated[
        Decimal, BeforeValidator(_decimal), Field(allow_inf_nan=False, ge=0, le=100)
    ]


class PassingRules(_RuleModel):
    overall_min: Annotated[
        Decimal, BeforeValidator(_decimal), Field(allow_inf_nan=False, ge=0, le=100)
    ]
    component_minima: dict[
        str, Annotated[Decimal, BeforeValidator(_decimal), Field(allow_inf_nan=False, ge=0, le=100)]
    ]
    external_minima: dict[
        str, Annotated[Decimal, BeforeValidator(_decimal), Field(allow_inf_nan=False, ge=0, le=100)]
    ]


class QuorumRules(_RuleModel):
    minimum_members: Annotated[StrictInt, Field(ge=1)]
    majority: Literal["simple"]


class AssessmentRules(_RuleModel):
    components: list[ComponentRules]
    external_areas: list[ExternalAreaRules]
    rounding: RoundingRules
    grades: list[GradeRule]
    passing: PassingRules
    quorum: QuorumRules

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
