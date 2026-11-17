"""Error types. Each carries the process exit code the CLI should use."""

from __future__ import annotations


class DevkitError(Exception):
    """Base class. The message is safe to show to the user."""

    exit_code = 1


class UsageError(DevkitError):
    """Rejected input: bad name, answer, option or profile."""

    exit_code = 2


class OperationError(DevkitError):
    """A valid request could not be completed (destination exists, generation failed...)."""

    exit_code = 1


class TemplateUnavailableError(OperationError):
    """The template source could not be reached or has no usable release."""
