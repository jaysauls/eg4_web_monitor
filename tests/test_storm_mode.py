"""Tests for storm mode feature in EG4 Web Monitor integration."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.eg4_web_monitor.const import (
    CONF_STORM_MODE,
)
from custom_components.eg4_web_monitor.const.storm_mode import (
    CLEAR_HOUR,
    CLEAR_MINUTE,
    STORM_SCHEDULE_END_HOUR,
    STORM_SCHEDULE_END_MINUTE,
    STORM_SCHEDULE_START_HOUR,
    STORM_SCHEDULE_START_MINUTE,
    WRITE_AC_CHARGE_END_TIME,
    WRITE_AC_CHARGE_START_TIME,
    WRITE_AC_CHARGE_START_TIME_1,
)
from custom_components.eg4_web_monitor.services import (
    _read_schedule_baseline,
    _resolve_control_serial,
    async_set_storm_mode,
    is_storm_mode_active,
)
from custom_components.eg4_web_monitor.switch import EG4StormModeSwitch


# ── Helpers ──────────────────────────────────────────────────────────

SERIAL = "1234567890"
MASTER_SERIAL = "9876543210"


def _mock_coordinator(
    *,
    has_http: bool = True,
    serial: str = SERIAL,
    device_type: str = "inverter",
    parameters: dict | None = None,
    storm_mode_data: dict | None = None,
) -> MagicMock:
    """Build a mock coordinator for storm mode tests."""
    coordinator = MagicMock()
    coordinator.has_http_api = MagicMock(return_value=has_http)
    coordinator.is_local_only = MagicMock(return_value=not has_http)
    coordinator.last_update_success = True
    coordinator.plant_id = "plant_123"
    coordinator.async_add_listener = MagicMock(return_value=lambda: None)
    coordinator.async_request_refresh = AsyncMock()
    coordinator.async_refresh = AsyncMock()
    coordinator.write_time_parameter = AsyncMock(return_value=True)

    # Build coordinator.data
    data: dict = {
        "devices": {
            serial: {
                "type": device_type,
                "model": "FlexBOSS21" if device_type == "inverter" else "GridBOSS",
            },
        },
        "parameters": {serial: parameters or {}},
    }
    coordinator.data = data

    # Mock inverter object
    mock_inverter = MagicMock()
    mock_inverter.enable_ac_charge_mode = AsyncMock(return_value=True)
    mock_inverter.disable_ac_charge_mode = AsyncMock(return_value=True)
    mock_inverter.set_ac_charge_soc_limit = AsyncMock(return_value=True)
    coordinator.get_inverter_object = MagicMock(return_value=mock_inverter)

    # Config entry
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.state = ConfigEntryState.LOADED
    entry.options = {}
    if storm_mode_data is not None:
        entry.options = {CONF_STORM_MODE: storm_mode_data}
    entry.runtime_data = coordinator
    coordinator.entry = entry

    return coordinator


def _mock_hass(coordinator: MagicMock) -> MagicMock:
    """Build a mock HomeAssistant object with the coordinator registered."""
    hass = MagicMock()
    entry = coordinator.entry
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    hass.config_entries.async_get_entry = MagicMock(return_value=entry)
    hass.config_entries.async_update_entry = MagicMock()
    return hass


def _make_call(serial: str = SERIAL, enable: bool = True, soc_limit: int = 100):
    """Build a mock ServiceCall."""
    call = MagicMock()
    call.data = {"serial": serial, "enable": enable, "soc_limit": soc_limit}
    return call


def _sample_parameters() -> dict:
    """Return parameter dict with a typical AC charge schedule."""
    return {
        "FUNC_AC_CHARGE": True,
        "HOLD_AC_CHARGE_SOC_LIMIT": 85,
        "HOLD_AC_FIRST_START_HOUR": "00",
        "HOLD_AC_FIRST_START_MINUTE": "00",
        "HOLD_AC_FIRST_END_HOUR": "06",
        "HOLD_AC_FIRST_END_MINUTE": "59",
        "HOLD_AC_FIRST_START_HOUR_1": "23",
        "HOLD_AC_FIRST_START_MINUTE_1": "01",
        "HOLD_AC_FIRST_END_HOUR_1": "00",
        "HOLD_AC_FIRST_END_MINUTE_1": "00",
        "HOLD_AC_FIRST_START_HOUR_2": "00",
        "HOLD_AC_FIRST_START_MINUTE_2": "00",
        "HOLD_AC_FIRST_END_HOUR_2": "00",
        "HOLD_AC_FIRST_END_MINUTE_2": "00",
    }


# ── _read_schedule_baseline tests ────────────────────────────────────


class TestReadScheduleBaseline:
    """Test baseline snapshot reading from parameter data."""

    def test_reads_three_slots(self):
        """All three time slots are captured."""
        params = _sample_parameters()
        slots = _read_schedule_baseline(params)
        assert len(slots) == 3

    def test_slot_values_correct(self):
        """Parsed hour/minute values match the parameter data."""
        params = _sample_parameters()
        slots = _read_schedule_baseline(params)
        assert slots[0] == {
            "start_hour": 0,
            "start_minute": 0,
            "end_hour": 6,
            "end_minute": 59,
        }
        assert slots[1] == {
            "start_hour": 23,
            "start_minute": 1,
            "end_hour": 0,
            "end_minute": 0,
        }

    def test_missing_params_default_to_zero(self):
        """Missing parameters default to 0."""
        slots = _read_schedule_baseline({})
        for slot in slots:
            assert slot == {
                "start_hour": 0,
                "start_minute": 0,
                "end_hour": 0,
                "end_minute": 0,
            }


# ── _resolve_control_serial tests ────────────────────────────────────


class TestResolveControlSerial:
    """Test serial routing for GridBOSS vs inverter."""

    def test_inverter_uses_own_serial(self):
        """Standard inverters use their own serial."""
        coordinator = _mock_coordinator()
        result = _resolve_control_serial(coordinator, SERIAL)
        assert result == SERIAL

    def test_gridboss_routes_to_master(self):
        """GridBOSS routes to master inverter serial."""
        coordinator = _mock_coordinator(device_type="gridboss")
        coordinator.data["devices"][SERIAL]["master_inverter_sn"] = MASTER_SERIAL
        result = _resolve_control_serial(coordinator, SERIAL)
        assert result == MASTER_SERIAL

    def test_gridboss_without_master_uses_own_serial(self):
        """GridBOSS without master mapping falls back to own serial."""
        coordinator = _mock_coordinator(device_type="gridboss")
        result = _resolve_control_serial(coordinator, SERIAL)
        assert result == SERIAL

    def test_no_data_returns_serial(self):
        """Missing coordinator data returns the serial unchanged."""
        coordinator = _mock_coordinator()
        coordinator.data = None
        result = _resolve_control_serial(coordinator, SERIAL)
        assert result == SERIAL


# ── is_storm_mode_active tests ───────────────────────────────────────


class TestIsStormModeActive:
    """Test storm mode active state detection."""

    def test_inactive_when_no_data(self):
        """No storm mode data means inactive."""
        coordinator = _mock_coordinator()
        assert is_storm_mode_active(coordinator.entry, SERIAL) is False

    def test_active_when_flag_set(self):
        """Storm mode is active when flag is set."""
        coordinator = _mock_coordinator(
            storm_mode_data={SERIAL: {"active": True}}
        )
        assert is_storm_mode_active(coordinator.entry, SERIAL) is True

    def test_inactive_for_different_serial(self):
        """Storm mode for one serial doesn't affect another."""
        coordinator = _mock_coordinator(
            storm_mode_data={"other_serial": {"active": True}}
        )
        assert is_storm_mode_active(coordinator.entry, SERIAL) is False


