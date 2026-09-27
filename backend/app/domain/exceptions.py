"""Domain-level exceptions for Plan & Estimate application."""


class ClientNotFoundError(Exception):
    """Raised when a client is not found for the requesting owner."""


class ProjectNotFoundError(Exception):
    """Raised when a project is not found for the requesting owner."""


class RoomNotFoundError(Exception):
    """Raised when a room is not found within an owned project."""


class SurfaceNotFoundError(Exception):
    """Raised when a surface is not found within an owned room."""


class OpeningNotFoundError(Exception):
    """Raised when an opening is not found within an owned surface."""


class InvalidSurfaceTypeError(Exception):
    """Raised when an opening is attached to a surface that is not a WALL."""


class DeductionExceedsGrossAreaError(Exception):
    """Raised when total opening deductions exceed wall surface gross area."""


class WallGenerationDimensionsMissingError(Exception):
    """Raised when a room lacks length/width/height needed to generate canonical walls."""


class WallGenerationConflictError(Exception):
    """Raised when room walls already exist but do not match the canonical rectangle."""


class AreaSegmentNotFoundError(Exception):
    """Raised when an area segment is not found within an owned room."""


class NegativeNetAreaError(Exception):
    """Raised when a plane's net area (additions minus subtractions) would be negative."""


class InspectionNotFoundError(Exception):
    """Raised when an inspection is not found within an owned room."""


class ChecklistTemplateNotFoundError(Exception):
    """Raised when a checklist template is not found by id or code."""


class ChecklistTemplateMissingError(Exception):
    """Raised when no template exists for a requested substrate."""


class InvalidInspectionTargetError(Exception):
    """Raised when an inspection targets both a surface and a plane simultaneously."""


class QualityScaleMismatchError(Exception):
    """Raised when a quality target does not belong to the substrate's scale (S/Q)."""


class SubstrateTemplateMismatchError(Exception):
    """Raised when a chosen template does not serve the inspection substrate."""


class InspectionAnswerValidationError(Exception):
    """Raised when an answer payload does not match the question's answer type."""


class InspectionStateError(Exception):
    """Raised when an operation is invalid for the current inspection status."""


class InspectionNotCompletedError(Exception):
    """Raised when risk evaluation is requested for a non-COMPLETED inspection."""


class RiskNotFoundError(Exception):
    """Raised when a risk is not found within an owned room."""


class CommunicationNotFoundError(Exception):
    """Raised when a communication application is not found within an owned room."""


class PriceItemNotFoundError(Exception):
    """Raised when a price item is not found for the requesting owner."""


class MarketReferenceNotFoundError(Exception):
    """Raised when a market reference is not found for the requesting owner."""


class PriceBookValidationError(Exception):
    """Raised when price book input violates a Stage 9 domain rule."""


class SurfaceWorkPlanNotFoundError(Exception):
    """Raised when a surface has no work plan, or the plan is not accessible."""


class SurfaceWorkPlanValidationError(Exception):
    """Raised when work plan input violates a Stage 10 domain rule."""


class CanonicalPlaneConflictError(Exception):
    """Raised when a room would hold more than one active FLOOR/CEILING surface."""


class CanonicalPlaneMissingError(Exception):
    """Raised when a room has no canonical FLOOR/CEILING surface to associate."""


class AreaSegmentSurfaceMismatchError(Exception):
    """Raised when an area segment's surface disagrees with its plane or room."""


class InvalidRevealConfigError(Exception):
    """Raised when reveal configuration is invalid (wrong type or missing depth)."""


class EstimateNotFoundError(Exception):
    """Raised when an estimate is not found for the requesting owner or project."""


class EstimateDraftExistsError(Exception):
    """Raised when POST /generate is called but an active DRAFT already exists."""


class EstimateValidationError(Exception):
    """Raised when estimate input violates a domain rule (e.g. NULL prices block FINAL)."""


class EstimateStateError(Exception):
    """Raised when an operation is invalid for the current estimate status."""


class OpeningRevealWorkNotFoundError(Exception):
    """Raised when an OpeningRevealPlannedWork row is not found."""


class OpeningRevealWorkValidationError(Exception):
    """Raised when reveal work input violates a domain rule (wrong category, disabled reveal)."""


class WorkRecommendationNotFoundError(Exception):
    """Raised when a work recommendation is not found within an owned project."""


class WorkRecommendationStateError(Exception):
    """Raised when an operation is invalid for the current recommendation status."""


class WorkRecommendationTargetError(Exception):
    """Raised when a recommendation's target is not actionable (e.g. ROOM advisory-only)."""


class CoefficientGroupNotFoundError(Exception):
    """Raised when a price coefficient group is not found within an owned catalog."""


class CoefficientOptionNotFoundError(Exception):
    """Raised when a price coefficient option is not found within an owned group."""


class PriceCoefficientValidationError(Exception):
    """Raised when coefficient catalog input violates a domain rule."""


class SurfaceWorkPlanOccurrenceConflictError(Exception):
    """Raised when a Work Plan save names an occurrence_key that is not a
    current occurrence of that plan (stale draft, foreign or invented key).
    Deliberately one error for all three cases: nothing about other plans'
    occurrences is disclosed (Stage 13 D13)."""


class TemplateApplicationConflictError(Exception):
    """Raised when a template-application intent reuses an application_id
    that is already recorded for a different plan or with different content
    (Stage 13C). Same response whatever the cause: nothing is disclosed."""


class TemplateApplicationStaleError(Exception):
    """Raised (409) when an apply-template request no longer matches current
    state: archived template, changed template steps (expected_step_ids) or
    a changed plan composition for REPLACE (expected_occurrence_keys)."""


class WorkflowTemplateNotFoundError(Exception):
    """Raised when a workflow template does not exist or is not owned."""


class WorkflowTemplateValidationError(Exception):
    """Raised when workflow template input violates a Stage 13 domain rule."""


class WorkflowTemplateStaleError(Exception):
    """Raised (409) when a step replacement's expected_step_ids no longer match
    the template's current ordered step ids (Stage 13F.2, D-F2)."""


class WorkExecutionConflictError(Exception):
    """Raised (409) when an execution transition no longer matches the
    occurrence's current execution state (Stage 13H, D-H17/D-H18): the
    caller's expected_status is stale, or the requested transition is not
    allowed from the current status. Carries the current status."""

    def __init__(self, message: str, current_status: object) -> None:
        super().__init__(message)
        self.current_status = current_status


class WorkExecutionValidationError(Exception):
    """Raised (422) when an execution transition is refused by a domain rule,
    e.g. the surface, room or project is archived (Stage 13H, D-H19)."""


class ExecutionDetachConfirmationRequiredError(Exception):
    """Raised (409) when a destructive WorkPlan mutation would detach
    IN_PROGRESS/COMPLETED execution history from the current plan and the
    request's `confirm_execution_detach_keys` is not exactly that set
    (Stage 13H.4, D-H7). `affected` lists the CURRENT protected records of
    the caller's own target plan(s). Distinct from WorkExecutionConflictError
    (an execution status transition conflict). Nothing is deleted: detached
    records stay stored as history."""

    def __init__(self, message: str, affected: list) -> None:
        super().__init__(message)
        self.affected = affected


class WorkExecutionSourceChangedError(Exception):
    """Raised (409) when a bulk execution apply's `expected_source` (the exact
    ordered snapshot of the source wall's current occurrence keys and
    statuses) no longer matches the locked source plan (Stage 13H.5B,
    BULK-H7). Carries the current snapshot of the caller's own source wall."""

    def __init__(self, message: str, current_source: list) -> None:
        super().__init__(message)
        self.current_source = current_source
