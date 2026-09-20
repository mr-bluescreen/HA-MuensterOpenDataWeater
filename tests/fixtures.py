"""Representative WFS response fixtures shared across the test suite.

Field-name variants exercise the parser's alias handling; they are not
claims about a single canonical upstream response (see docs/research.md
for the outbound-access limitation that prevented live capture).
"""

from __future__ import annotations

STATION_CSV = (
    "device_id;device_name;latitude;longitude\n"
    "50618;Aasee;51,9403;7,6046\n"
    "50619;Zentrum;51,9625;7,6256\n"
    "50620;Kinderhaus;51,9863;7,6132\n"
)

LATEST_JSON = [
    {
        "device_id": "50618",
        "timestamp": "2026-09-07T09:30:00+02:00",
        "temperature": 21.3,
        "humidity": 58.0,
        "heat_notification": "keine",
        "temperature_quality": 0,
        "humidity_quality": 0,
    },
    {
        "device_id": "50619",
        "timestamp": "2026-09-07T09:30:00+02:00",
        "temperature": 22.1,
        "humidity": 55.0,
        "heat_notification": "keine",
        "temperature_quality": 0,
        "humidity_quality": 0,
    },
]
