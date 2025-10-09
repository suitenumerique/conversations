"""Exceptions for activation code handling."""


class InvalidCodeError(ValueError):
    """Raised when an activation code is invalid or cannot be used."""


class UserAlreadyActivatedError(ValueError):
    """Raised when a user tries to activate but is already activated."""
