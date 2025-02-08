"""Platform for climate integration."""

# pylint: disable=broad-except, global-statement, too-many-locals, too-many-statements, unused-argument, unused-variable, import-error, abstract-method

import logging
import asyncio
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import HVACMode, ClimateEntityFeature
from homeassistant.const import UnitOfTemperature, ATTR_TEMPERATURE
from .const import DOMAIN, EVENT_NEW_DATA

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the climate platform from a config entry."""
    device = hass.data[DOMAIN].get("device")
    if not device:
        return

    operate = hass.data[DOMAIN].get("mode", "auto")
    op_mode = 1 if operate == "auto" else 0

    devices = [
        AirtubClimateDevice(hass, f"boiler_{device}_ch", op_mode),
        AirtubClimateDevice(hass, f"boiler_{device}_dhw", op_mode)
    ]
    async_add_entities(devices)

    async def handle_new_data_event(event):
        await asyncio.gather(*(device.async_update() for device in devices))
        for device in devices:
            device.async_schedule_update_ha_state(True)

    hass.bus.async_listen(EVENT_NEW_DATA, handle_new_data_event)


class AirtubClimateDevice(ClimateEntity):
    """Representation of a custom climate device."""

    def __init__(self, hass, name, mode):
        """Initialize the climate device."""
        self._enable_turn_on_off_backwards_compatibility = False
        self._mode = mode
        self._unique_id = name
        self.entity_id = f"climate.{name}"
        self._name = self._generate_friendly_name()
        self._hass = hass
        self._mode_set = False
        self._attr_icon_ch = "mdi:radiator"
        self._attr_icon_dhw = "mdi:shower"
        self._temperature = 0
        self._target_temperature = 0
        self._hvac_mode = HVACMode.OFF
        self._operation = "待机"
        self._man_temperature = 0
        self._man_target_temperature = 0
        self._man_hvac_mode = HVACMode.OFF
        self._dhw_temperature = 0
        self._dhw_target_temperature = 0
        self._dhw_mode = HVACMode.OFF
        self._dhw_operation = "待机"
        self._supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )
        self._disable_update = False

    def _generate_friendly_name(self):
        """Generate a friendly name."""
        if "_ch" in self._unique_id:
            return "ch_auto_control" if self._mode else "ch_man_control"
        return "dhw_control"

    @property
    def unique_id(self):
        """Return the unique ID of the climate device."""
        return self._unique_id

    @property
    def translation_key(self):
        """Return the translation key."""
        return self._name

    @property
    def has_entity_name(self):
        """Return the entity name."""
        return True

    @property
    def icon(self):
        return self._attr_icon_ch if "_ch" in self._unique_id else self._attr_icon_dhw

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return UnitOfTemperature.CELSIUS

    @property
    def hvac_modes(self):
        """Return the list of available operation modes."""
        return [HVACMode.OFF, HVACMode.HEAT]

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return self._supported_features

    @property
    def hvac_mode(self):
        """Return current operation mode."""
        if "_ch" in self._unique_id:
            return self._hvac_mode if self._mode else self._man_hvac_mode
        return self._dhw_mode

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        return 1.0  # 设置步进为1.0

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        if "_ch" in self._unique_id:
            return self._target_temperature if self._mode else self._man_target_temperature
        return self._dhw_target_temperature

    @property
    def current_temperature(self):
        """Return the current temperature."""
        if "_ch" in self._unique_id:
            return self._temperature if self._mode else self._man_temperature
        return self._dhw_temperature

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        if "_ch" in self._unique_id:
            return 4 if self._mode else 35
        return 35

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        if "_ch" in self._unique_id:
            return 30 if self._mode else 80
        return 60

    @property
    def hvac_action(self):
        """Return current HVAC mode."""
        return self._operation if "_ch" in self._unique_id else self._dhw_operation

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode."""
        mode = "1" if hvac_mode == HVACMode.HEAT else "0"
        command = None
        if "_ch" in self._unique_id:
            if self._mode:
                self._hvac_mode = hvac_mode
                command = '{"atm":' + mode + "}"
            else:
                self._man_hvac_mode = hvac_mode
                command = '{"tcm":' + mode + "}"
        else:
            self._dhw_mode = hvac_mode
            command = '{"tdm":' + mode + "}"

        # 准备要发送的 JSON 数据
        json_data = {"cmd": command}

        # 禁用自动更新
        self._disable_update = True

        # 调用 service 发送数据
        await self._hass.services.async_call(
            DOMAIN, "sender", json_data  # 你的 domain  # 你的 service 名  # 传递的数据
        )

        # 启用自动更新
        await asyncio.sleep(3)  # 等待一段时间
        self._disable_update = False

        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        command = None
        if ATTR_TEMPERATURE in kwargs:
            if "_ch" in self._unique_id:
                if self._mode:
                    self._target_temperature = kwargs[ATTR_TEMPERATURE]
                    command = '{"trt":' + str(self._target_temperature) + "}"
                else:
                    self._man_target_temperature = kwargs[ATTR_TEMPERATURE]
                    command = '{"tct":' + str(self._man_target_temperature) + "}"
            else:
                self._dhw_target_temperature = kwargs[ATTR_TEMPERATURE]
                command = '{"tdt":' + str(self._dhw_target_temperature) + "}"
            json_data = {"cmd": command}

            # 禁用自动更新
            self._disable_update = True

            await self._hass.services.async_call(DOMAIN, "sender", json_data)

            # 启用自动更新
            await asyncio.sleep(3)  # 等待一段时间
            self._disable_update = False

        self.async_write_ha_state()

    async def async_update(self):
        """Fetch new state data for the climate entity."""

        if self._disable_update:
            return

        if not self.hass:
            return

        data = self._hass.data.get(DOMAIN, {}).get("data", {})
        if not data:
            return

        current_heating_mode = data.get("atm", self._mode)
        if current_heating_mode != self._mode and not self._mode_set:
            command = '{"atm":' + str(self._mode) + "}"
            json_data = {"cmd": command}
            await self._hass.services.async_call(DOMAIN, "sender", json_data)
            await asyncio.sleep(5)
        else:
            self._mode_set = True

        if "_ch" in self._unique_id:
            if self._mode:
                op_mode = data.get("atm", self._mode)
                self._hvac_mode = HVACMode.HEAT if op_mode else HVACMode.OFF
                self._temperature = data.get("crt", self._temperature)
                self._target_temperature = data.get("trt", self._target_temperature)
                mode = data.get("ccm", 0)
                fst = data.get("fst", 0)
                self._operation = "🔥加热中" if (mode and fst) else "待机"
            else:
                op_mode = data.get("tcm", self._mode)
                self._man_hvac_mode = HVACMode.HEAT if op_mode else HVACMode.OFF
                self._man_temperature = data.get("cct", self._man_temperature)
                self._man_target_temperature = data.get(
                    "tct", self._man_target_temperature
                )
                mode = data.get("ccm", 0)
                fst = data.get("fst", 0)
                self._operation = "🔥加热中" if (mode and fst) else "待机"
        else:
            mode = data.get("tdm", self._dhw_mode)
            self._dhw_mode = HVACMode.HEAT if mode else HVACMode.OFF
            self._dhw_temperature = data.get("cdt", self._dhw_temperature)
            self._dhw_target_temperature = data.get("tdt", self._dhw_target_temperature)
            mode = data.get("cdm", 0)
            fst = data.get("fst", 0)
            self._dhw_operation = "🔥加热中" if (mode and fst) else "待机"

        self.async_write_ha_state()
