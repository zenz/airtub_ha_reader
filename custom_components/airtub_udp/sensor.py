"""Platform for sensor integration."""

# pylint: disable=broad-except, global-statement, too-many-locals, too-many-statements, too-many-instance-attributes, too-many-arguments, unused-argument, unused-variable, import-error, overridden-final-method

import logging
from homeassistant.core import HomeAssistant, callback
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import UnitOfTemperature, PERCENTAGE
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from .const import DOMAIN, EVENT_NEW_DATA

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the sensor platform from a config entry."""
    device = hass.data[DOMAIN].get("device")
    if not device:
        return

    data = hass.data[DOMAIN].get("data", {})

    entities = [
        UDPMulticastBinarySensor(hass, device, key, value, f"boiler_{device}_{key}")
        if key.endswith(("m", "fst", "loc", "ovr", "sch", "tmd", "vir"))
        else UDPMulticastSensor(hass, device, key, value, f"boiler_{device}_{key}")
        for key, value in data.items()
    ]

    async_add_entities(entities, update_before_add=True)

    @callback
    def handle_data_changed_event(event):
        """Handle the custom event and notify all entities."""
        for entity in entities:
            entity.handle_event(event)

    hass.bus.async_listen(EVENT_NEW_DATA, handle_data_changed_event)


class UDPMulticastSensor(SensorEntity):
    """Representation of a UDP Multicast sensor."""

    def __init__(
        self,
        hass: HomeAssistant,
        device: str,
        key: str,
        initial_value: str,
        entity_id: str,
    ):
        """Initialize the sensor."""
        self._hass = hass
        self._device = device
        self._key = key
        self._name = f"boiler_{device}_{key}"
        self._state = self._convert_to_number(initial_value)
        self._entity_id = entity_id
        self._setup_attributes(key)

    def _setup_attributes(self, key):
        """Setup sensor attributes based on key."""
        if key in ["cct", "cdt", "tct", "tdt", "odt"]:
            self._attr_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_icon = "mdi:thermometer"
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_state_class = "measurement"
            self._attr_precision = 0  # 温度精度为0
        elif key in ["trt", "crt"]:
            self._attr_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_icon = "mdi:thermometer"
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_state_class = "measurement"
            self._attr_precision = 1  # 温度精度为1
        elif key in ["mod"]:
            self._attr_unit_of_measurement = PERCENTAGE
            self._attr_icon = "mdi:percent-box"
            self._attr_device_class = None
            self._attr_state_class = "measurement"
            self._attr_precision = 0  # 百分比精度为0
        elif key in ["gas"]:
            self._attr_unit_of_measurement = "m³"
            self._attr_icon = "mdi:meter-gas"
            self._attr_device_class = SensorDeviceClass.GAS
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
            self._attr_precision = 6  # 小数点后6位
        elif key in ["flt"]:
            self._attr_unit_of_measurement = None
            self._attr_icon = "mdi:alert-octagram"
            self._attr_device_class = None
            self._attr_state_class = None
            self._attr_precision = None
        elif key in ["pwr"]:
            self._attr_unit_of_measurement = None
            self._attr_icon = "mdi:battery"
            self._attr_device_class = None
            self._attr_state_class = "measurement"
            self._attr_precision = 0 # 默认京都为0
        else:
            self._attr_unit_of_measurement = None
            self._attr_icon = "mdi:numeric"
            self._attr_device_class = None
            self._attr_state_class = "measurement"
            self._attr_precision = 0  # 默认精度为0

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        if self._key == "flt":
            # 将状态值转换为整数
            int_state = int(self._state)
            if int_state == 0:
                return "off"
            # 将整数值转换为字符串并确保至少有2位数字
            str_state = f"E{int_state:02}"
            return str_state
        return (
            round(self._state, self._attr_precision)
            if self._attr_precision is not None
            else self._state
        )

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._entity_id

    @property
    def icon(self):
        return self._attr_icon

    @property
    def device_class(self):
        """Return the device class of the sensor."""
        return self._attr_device_class

    @property
    def state_class(self):
        """Return the state class of the sensor."""
        return self._attr_state_class

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._attr_unit_of_measurement

    @staticmethod
    def _convert_to_number(value):
        """Convert value to number if possible."""
        if value == "":
            return 0
        try:
            return float(value)
        except ValueError:
            return 0

    def handle_event(self, event):
        """Handle the custom event and update state."""
        self.async_schedule_update_ha_state(True)

    async def async_update(self):
        """Fetch new state data for the sensor."""
        data = self._hass.data[DOMAIN].get("data", {})
        if self._key in data:
            new_value = data[self._key]
            new_value_converted = self._convert_to_number(new_value)
            if new_value_converted != self._state:
                self._state = new_value_converted
                self.async_write_ha_state()


class UDPMulticastBinarySensor(BinarySensorEntity):
    """Representation of a UDP Multicast binary sensor."""

    def __init__(
        self,
        hass: HomeAssistant,
        device: str,
        key: str,
        initial_value: str,
        entity_id: str,
    ):
        """Initialize the binary sensor."""
        self._hass = hass
        self._device = device
        self._key = key
        self._name = f"boiler_{device}_{key}"
        self._state = self._convert_to_boolean(initial_value)
        self._entity_id = entity_id
        self._attr_icon = "mdi:toggle-switch-variant"

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def icon(self):
        return self._attr_icon

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return self._state

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._entity_id

    @property
    def device_class(self):
        """Return the device class of the binary sensor."""
        return "opening"

    @staticmethod
    def _convert_to_boolean(value):
        """Convert value to boolean."""
        return value == 1

    def handle_event(self, event):
        """Handle the custom event and update state."""
        self.async_schedule_update_ha_state(True)

    async def async_update(self):
        """Fetch new state data for the binary sensor."""
        data = self._hass.data[DOMAIN].get("data", {})
        if self._key in data:
            new_value = data[self._key]
            new_value_converted = self._convert_to_boolean(new_value)
            if new_value_converted != self._state:
                self._state = new_value_converted
                self.async_write_ha_state()
