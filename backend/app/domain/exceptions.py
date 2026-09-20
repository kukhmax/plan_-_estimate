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
