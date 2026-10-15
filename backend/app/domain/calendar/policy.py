"""When a reminder is sent, when it is late, when it is given up (Stage 18D): the rules of the delivery loop as pure functions."""
from datetime import datetime, timedelta

LATE_AFTER = timedelta(minutes=15)  # later than this after its time a message carries the mark "late" (Q9)
MISSED_AFTER = timedelta(hours=24)  # later than this it is not sent any more: the calendar shows it as missed (Q9)
STALE_SENDING = timedelta(minutes=5)  # a reminder taken by the loop and not finished this long ago goes back to the queue
MAX_ATTEMPTS = 5
BACKOFF = (timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=15), timedelta(minutes=15))  # after the 1st, 2nd, 3rd, 4th failure

ON_TIME, LATE, MISSED = "ON_TIME", "LATE", "MISSED"


def lateness(send_at: datetime, now: datetime) -> str:
    delay = now - send_at
    if delay > MISSED_AFTER:
        return MISSED
    return LATE if delay > LATE_AFTER else ON_TIME


def retry_delay(attempts: int, retry_after_seconds: int | None = None) -> timedelta | None:
    """The wait before the next attempt after `attempts` failed ones; None when the attempts are used up.

    A 429 answer says how long to wait: that wait is used when it is longer than the backoff, and it does not count as a failure of the
    message itself beyond the attempt it consumed.
    """
    if attempts >= MAX_ATTEMPTS:
        return None
    base = BACKOFF[min(attempts, len(BACKOFF)) - 1] if attempts >= 1 else BACKOFF[0]
    return max(base, timedelta(seconds=retry_after_seconds)) if retry_after_seconds else base
