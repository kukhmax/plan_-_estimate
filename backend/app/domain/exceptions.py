"""Domain-level exceptions for Plan & Estimate application."""


class ClientNotFoundError(Exception):
    """Raised when a client is not found for the requesting owner."""


class ProjectNotFoundError(Exception):
    """Raised when a project is not found for the requesting owner."""


class RoomNotFoundError(Exception):
    """Raised when a room is not found within an owned project."""
