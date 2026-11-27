"""Platform for climate integration."""

import asyncio
import json
from typing import ClassVar

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature

from .const import DOMAIN, EVENT_NEW_DATA


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the climate platform from a config entry."""
    device = hass.data[DOMAIN].get("device")
    if not device:
        return

    operate = hass.data[DOMAIN].get("mode", "auto")
    op_mode = 1 if operate == "auto" else 0
    devices = [
        AirtubClimateDevice(hass, f"boiler_{device}_ch", op_mode),
        AirtubClimateDevice(hass, f"boiler_{device}_dhw", op_mode),
    ]
    async_add_entities(devices)

    async def handle_new_data_event(event):
        if DOMAIN not in hass.data:
            return
        await asyncio.gather(*(device.async_update() for device in devices))

    config_entry.async_on_unload(
        hass.bus.async_listen(EVENT_NEW_DATA, handle_new_data_event)
    )


class AirtubClimateDevice(ClimateEntity):
    """Representation of a custom climate device."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes: ClassVar[list[HVACMode]] = [HVACMode.OFF, HVACMode.HEAT]
    _attr_target_temperature_step = 1.0
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, hass, name, mode):
        """Initialize the climate device."""
        self._mode = mode
        self._attr_unique_id = name
        self.entity_id = f"climate.{name}"
        self._attr_translation_key = self._generate_translation_key()
        self._attr_icon = "mdi:radiator" if "_ch" in name else "mdi:shower"
        self._hass = hass
        self._mode_set = False
        self._temperature = 0
        self._target_temperature = 0
        self._hvac_mode = HVACMode.OFF
        self._hvac_action = HVACAction.OFF
        self._man_temperature = 0
        self._man_target_temperature = 0
        self._man_hvac_mode = HVACMode.OFF
        self._man_hvac_action = HVACAction.OFF
        self._dhw_temperature = 0
        self._dhw_target_temperature = 0
        self._dhw_mode = HVACMode.OFF
        self._dhw_action = HVACAction.OFF
        self._disable_update = False

    def _generate_translation_key(self):
        """Generate the entity translation key."""
        if "_ch" in self._attr_unique_id:
            return "ch_auto_control" if self._mode else "ch_man_control"
        return "dhw_control"

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        if "_ch" in self._attr_unique_id:
            return 4 if self._mode else 35
        return 35

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        if "_ch" in self._attr_unique_id:
            return 30 if self._mode else 80
        return 60

    @property
    def hvac_mode(self):
        """Return current operation mode."""
        if "_ch" in self._attr_unique_id:
            return self._hvac_mode if self._mode else self._man_hvac_mode
        return self._dhw_mode

    @property
    def native_target_temperature(self):
        """Return the target temperature in the native unit."""
        if "_ch" in self._attr_unique_id:
            return (
                self._target_temperature if self._mode else self._man_target_temperature
            )
        return self._dhw_target_temperature

    @property
    def native_current_temperature(self):
        """Return the current temperature in the native unit."""
        if "_ch" in self._attr_unique_id:
            return self._temperature if self._mode else self._man_temperature
        return self._dhw_temperature

    @property
    def hvac_action(self):
        """Return the current HVAC action."""
        if "_ch" in self._attr_unique_id:
            return self._hvac_action if self._mode else self._man_hvac_action
        return self._dhw_action

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode."""
        mode = "1" if hvac_mode == HVACMode.HEAT else "0"
        if "_ch" in self._attr_unique_id:
            if self._mode:
                self._hvac_mode = hvac_mode
                command = {"atm": int(mode)}
            else:
                self._man_hvac_mode = hvac_mode
                command = {"tcm": int(mode)}
        else:
            self._dhw_mode = hvac_mode
            command = {"tdm": int(mode)}

        self._disable_update = True
        try:
            await self._hass.services.async_call(
                DOMAIN,
                "sender",
                service_data={"cmd": json.dumps(command, separators=(",", ":"))},
                blocking=True,
            )
        finally:
            self._disable_update = False

        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        if ATTR_TEMPERATURE not in kwargs:
            return

        temperature = kwargs[ATTR_TEMPERATURE]
        if "_ch" in self._attr_unique_id:
            if self._mode:
                self._target_temperature = temperature
                command = {"trt": temperature}
            else:
                self._man_target_temperature = temperature
                command = {"tct": temperature}
        else:
            self._dhw_target_temperature = temperature
            command = {"tdt": temperature}

        self._disable_update = True
        try:
            await self._hass.services.async_call(
                DOMAIN,
                "sender",
                service_data={"cmd": json.dumps(command, separators=(",", ":"))},
                blocking=True,
            )
        finally:
            self._disable_update = False

        self.async_write_ha_state()

    async def async_added_to_hass(self):
        """Write the latest state when the entity is added."""
        await super().async_added_to_hass()
        await self.async_update()

    async def async_update(self):
        """Fetch new state data for the climate entity."""
        if self._disable_update or not self.hass:
            return

        data = self._hass.data.get(DOMAIN, {}).get("data", {})
        if not data:
            return

        if "_ch" in self._attr_unique_id and self._mode and not self._mode_set:
            current_mode = data.get("atm", self._mode)
            if current_mode != self._mode:
                if self._hass.data[DOMAIN].get("ip") is not None:
                    await self._hass.services.async_call(
                        DOMAIN,
                        "sender",
                        service_data={"cmd": json.dumps({"atm": self._mode})},
                        blocking=True,
                    )
                    self._mode_set = True
            else:
                self._mode_set = True

        if "_ch" in self._attr_unique_id:
            if self._mode:
                op_mode = data.get("atm", 0)
                self._hvac_mode = HVACMode.HEAT if op_mode else HVACMode.OFF
                self._temperature = data.get("crt", self._temperature)
                self._target_temperature = data.get("trt", self._target_temperature)
                self._hvac_action = self._get_hvac_action(
                    self._hvac_mode, data.get("ccm", 0), data.get("fst", 0)
                )
            else:
                op_mode = data.get("tcm", 0)
                self._man_hvac_mode = HVACMode.HEAT if op_mode else HVACMode.OFF
                self._man_temperature = data.get("cct", self._man_temperature)
                self._man_target_temperature = data.get(
                    "tct", self._man_target_temperature
                )
                self._man_hvac_action = self._get_hvac_action(
                    self._man_hvac_mode, data.get("ccm", 0), data.get("fst", 0)
                )
        else:
            mode = data.get("tdm", 0)
            self._dhw_mode = HVACMode.HEAT if mode else HVACMode.OFF
            self._dhw_temperature = data.get("cdt", self._dhw_temperature)
            self._dhw_target_temperature = data.get("tdt", self._dhw_target_temperature)
            self._dhw_action = self._get_hvac_action(
                self._dhw_mode, data.get("cdm", 0), data.get("fst", 0)
            )

        self.async_write_ha_state()

    @staticmethod
    def _get_hvac_action(hvac_mode, active, flame):
        """Return the HVAC action for the reported boiler state."""
        if hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        if active and flame:
            return HVACAction.HEATING
        return HVACAction.IDLE
