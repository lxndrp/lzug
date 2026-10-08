"""Assessment-owned commands, materialized projections, and persistence ports.

The contracts keep Assessment use cases independent of SQLAlchemy and transport
models. A write UoW includes all child rows of an operation and never commits on
its own; the caller owns the transaction boundary.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from typing import Any, Literal, Protocol, TypedDict

from backend.assessment.rules import AssessmentRules

AssessmentStatus = Literal["incomplete", "calculation_ready", "determined", "communicated"]


class AssessmentActorSnapshot(TypedDict):
    """Detached active membership scope for one authenticated actor."""

    person_id: int | None
    person_ids: Sequence[int]
    committee_ids: Sequence[int]
    member_ids: Sequence[int]
    management_committee_ids: Sequence[int]
    member_by_committee: Mapping[int, int]


class AssessmentModelCommand(TypedDict):
    model_key: str
    version: int
    ihk: str
    occupation: str
    specialization: str | None
    training_regulation: str
    exam_regulation: str
    ihk_guidelines: str
    valid_from: str
    valid_until: str | None
    official_scale_min: str
    official_scale_max: str
    rules: AssessmentRules
    retention_rule_reference: str
    retention_years: int
    actor_member_id: int


class EnsureRoundResultsCommand(TypedDict):
    round_id: int
    expected_binding_version: int


class RoundBindingCommand(TypedDict):
    round_id: int
    model_version_id: int
    expected_binding_version: int | None
    actor_member_id: int
    reason: str
    bound_at: str


class IndividualAssessmentCommand(TypedDict):
    result_id: int
    expected_result_version: int
    component_key: str
    criterion_key: str
    assessor_member_id: int
    raw_points: str
    normalized_points: str
    rationale: str | None
    status: Literal["draft", "submitted", "withdrawn"]
    previous_assessment_id: int | None
    change_reason: str | None
    submitted_at: str | None
    created_at: str


class DisclosureCommand(TypedDict):
    result_id: int
    expected_result_version: int
    component_key: str
    disclosed_by_member_id: int
    disclosed_at: str


class ComponentCalculationInput(TypedDict):
    kind: Literal["component"]
    key: str
    points: str
    weight: str


class ExternalCalculationInput(TypedDict):
    kind: Literal["external"]
    key: str
    points: str
    weight: str
    revision_id: int


class CalculationPath(TypedDict):
    inputs: Sequence[ComponentCalculationInput | ExternalCalculationInput]
    unrounded_total: str
    rounded_total: str
    threshold_basis: Literal["unrounded", "rounded"]


class CalculationCommand(TypedDict):
    result_id: int
    expected_result_version: int
    result_state: AssessmentStatus
    version: int
    input_fingerprint: str
    total_points: str
    grade: str
    passed: bool
    path: CalculationPath
    created_at: str


class ResultStateCommand(TypedDict):
    result_id: int
    expected_result_version: int
    state: AssessmentStatus


class CommitteeVote(TypedDict):
    yes_member_ids: Sequence[int]
    no_member_ids: Sequence[int]


class CommitteeDissent(TypedDict):
    member_id: int
    statement: str


class ComponentDeterminationCommand(TypedDict):
    result_id: int
    expected_result_version: int
    component_key: str
    revision: int
    points: str
    rationale: str | None
    participant_member_ids: Sequence[int]
    vote: CommitteeVote
    dissent: Sequence[CommitteeDissent]
    previous_assessment_id: int | None
    determined_by_member_id: int
    determined_at: str


class ExternalResultCommand(TypedDict):
    result_id: int
    expected_result_version: int
    area_key: str
    revision: int
    points: str
    grade: str | None
    professional_status: str
    determining_authority: str
    source_reference: str
    recorded_by_member_id: int
    recorded_at: str
    previous_external_result_id: int | None
    correction_reason: str | None
    result_state: AssessmentStatus


class ExternalResultConfirmationCommand(TypedDict):
    result_id: int
    external_result_id: int
    expected_result_version: int
    confirmed_by_member_id: int
    confirmed_at: str


class ResultDeterminationCommand(TypedDict):
    result_id: int
    expected_result_version: int
    calculation_id: int
    revision: int
    participant_member_ids: Sequence[int]
    vote: CommitteeVote
    dissent: Sequence[CommitteeDissent]
    previous_determination_id: int | None
    correction_id: int | None
    determined_by_member_id: int
    determined_at: str


class RecordConfirmationCommand(TypedDict):
    result_id: int
    expected_result_version: int
    determination_id: int
    committee_member_id: int
    confirmed_at: str


class CorrectionCommand(TypedDict):
    result_id: int
    expected_result_version: int
    determination_id: int
    reason: str
    requested_by_member_id: int
    reopening_reference: str | None
    requested_at: str


class DayReopeningCorrectionCommand(TypedDict):
    result_id: int
    expected_result_version: int
    reopening_reference: str
    requested_by_member_id: int
    reason: str
    requested_at: str


class DayReopeningCorrectionReceipt(TypedDict):
    result_id: int
    result_version: int
    determination_id: int | None
    participant_member_ids: Sequence[int]
    communicated: bool
    ihk_processed: bool


class CommunicationCommand(TypedDict):
    result_id: int
    expected_result_version: int
    determination_id: int
    method: str
    responsible_member_id: int
    communicated_at: str
    external_document_status: str | None
    external_document_reference: str | None
    created_at: str


class RetentionCommand(TypedDict):
    result_id: int
    expected_result_version: int
    rule_reference: str
    version: int
    period_start: str | None
    retain_until: str | None
    legal_hold: bool
    hold_reason: str | None
    release_reason: str | None
    updated_by_member_id: int
    updated_at: str


class AssessmentModelSnapshot(TypedDict):
    id: int
    model_key: str
    version: int
    ihk: str
    occupation: str
    specialization: str | None
    training_regulation: str
    exam_regulation: str
    ihk_guidelines: str
    valid_from: str
    valid_until: str | None
    official_scale_min: str
    official_scale_max: str
    rules: AssessmentRules
    retention_rule_reference: str
    retention_years: int
    created_by_member_id: int
    created_at: str


class AssessmentIdentityMembershipSnapshot(TypedDict):
    committee_member_id: int
    person_id: int
    representing_side: str
    is_active: bool


class AssessmentIdentitySnapshot(TypedDict):
    """Identity-owned facts Assessment needs for model applicability and scope."""

    committee_id: int
    occupation: str
    ihk: str
    memberships: Sequence[AssessmentIdentityMembershipSnapshot]


class AssessmentPlanningCandidateSnapshot(TypedDict):
    round_candidate_id: int
    candidate_id: int
    specialization: str | None
    is_active: bool


class AssessmentPlanningDaySnapshot(TypedDict):
    day_id: int
    date: str
    revision: int
    status: str
    closure_status: str
    reopening_assessment_result_ids: Sequence[int]


class AssessmentPlanningSnapshot(TypedDict):
    """Planning-owned facts consumed by model applicability and result reads."""

    round_id: int
    committee_id: int
    half_year: int
    half_year_season: Literal["summer", "winter"]
    effective_date: str
    candidates: Sequence[AssessmentPlanningCandidateSnapshot]
    days: Sequence[AssessmentPlanningDaySnapshot]


class AssessmentProtocolParticipantSnapshot(TypedDict):
    protocol_id: int
    slot_id: int
    round_candidate_id: int
    version: int
    participant_member_ids: Sequence[int]


class RoundBindingSnapshot(TypedDict):
    id: int
    round_id: int
    model_version_id: int
    version: int
    bound_by_member_id: int
    binding_reason: str
    bound_at: str


class AssessmentSubjectSnapshot(TypedDict):
    candidate_id: int
    first_name: str
    last_name: str
    ihk_exam_number: str | None
    specialization: str | None


class IndividualAssessmentSnapshot(TypedDict):
    id: int
    component_key: str
    criterion_key: str
    assessor_member_id: int
    revision: int
    raw_points: str
    normalized_points: str
    rationale: str | None
    status: Literal["draft", "submitted", "withdrawn", "superseded"]
    previous_assessment_id: int | None
    change_reason: str | None
    submitted_at: str | None
    created_at: str


class ComponentAssessmentSnapshot(TypedDict):
    id: int
    component_key: str
    revision: int
    points: str
    rationale: str | None
    participant_member_ids: Sequence[int]
    vote: CommitteeVote
    dissent: Sequence[CommitteeDissent]
    status: Literal["current", "superseded"]
    previous_assessment_id: int | None
    determined_by_member_id: int
    determined_at: str


class ExternalResultSnapshot(TypedDict):
    id: int
    area_key: str
    revision: int
    points: str
    grade: str | None
    professional_status: str
    determining_authority: str
    source_reference: str
    status: Literal["replaced", "unconfirmed", "confirmed"]
    recorded_by_member_id: int
    recorded_at: str
    previous_external_result_id: int | None
    correction_reason: str | None
    confirmed_by_member_id: int | None
    confirmed_at: str | None


class DisclosureSnapshot(TypedDict):
    component_key: str
    disclosed_by_member_id: int
    disclosed_at: str


class CalculationSnapshot(TypedDict):
    id: int
    version: int
    total_points: str
    grade: str
    passed: bool
    path: CalculationPath
    input_fingerprint: str
    created_at: str


class DeterminationSnapshot(TypedDict):
    id: int
    revision: int
    calculation_id: int
    participant_member_ids: Sequence[int]
    vote: CommitteeVote
    dissent: Sequence[CommitteeDissent]
    status: Literal["current", "superseded"]
    previous_determination_id: int | None
    correction_id: int | None
    determined_by_member_id: int
    determined_at: str


class ResultRecordSnapshot(TypedDict):
    id: int
    determination_id: int
    committee_member_id: int
    confirmed_at: str


class CorrectionSnapshot(TypedDict):
    id: int
    determination_id: int
    reason: str
    requested_by_member_id: int
    status: Literal["open", "completed"]
    reopening_reference: str | None
    requested_at: str
    completed_at: str | None


class CommunicationSnapshot(TypedDict):
    id: int
    determination_id: int
    method: str
    responsible_member_id: int
    communicated_at: str
    external_document_status: str | None
    external_document_reference: str | None
    status: Literal["current", "obsolete"]
    created_at: str


class RetentionSnapshot(TypedDict):
    rule_reference: str
    version: int
    period_start: str | None
    retain_until: str | None
    legal_hold: bool
    hold_reason: str | None
    updated_by_member_id: int
    updated_at: str


class AssessmentResultSnapshot(TypedDict):
    """Complete materialized source state, including not-yet-disclosed values."""

    id: int
    round_id: int
    committee_id: int
    round_candidate_id: int
    version: int
    state: AssessmentStatus
    correction_open: bool
    legacy_status: str | None
    subject: AssessmentSubjectSnapshot
    model: AssessmentModelSnapshot
    binding: RoundBindingSnapshot
    participant_member_ids: Sequence[int]
    days: Sequence[AssessmentPlanningDaySnapshot]
    individual_assessments: Sequence[IndividualAssessmentSnapshot]
    component_assessments: Sequence[ComponentAssessmentSnapshot]
    external_results: Sequence[ExternalResultSnapshot]
    disclosures: Sequence[DisclosureSnapshot]
    calculations: Sequence[CalculationSnapshot]
    determinations: Sequence[DeterminationSnapshot]
    record_confirmations: Sequence[ResultRecordSnapshot]
    corrections: Sequence[CorrectionSnapshot]
    communications: Sequence[CommunicationSnapshot]
    retention: RetentionSnapshot | None
    exports: Sequence[ExportSnapshot]
    created_at: str
    updated_at: str


class AssessmentResultProjection(TypedDict):
    """Actor-specific result view; undisclosed individual data is omitted."""

    id: int
    round_id: int
    committee_id: int
    round_candidate_id: int
    version: int
    state: AssessmentStatus
    correction_open: bool
    legacy_status: str | None
    subject: AssessmentSubjectSnapshot
    model: AssessmentModelSnapshot
    binding: RoundBindingSnapshot
    participant_member_ids: Sequence[int]
    day_revisions: Mapping[int, int]
    content_mutable: bool
    visible_individual_assessments: Sequence[IndividualAssessmentSnapshot]
    component_assessments: Sequence[ComponentAssessmentSnapshot]
    external_results: Sequence[ExternalResultSnapshot]
    disclosures: Sequence[DisclosureSnapshot]
    visible_calculations: Sequence[CalculationSnapshot]
    current_calculation: CalculationSnapshot | None
    calculations_disclosed: bool
    determinations: Sequence[DeterminationSnapshot]
    record_confirmations: Sequence[ResultRecordSnapshot]
    corrections: Sequence[CorrectionSnapshot]
    communications: Sequence[CommunicationSnapshot]
    retention: RetentionSnapshot | None
    exports: Sequence[ExportSnapshot]
    actor_member_id: int | None
    actor_is_participant: bool
    actor_can_manage: bool
    created_at: str
    updated_at: str


class AssessmentDayCompletionSlotSnapshot(TypedDict):
    slot_id: int
    execution_status: str
    result: (
        AssessmentResultSnapshot
        | AssessmentLegacyResultSnapshot
        | AssessmentUnboundResultSnapshot
        | None
    )


class AssessmentLegacyResultSnapshot(TypedDict):
    """Minimal historical result projection; legacy rows have no model binding."""

    id: int
    legacy_status: str


class AssessmentUnboundResultSnapshot(TypedDict):
    """Result row lacking an Assessment model binding; day close must report it as blocked."""

    id: int
    legacy_status: None
    model: None


class AssessmentDayCompletionSnapshot(TypedDict):
    day_id: int
    committee_id: int
    slots: Sequence[AssessmentDayCompletionSlotSnapshot]


class AssessmentHumanExportResult(TypedDict):
    """The narrow renderer contract; intentionally excludes internal histories."""

    id: int
    state: AssessmentStatus
    model_version: AssessmentModelSnapshot
    candidate: AssessmentSubjectSnapshot
    external_results: Sequence[ExternalResultSnapshot]
    committee_assessments: Sequence[ComponentAssessmentSnapshot]
    current_calculation: CalculationSnapshot | None
    current_determination: DeterminationSnapshot | None
    correction_open: bool
    communications: Sequence[CommunicationSnapshot]


class AssessmentHumanExportData(TypedDict):
    export_status: Literal["draft", "determined"]
    official_document: Literal[False]
    result: AssessmentHumanExportResult


class AssessmentMachineResultProjection(TypedDict):
    """Stable JSON response fields for the legacy-compatible machine export."""

    id: int
    round_candidate_id: int
    day_revisions: Mapping[str, int]
    version: int
    state: AssessmentStatus
    correction_open: bool
    legacy_status: str | None
    candidate: Mapping[str, Any]
    binding: Mapping[str, Any]
    model_version: Mapping[str, Any]
    participants: Sequence[int]
    disclosures: Sequence[DisclosureSnapshot]
    individual_assessments: Sequence[IndividualAssessmentSnapshot]
    individual_assessment_counts: Sequence[Mapping[str, Any]]
    committee_assessments: Sequence[ComponentAssessmentSnapshot]
    external_results: Sequence[ExternalResultSnapshot]
    calculations: Sequence[CalculationSnapshot]
    current_calculation: CalculationSnapshot | None
    determinations: Sequence[DeterminationSnapshot]
    current_determination: DeterminationSnapshot | None
    corrections: Sequence[CorrectionSnapshot]
    communications: Sequence[CommunicationSnapshot]
    retention: RetentionSnapshot | None
    exports: Sequence[ExportSnapshot]
    permissions: Mapping[str, bool]
    created_at: str
    updated_at: str
    _links: Mapping[str, Any]


class AssessmentMachineExportData(TypedDict):
    export_status: Literal["draft", "determined"]
    official_document: Literal[False]
    model_version: AssessmentModelSnapshot
    candidate: AssessmentSubjectSnapshot
    result: AssessmentMachineResultProjection


class ResultExportCommand(TypedDict):
    result_id: int
    expected_result_version: int
    determination_id: int | None
    export_kind: Literal["machine", "human"]
    status: Literal["draft", "determined"]
    generated_by_member_id: int
    generated_at: str


class ExportSnapshot(TypedDict):
    id: int
    determination_id: int | None
    export_kind: Literal["machine", "human"]
    status: Literal["draft", "determined", "superseded"]
    generated_by_member_id: int
    generated_at: str


class ResultQueryPort(Protocol):
    """Read-only, Assessment-owned materialized lookups."""

    def list_models(self) -> Sequence[AssessmentModelSnapshot]: ...

    def model_by_id(self, model_version_id: int) -> AssessmentModelSnapshot | None: ...

    def result_by_id(self, result_id: int) -> AssessmentResultSnapshot | None: ...

    def results_for_round(self, round_id: int) -> Sequence[AssessmentResultSnapshot]: ...

    def result_by_slot(
        self, slot_id: int, day_id: int | None = None
    ) -> AssessmentResultSnapshot | None: ...

    def result_for_round_candidate(
        self, round_candidate_id: int
    ) -> AssessmentResultSnapshot | None: ...

    def binding_for_round(self, round_id: int) -> RoundBindingSnapshot | None: ...

    def identity_for_committee(self, committee_id: int) -> AssessmentIdentitySnapshot | None: ...

    def planning_for_round(self, round_id: int) -> AssessmentPlanningSnapshot | None: ...

    def round_has_assessment_inputs(self, round_id: int) -> bool: ...

    def protocols_for_round_candidate(
        self, round_candidate_id: int
    ) -> Sequence[AssessmentProtocolParticipantSnapshot]: ...

    def days_for_result(self, result_id: int) -> Sequence[AssessmentPlanningDaySnapshot]: ...

    def day_completion(self, day_id: int) -> AssessmentDayCompletionSnapshot | None: ...


class AssessmentRepositoryPort(Protocol):
    """Assessment-owned writes within the caller's transaction.

    Result mutations compare ``expected_result_version`` and return/raise a
    conflict when it is stale. Revisions, superseded rows, calculation state,
    and other child records for one command are persisted atomically.
    """

    def create_model(self, command: AssessmentModelCommand) -> AssessmentModelSnapshot: ...

    def bind_round(self, command: RoundBindingCommand) -> RoundBindingSnapshot | None: ...

    def ensure_round_results(self, command: EnsureRoundResultsCommand) -> None: ...

    def save_individual_assessment(self, command: IndividualAssessmentCommand) -> None: ...

    def save_calculation(self, command: CalculationCommand) -> None: ...

    def set_result_state(self, command: ResultStateCommand) -> None: ...

    def disclose_component(self, command: DisclosureCommand) -> None: ...

    def determine_component(self, command: ComponentDeterminationCommand) -> None: ...

    def record_external_result(self, command: ExternalResultCommand) -> None: ...

    def confirm_external_result(self, command: ExternalResultConfirmationCommand) -> None: ...

    def determine_result(self, command: ResultDeterminationCommand) -> None: ...

    def confirm_record(self, command: RecordConfirmationCommand) -> None: ...

    def open_correction(self, command: CorrectionCommand) -> None: ...

    def open_day_reopening_correction(
        self, command: DayReopeningCorrectionCommand
    ) -> DayReopeningCorrectionReceipt: ...

    def communicate_result(self, command: CommunicationCommand) -> None: ...

    def save_retention(self, command: RetentionCommand) -> None: ...

    def record_export(self, command: ResultExportCommand) -> ExportSnapshot: ...

    def complete_result_day_mutation(
        self,
        result_id: int,
        kind: str,
        payload: Mapping[str, Any],
        actor_member_id: int,
        reason: str | None = None,
    ) -> None: ...


class AssessmentUnitOfWork(Protocol):
    """One transaction-scoped Assessment boundary; deliberately has no commit method."""

    @property
    def queries(self) -> ResultQueryPort: ...

    @property
    def repository(self) -> AssessmentRepositoryPort: ...


class AssessmentUnitOfWorkFactory(Protocol):
    """Open a transaction; a GET may request write mode for calculation materialization.

    The context owner decides when to commit, including when a read use case
    materializes a missing calculation in the same UoW as its source snapshot.
    """

    def __call__(self, *, write: bool = False) -> AbstractContextManager[AssessmentUnitOfWork]: ...
