"""Custom exceptions used across the add-on."""


class BeeminderError(Exception):
    """Base error for Beeminder client failures."""


class BeeminderAuthError(BeeminderError):
    """Raised when Beeminder authentication fails."""


class BeeminderRequestError(BeeminderError):
    """Raised for non-auth request failures."""

