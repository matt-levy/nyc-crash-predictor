import os
import logging
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any

import httpx

from app.models.risk import CrashRecord

logger = logging.getLogger(__name__)

DATASET_URL = "https://data.cityofnewyork.us/resource/h9gi-nx95.json"
SELECT_FIELDS = ",".join(
    [
        "collision_id", "crash_date", "crash_time", "latitude", "longitude",
        "number_of_persons_injured", "number_of_persons_killed",
        "number_of_pedestrians_injured", "number_of_cyclist_injured",
        "number_of_motorist_injured", "contributing_factor_vehicle_1",
        "contributing_factor_vehicle_2", "contributing_factor_vehicle_3",
        "contributing_factor_vehicle_4", "contributing_factor_vehicle_5",
    ]
)


class NYCOpenDataError(Exception):
    pass


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError) as exc:
        raise NYCOpenDataError("NYC Open Data returned a malformed numeric field") from exc


def _normalize(row: dict[str, Any]) -> CrashRecord:
    try:
        date_part = str(row["crash_date"]).split("T", 1)[0]
        timestamp = datetime.strptime(
            f"{date_part} {row.get('crash_time', '00:00')}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=timezone.utc)
        factors = []
        for index in range(1, 6):
            factor = row.get(f"contributing_factor_vehicle_{index}")
            if factor and factor.lower() not in {"unspecified", "unknown"}:
                factors.append(factor)
        return CrashRecord(
            collision_id=str(row["collision_id"]),
            timestamp=timestamp,
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
            persons_injured=_integer(row.get("number_of_persons_injured")),
            persons_killed=_integer(row.get("number_of_persons_killed")),
            pedestrians_injured=_integer(row.get("number_of_pedestrians_injured")),
            cyclists_injured=_integer(row.get("number_of_cyclist_injured")),
            motorists_injured=_integer(row.get("number_of_motorist_injured")),
            contributing_factors=factors,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise NYCOpenDataError("NYC Open Data returned a malformed crash record") from exc


async def get_nearby_crashes(
    latitude: float, longitude: float, radius_meters: int, days: int
) -> list[CrashRecord]:
    # Socrata's within_circle operates on the dataset's actual `location` point field.
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    where = (
        f"within_circle(location, {latitude}, {longitude}, {radius_meters}) "
        f"AND crash_date >= '{cutoff:%Y-%m-%dT00:00:00.000}'"
    )
    headers = {}
    if token := os.getenv("NYC_OPEN_DATA_APP_TOKEN"):
        headers["X-App-Token"] = token
    params = {"$select": SELECT_FIELDS, "$where": where, "$order": "crash_date DESC", "$limit": 50000}
    started = perf_counter()
    logger.info(
        "nyc_crash_query_started latitude=%.6f longitude=%.6f radius_meters=%d days=%d",
        latitude, longitude, radius_meters, days,
    )
    try:
        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            response = await client.get(DATASET_URL, params=params)
            response.raise_for_status()
            payload = response.json()
    except httpx.TimeoutException as exc:
        raise NYCOpenDataError("NYC Open Data request timed out") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise NYCOpenDataError("NYC Open Data request failed") from exc
    if not isinstance(payload, list):
        raise NYCOpenDataError("NYC Open Data returned an unexpected response")
    records = [_normalize(row) for row in payload]
    logger.info(
        "nyc_crash_query_completed duration_seconds=%.3f record_count=%d",
        perf_counter() - started, len(records),
    )
    return records
