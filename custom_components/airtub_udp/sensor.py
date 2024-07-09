import logging
from homeassistant.core import HomeAssistant, callback
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import UnitOfTemperature, PERCENTAGE
from homeassistant.components.sensor import SensorDeviceClass
from .const import DOMAIN, EVENT_NEW_DATA

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant, config: dict, async_add_entities, discovery_info=None
):
    """Set up the UDP Multicast sensor platform."""
    pass


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the sensor platform from a config entry."""
    device = hass.data[DOMAIN]["device"]
    entities = []
    data = hass.data[DOMAIN].get("data", {})

    _LOGGER.debug(f"Setting up platform with device: {device}, data: {data}")

    for key, value in data.items():
        entity_id = f"boiler_{device}_{key}"
        _LOGGER.debug(f"Creating entity for key: {key}, entity_id: {entity_id}")
        if key.endswith("m") or key.endswith("fst") or key.endswith("sch"):
            entity = UDPMulticastBinarySensor(hass, device, key, value, entity_id)
        else:
            entity = UDPMulticastSensor(hass, device, key, value, entity_id)
        entities.append(entity)

    async_add_entities(entities, update_before_add=True)


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
        if key in ["cct", "cdt", "tct", "tdt", "odt", "tdf"]:
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
        else:
            self._attr_unit_of_measurement = None
            self._attr_icon = "mdi:numeric"
            self._attr_device_class = None
            self._attr_state_class = "measurement"
            self._attr_precision = 0  # 默认精度为0
        hass.bus.async_listen(EVENT_NEW_DATA, self._handle_data_changed_event)

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
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
        _LOGGER.debug(f"Attempting to convert value: {value}")
        if value == "":
            return 0
        try:
            return float(value)
        except ValueError:
            _LOGGER.debug(f"Conversion failed for value: {value}, returning 0")
            return 0

    @callback
    def _handle_data_changed_event(self, event):
        """Handle the custom event and update state"""
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
        else:
            _LOGGER.debug(f"Key '{self._key}' not found in data.")


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
        hass.bus.async_listen(EVENT_NEW_DATA, self._handle_data_changed_event)

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
        _LOGGER.debug(f"Attempting to convert value to boolean: {value}")
        return value == 1

    @callback
    def _handle_data_changed_event(self, event):
        """Handle the custom event and update state"""
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
        else:
            _LOGGER.debug(f"Key '{self._key}' not found in data.")
