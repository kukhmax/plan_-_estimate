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