# ── Enable storm mode tests ──────────────────────────────────────────


class TestEnableStormMode:
    """Test storm mode enable flow."""

    @pytest.mark.asyncio
    async def test_enable_saves_baseline(self):
        """Enable saves the current schedule to config entry."""
        coordinator = _mock_coordinator(parameters=_sample_parameters())
        hass = _mock_hass(coordinator)
        call = _make_call(enable=True)

        await async_set_storm_mode(hass, call)

        # Verify config entry was updated with baseline
        hass.config_entries.async_update_entry.assert_called()
        update_args = hass.config_entries.async_update_entry.call_args
        options = update_args.kwargs.get("options", update_args[1].get("options", {}))
        storm_data = options[CONF_STORM_MODE]
        assert SERIAL in storm_data
        assert storm_data[SERIAL]["active"] is True
        assert storm_data[SERIAL]["ac_charge_enabled"] is True
        assert storm_data[SERIAL]["soc_limit"] == 85
        assert len(storm_data[SERIAL]["time_slots"]) == 3

    @pytest.mark.asyncio
    async def test_enable_writes_storm_schedule(self):
        """Enable writes the storm schedule via writeTime."""
        coordinator = _mock_coordinator(parameters=_sample_parameters())
        hass = _mock_hass(coordinator)
        call = _make_call(enable=True)

        await async_set_storm_mode(hass, call)

        # Should have written T1 start + T1 end + T2 start/end + T3 start/end = 6 calls
        write_calls = coordinator.write_time_parameter.call_args_list
        assert len(write_calls) == 6

        # First call: T1 start = 00:00
        assert write_calls[0].args == (
            SERIAL,
            WRITE_AC_CHARGE_START_TIME,
            STORM_SCHEDULE_START_HOUR,
            STORM_SCHEDULE_START_MINUTE,
        )
        # Second call: T1 end = 23:59
        assert write_calls[1].args == (
            SERIAL,
            WRITE_AC_CHARGE_END_TIME,
            STORM_SCHEDULE_END_HOUR,
            STORM_SCHEDULE_END_MINUTE,
        )
        # T2/T3 should be cleared
        assert write_calls[2].args == (
            SERIAL,
            WRITE_AC_CHARGE_START_TIME_1,
            CLEAR_HOUR,
            CLEAR_MINUTE,
        )

    @pytest.mark.asyncio
    async def test_enable_activates_ac_charge_if_disabled(self):
        """Enable turns on FUNC_AC_CHARGE if it was off."""
        params = _sample_parameters()
        params["FUNC_AC_CHARGE"] = False
        coordinator = _mock_coordinator(parameters=params)
        hass = _mock_hass(coordinator)
        call = _make_call(enable=True)

        await async_set_storm_mode(hass, call)

        inverter = coordinator.get_inverter_object(SERIAL)
        inverter.enable_ac_charge_mode.assert_called_once()

    @pytest.mark.asyncio
    async def test_enable_skips_ac_charge_if_already_on(self):
        """Enable skips FUNC_AC_CHARGE toggle if already enabled."""
        coordinator = _mock_coordinator(parameters=_sample_parameters())
        hass = _mock_hass(coordinator)
        call = _make_call(enable=True)

        await async_set_storm_mode(hass, call)

        inverter = coordinator.get_inverter_object(SERIAL)
        inverter.enable_ac_charge_mode.assert_not_called()

    @pytest.mark.asyncio
    async def test_enable_sets_soc_limit(self):
        """Enable sets the SOC limit to the requested value."""
        coordinator = _mock_coordinator(parameters=_sample_parameters())
        hass = _mock_hass(coordinator)
        call = _make_call(enable=True, soc_limit=100)

        await async_set_storm_mode(hass, call)

        inverter = coordinator.get_inverter_object(SERIAL)
        inverter.set_ac_charge_soc_limit.assert_called_once_with(soc_percent=100)

    @pytest.mark.asyncio
    async def test_enable_refreshes_coordinator(self):
        """Enable triggers a coordinator refresh."""
        coordinator = _mock_coordinator(parameters=_sample_parameters())
        hass = _mock_hass(coordinator)
        call = _make_call(enable=True)

        await async_set_storm_mode(hass, call)

        coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_enable_requires_http(self):
        """Enable raises when no cloud API is available."""
        coordinator = _mock_coordinator(has_http=False, parameters=_sample_parameters())
        hass = _mock_hass(coordinator)
        call = _make_call(enable=True)

        with pytest.raises(HomeAssistantError, match="cloud API"):
            await async_set_storm_mode(hass, call)


