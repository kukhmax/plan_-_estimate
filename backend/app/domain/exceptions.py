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
