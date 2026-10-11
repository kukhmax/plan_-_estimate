"""Calendar and reminders (Stage 18): working days, public holidays and the events derived from the data of an object.

Pure functions only (no database, no network, no clock): the same input gives the same output, which is what makes a reminder
reproducible. Tables, reconciliation and delivery come in the later sub-stages (18C, 18D).
"""
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = ZoneInfo("Europe/Warsaw")  # the contractor works in Poland; the database keeps UTC (Q15)