# ── Disable storm mode tests ─────────────────────────────────────────


class TestDisableStormMode:
    """Test storm mode disable flow."""

    def _baseline_data(self) -> dict:
        return {
            SERIAL: {
                "active": True,
                "ac_charge_enabled": True,
                "soc_limit": 85,
                "time_slots": [
                    {"start_hour": 0, "start_minute": 0, "end_hour": 6, "end_minute": 59},
                    {"start_hour": 23, "start_minute": 1, "end_hour": 0, "end_minute": 0},
                    {"start_hour": 0, "start_minute": 0, "end_hour": 0, "end_minute": 0},
                ],
            }
        }

    @pytest.mark.asyncio
    async def test_disable_restores_time_slots(self):
        """Disable restores saved time slots via writeTime."""
        coordinator = _mock_coordinator(storm_mode_data=self._baseline_data())
        hass = _mock_hass(coordinator)
        call = _make_call(enable=False)

        await async_set_storm_mode(hass, call)

        write_calls = coordinator.write_time_parameter.call_args_list
        assert len(write_calls) == 6

        # T1 start restored to 00:00
        assert write_calls[0].args == (SERIAL, WRITE_AC_CHARGE_START_TIME, 0, 0)
        # T1 end restored to 06:59
        assert write_calls[1].args == (SERIAL, WRITE_AC_CHARGE_END_TIME, 6, 59)
        # T2 start restored to 23:01
        assert write_calls[2].args == (SERIAL, WRITE_AC_CHARGE_START_TIME_1, 23, 1)

    @pytest.mark.asyncio
    async def test_disable_restores_soc_limit(self):
        """Disable restores the saved SOC limit."""
        coordinator = _mock_coordinator(storm_mode_data=self._baseline_data())
        hass = _mock_hass(coordinator)
        call = _make_call(enable=False)

        await async_set_storm_mode(hass, call)

        inverter = coordinator.get_inverter_object(SERIAL)
        inverter.set_ac_charge_soc_limit.assert_called_once_with(soc_percent=85)

    @pytest.mark.asyncio
    async def test_disable_skips_ac_charge_toggle_if_was_enabled(self):
        """Disable doesn't turn off AC charge if baseline had it enabled."""
        coordinator = _mock_coordinator(storm_mode_data=self._baseline_data())
        hass = _mock_hass(coordinator)
        call = _make_call(enable=False)

        await async_set_storm_mode(hass, call)

        inverter = coordinator.get_inverter_object(SERIAL)
        inverter.disable_ac_charge_mode.assert_not_called()

    @pytest.mark.asyncio
    async def test_disable_turns_off_ac_charge_if_was_disabled(self):
        """Disable turns off AC charge if baseline had it disabled."""
        baseline = self._baseline_data()
        baseline[SERIAL]["ac_charge_enabled"] = False
        coordinator = _mock_coordinator(storm_mode_data=baseline)
        hass = _mock_hass(coordinator)
        call = _make_call(enable=False)

        await async_set_storm_mode(hass, call)

        inverter = coordinator.get_inverter_object(SERIAL)
        inverter.disable_ac_charge_mode.assert_called_once()

    @pytest.mark.asyncio
    async def test_disable_clears_storm_state(self):
        """Disable removes the storm mode state from config entry."""
        coordinator = _mock_coordinator(storm_mode_data=self._baseline_data())
        hass = _mock_hass(coordinator)
        call = _make_call(enable=False)

        await async_set_storm_mode(hass, call)

        update_args = hass.config_entries.async_update_entry.call_args
        options = update_args.kwargs.get("options", update_args[1].get("options", {}))
        storm_data = options[CONF_STORM_MODE]
        assert SERIAL not in storm_data

    @pytest.mark.asyncio
    async def test_disable_raises_when_not_active(self):
        """Disable raises when storm mode is not active."""
        coordinator = _mock_coordinator()
        hass = _mock_hass(coordinator)
        call = _make_call(enable=False)

        with pytest.raises(ServiceValidationError, match="not active"):
            await async_set_storm_mode(hass, call)


