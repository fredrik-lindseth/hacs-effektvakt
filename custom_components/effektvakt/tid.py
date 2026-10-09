"""Tidslinjen for varighet og rekkefølge; lokale datoer eies av regnskapet."""

from datetime import UTC, datetime, timedelta


def tidslinje(tid: datetime) -> datetime:
    """UTC for sonebevisst tid, uendret for eldre naive tidsstempler."""
    return tid if tid.tzinfo is None else tid.astimezone(UTC)


def legg_til_time(tid: datetime) -> datetime:
    """Neste faktiske time, også når lokal klokke hopper eller gjentas."""
    neste = tidslinje(tid) + timedelta(hours=1)
    return neste if tid.tzinfo is None else neste.astimezone(tid.tzinfo)
