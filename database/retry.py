"""Bounded retry for transient Supabase/PostgREST calls.

A backfill issues thousands of HTTP requests; a few of them will stall or have
their connection dropped no matter how generous the timeout is. Every call is
either an upsert on a primary key or a read, so replaying one is safe.

Application errors - a missing table, a bad payload, a constraint violation -
are raised immediately. Retrying those would only turn a clear failure into a
slow one.
"""

import time

import httpx

try:  # postgrest is always installed with supabase; degrade gracefully anyway
    from postgrest.exceptions import APIError
except ImportError:  # pragma: no cover
    APIError = None

DEFAULT_ATTEMPTS = 5

BASE_DELAY_SECONDS = 1.0

MAX_DELAY_SECONDS = 30.0

# Transport-level failures: timeouts, dropped connections, protocol errors.
TRANSIENT_EXCEPTIONS = (httpx.TransportError,)

# PostgREST/Supabase statuses worth replaying (overload, gateway, timeout).
TRANSIENT_STATUS_CODES = {"408", "429", "500", "502", "503", "504"}


def backoff_delay(attempt):
    """Exponential backoff: 1s, 2s, 4s, 8s, capped."""
    return min(BASE_DELAY_SECONDS * (2 ** (attempt - 1)), MAX_DELAY_SECONDS)


def is_transient(error):
    """True when replaying the same call could reasonably succeed."""
    if isinstance(error, TRANSIENT_EXCEPTIONS):
        # An unsupported protocol will never fix itself.
        return not isinstance(error, httpx.UnsupportedProtocol)

    if APIError is not None and isinstance(error, APIError):
        return str(getattr(error, "code", "")) in TRANSIENT_STATUS_CODES

    return False


def describe(error):
    """Short, log-friendly description of a failure."""
    detail = getattr(error, "message", None) or str(error) or "no detail"

    return f"{type(error).__name__}: {detail}"


def run_with_retry(
    operation,
    description,
    attempts=DEFAULT_ATTEMPTS,
    sleep=None,
):
    """Call `operation()`, retrying transient failures with backoff.

    `description` names what is being retried (table and batch) so the log
    says which call is struggling.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    # Resolved per call so tests can patch time.sleep.
    sleep = sleep or time.sleep

    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as error:
            if not is_transient(error):
                raise

            if attempt == attempts:
                print(
                    f"{description}: giving up after {attempts} attempts "
                    f"({describe(error)})"
                )
                raise

            delay = backoff_delay(attempt)

            print(
                f"{description}: {describe(error)}; "
                f"retrying in {delay:.0f}s "
                f"(attempt {attempt + 1}/{attempts})"
            )

            sleep(delay)