# ── Device not found test ────────────────────────────────────────────


class TestDeviceNotFound:
    """Test error handling when the serial is unknown."""

    @pytest.mark.asyncio
    async def test_unknown_serial_raises(self):
        """Unknown serial raises ServiceValidationError."""
        coordinator = _mock_coordinator()
        hass = _mock_hass(coordinator)
        call = _make_call(serial="unknown_serial", enable=True)

        with pytest.raises(ServiceValidationError, match="No EG4 device"):
            await async_set_storm_mode(hass, call)


# ── Storm mode switch entity tests ───────────────────────────────────


class TestStormModeSwitch:
    """Test the EG4StormModeSwitch entity."""

    def test_is_on_when_active(self):
        """Switch reports on when storm mode is active."""
        coordinator = _mock_coordinator(
            storm_mode_data={SERIAL: {"active": True}}
        )
        switch = EG4StormModeSwitch(coordinator, SERIAL)
        assert switch.is_on is True

    def test_is_off_when_inactive(self):
        """Switch reports off when storm mode is inactive."""
        coordinator = _mock_coordinator()
        switch = EG4StormModeSwitch(coordinator, SERIAL)
        assert switch.is_on is False

    def test_available_with_http(self):
        """Switch is available when cloud API is present."""
        coordinator = _mock_coordinator(has_http=True)
        switch = EG4StormModeSwitch(coordinator, SERIAL)
        assert switch.available is True

    def test_unavailable_without_http(self):
        """Switch is unavailable when cloud API is missing."""
        coordinator = _mock_coordinator(has_http=False)
        switch = EG4StormModeSwitch(coordinator, SERIAL)
        assert switch.available is False

    def test_switch_icon(self):
        """Switch has the hurricane icon."""
        coordinator = _mock_coordinator()
        switch = EG4StormModeSwitch(coordinator, SERIAL)
        assert switch._attr_icon == "mdi:weather-hurricane"

    def test_switch_name(self):
        """Switch has the expected name."""
        coordinator = _mock_coordinator()
        switch = EG4StormModeSwitch(coordinator, SERIAL)
        assert switch._attr_name == "Storm Mode"


