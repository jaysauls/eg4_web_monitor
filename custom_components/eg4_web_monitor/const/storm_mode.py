"""Storm mode constants for the EG4 Web Monitor integration.

This module contains constants for the storm mode feature, which overrides
the normal AC charge schedule to force near-24h grid charging during
severe weather events.

Time parameter names follow the EG4 cloud API conventions:
- Read names (from remoteRead): HOLD_AC_FIRST_START_HOUR, etc.
- Write names (for writeTime): HOLD_AC_CHARGE_START_TIME, etc.
"""

from __future__ import annotations

# =============================================================================
# Service
# =============================================================================

SERVICE_SET_STORM_MODE = "set_storm_mode"

# =============================================================================
# Config Entry Storage Keys
# =============================================================================

CONF_STORM_MODE = "storm_mode"

# =============================================================================
# AC Charge Schedule — Read Parameter Names (from remoteRead response)
# =============================================================================
# These are the keys returned by the cloud API remoteRead endpoint.
# Each time slot has separate hour and minute fields.

# Time slot 1
READ_AC_CHARGE_START_HOUR = "HOLD_AC_FIRST_START_HOUR"
READ_AC_CHARGE_START_MINUTE = "HOLD_AC_FIRST_START_MINUTE"
READ_AC_CHARGE_END_HOUR = "HOLD_AC_FIRST_END_HOUR"
READ_AC_CHARGE_END_MINUTE = "HOLD_AC_FIRST_END_MINUTE"

# Time slot 2
READ_AC_CHARGE_START_HOUR_1 = "HOLD_AC_FIRST_START_HOUR_1"
READ_AC_CHARGE_START_MINUTE_1 = "HOLD_AC_FIRST_START_MINUTE_1"
READ_AC_CHARGE_END_HOUR_1 = "HOLD_AC_FIRST_END_HOUR_1"
READ_AC_CHARGE_END_MINUTE_1 = "HOLD_AC_FIRST_END_MINUTE_1"

# Time slot 3
READ_AC_CHARGE_START_HOUR_2 = "HOLD_AC_FIRST_START_HOUR_2"
READ_AC_CHARGE_START_MINUTE_2 = "HOLD_AC_FIRST_START_MINUTE_2"
READ_AC_CHARGE_END_HOUR_2 = "HOLD_AC_FIRST_END_HOUR_2"
READ_AC_CHARGE_END_MINUTE_2 = "HOLD_AC_FIRST_END_MINUTE_2"

# =============================================================================
# AC Charge Schedule — Write Parameter Names (for writeTime endpoint)
# =============================================================================
# These are the timeParam values accepted by the writeTime endpoint.
# Each call writes both hour and minute for one time boundary.

# Time slot 1
WRITE_AC_CHARGE_START_TIME = "HOLD_AC_CHARGE_START_TIME"
WRITE_AC_CHARGE_END_TIME = "HOLD_AC_CHARGE_END_TIME"

# Time slot 2
WRITE_AC_CHARGE_START_TIME_1 = "HOLD_AC_CHARGE_START_TIME_1"
WRITE_AC_CHARGE_END_TIME_1 = "HOLD_AC_CHARGE_END_TIME_1"

# Time slot 3
WRITE_AC_CHARGE_START_TIME_2 = "HOLD_AC_CHARGE_START_TIME_2"
WRITE_AC_CHARGE_END_TIME_2 = "HOLD_AC_CHARGE_END_TIME_2"

# =============================================================================
# Read-to-Write Parameter Mapping
# =============================================================================
# Maps each time slot boundary from its read parameter pair (hour, minute)
# to the corresponding writeTime parameter name.

AC_CHARGE_TIME_SLOTS: list[dict[str, str]] = [
    {
        "read_start_hour": READ_AC_CHARGE_START_HOUR,
        "read_start_minute": READ_AC_CHARGE_START_MINUTE,
        "read_end_hour": READ_AC_CHARGE_END_HOUR,
        "read_end_minute": READ_AC_CHARGE_END_MINUTE,
        "write_start": WRITE_AC_CHARGE_START_TIME,
        "write_end": WRITE_AC_CHARGE_END_TIME,
    },
    {
        "read_start_hour": READ_AC_CHARGE_START_HOUR_1,
        "read_start_minute": READ_AC_CHARGE_START_MINUTE_1,
        "read_end_hour": READ_AC_CHARGE_END_HOUR_1,
        "read_end_minute": READ_AC_CHARGE_END_MINUTE_1,
        "write_start": WRITE_AC_CHARGE_START_TIME_1,
        "write_end": WRITE_AC_CHARGE_END_TIME_1,
    },
    {
        "read_start_hour": READ_AC_CHARGE_START_HOUR_2,
        "read_start_minute": READ_AC_CHARGE_START_MINUTE_2,
        "read_end_hour": READ_AC_CHARGE_END_HOUR_2,
        "read_end_minute": READ_AC_CHARGE_END_MINUTE_2,
        "write_start": WRITE_AC_CHARGE_START_TIME_2,
        "write_end": WRITE_AC_CHARGE_END_TIME_2,
    },
]

# =============================================================================
# Storm Mode Schedule Values
# =============================================================================
# When storm mode is active, T1 covers 00:00–23:59 and T2/T3 are cleared.

STORM_SCHEDULE_START_HOUR = 0
STORM_SCHEDULE_START_MINUTE = 0
STORM_SCHEDULE_END_HOUR = 23
STORM_SCHEDULE_END_MINUTE = 59

CLEAR_HOUR = 0
CLEAR_MINUTE = 0

# =============================================================================
# Storm Mode SOC Defaults
# =============================================================================

STORM_SOC_LIMIT_DEFAULT = 100