# ── writeTime coordinator method tests ───────────────────────────────


class TestWriteTimeParameter:
    """Test the coordinator's write_time_parameter method."""

    @pytest.mark.asyncio
    async def test_write_time_posts_correct_payload(self):
        """write_time_parameter sends correct POST data."""
        from custom_components.eg4_web_monitor.coordinator_http import HTTPUpdateMixin

        mixin = MagicMock(spec=HTTPUpdateMixin)
        mixin.client = MagicMock()
        mixin.client.base_url = "https://monitor.eg4electronics.com"
        mixin.hass = MagicMock()

        # Mock session
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"success": True})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_response)

        with patch(
            "custom_components.eg4_web_monitor.coordinator_http.aiohttp_client"
        ) as mock_aiohttp:
            mock_aiohttp.async_get_clientsession.return_value = mock_session

            result = await HTTPUpdateMixin.write_time_parameter(
                mixin,
                serial="44300E0240",
                time_param="HOLD_AC_CHARGE_START_TIME",
                hour=0,
                minute=0,
            )

        assert result is True
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        assert "/WManage/web/maintain/remoteSet/writeTime" in call_args.args[0]
        payload = call_args.kwargs.get("data", call_args[1].get("data", {}))
        assert payload["inverterSn"] == "44300E0240"
        assert payload["timeParam"] == "HOLD_AC_CHARGE_START_TIME"
        assert payload["hour"] == "00"
        assert payload["minute"] == "00"
        assert payload["clientType"] == "WEB"

    @pytest.mark.asyncio
    async def test_write_time_raises_without_client(self):
        """write_time_parameter raises when client is None."""
        from custom_components.eg4_web_monitor.coordinator_http import HTTPUpdateMixin

        mixin = MagicMock(spec=HTTPUpdateMixin)
        mixin.client = None

        with pytest.raises(HomeAssistantError, match="Cloud API not available"):
            await HTTPUpdateMixin.write_time_parameter(
                mixin, serial="123", time_param="TEST", hour=0, minute=0
            )
