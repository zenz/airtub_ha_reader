"""Platform for sensor integration."""

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfRatio, UnitOfTemperature, UnitOfVolume
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, EVENT_NEW_DATA

BINARY_SENSOR_SUFFIXES = ("m", "fst", "loc", "ovr", "sch", "tmd", "vir")


def _create_entity(hass, device, key, value):
    """Create the right entity type for a data key."""
    entity_id = f"boiler_{device}_{key}"
    if key.endswith(BINARY_SENSOR_SUFFIXES):
        return UDPMulticastBinarySensor(hass, device, key, value, entity_id)
    return UDPMulticastSensor(hass, device, key, value, entity_id)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the sensor platform from a config entry."""
    device = hass.data[DOMAIN].get("device")
    if not device:
        return

    data = hass.data[DOMAIN].get("data", {})
    entities = []
    known_keys = set()

    def _build_new_entities(current_data):
        new_entities = []
        for key, value in current_data.items():
            if key in known_keys:
                continue
            known_keys.add(key)
            new_entities.append(_create_entity(hass, device, key, value))
        return new_entities

    new_entities = _build_new_entities(data)
    if new_entities:
        async_add_entities(new_entities)
        entities.extend(new_entities)

    @callback
    def handle_data_changed_event(event):
        """Handle new data and add entities for newly reported keys."""
        runtime = hass.data.get(DOMAIN)
        if runtime is None:
            return

        new_entities = _build_new_entities(runtime.get("data", {}))
        if new_entities:
            async_add_entities(new_entities)
            entities.extend(new_entities)

        for entity in entities:
            if entity.hass is not None:
                entity.handle_event(event)

    config_entry.async_on_unload(
        hass.bus.async_listen(EVENT_NEW_DATA, handle_data_changed_event)
    )


class UDPMulticastSensor(SensorEntity):
    """Representation of a UDP multicast sensor."""

    _attr_should_poll = False

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
        self._attr_name = f"boiler_{device}_{key}"
        self._attr_unique_id = entity_id
        self._state = self._convert_to_number(initial_value)
        self._setup_attributes(key)

    def _setup_attributes(self, key):
        """Set up sensor attributes based on the data key."""
        if key in ["cct", "cdt", "tct", "tdt", "odt"]:
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_icon = "mdi:thermometer"
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_suggested_display_precision = 0
        elif key in ["trt", "crt"]:
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_icon = "mdi:thermometer"
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_suggested_display_precision = 1
        elif key == "mod":
            self._attr_native_unit_of_measurement = UnitOfRatio.PERCENTAGE
            self._attr_icon = "mdi:percent-box"
            self._attr_device_class = None
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_suggested_display_precision = 0
        elif key == "gas":
            self._attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
            self._attr_icon = "mdi:meter-gas"
            self._attr_device_class = SensorDeviceClass.GAS
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
            self._attr_suggested_display_precision = 6
        elif key == "flt":
            self._attr_native_unit_of_measurement = None
            self._attr_icon = "mdi:alert-octagram"
            self._attr_device_class = None
            self._attr_state_class = None
            self._attr_suggested_display_precision = None
        elif key == "pwr":
            self._attr_native_unit_of_measurement = None
            self._attr_icon = "mdi:battery"
            self._attr_device_class = None
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_suggested_display_precision = 0
        else:
            self._attr_native_unit_of_measurement = None
            self._attr_icon = "mdi:numeric"
            self._attr_device_class = None
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_suggested_display_precision = 0

    async def async_added_to_hass(self):
        """Write the latest state when the entity is added."""
        await super().async_added_to_hass()
        self.handle_event(None)

    @property
    def native_value(self):
        """Return the value reported by the sensor."""
        if self._key == "flt":
            int_state = int(self._state)
            if int_state == 0:
                return "off"
            return f"E{int_state:02}"
        return self._state

    @staticmethod
    def _convert_to_number(value):
        """Convert a value to a number if possible."""
        if value == "":
            return 0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0

    def handle_event(self, event):
        """Update the sensor from the latest integration data."""
        data = self._hass.data.get(DOMAIN, {}).get("data", {})
        if self._key in data:
            self._state = self._convert_to_number(data[self._key])
        self.async_write_ha_state()


class UDPMulticastBinarySensor(BinarySensorEntity):
    """Representation of a UDP multicast binary sensor."""

    _attr_should_poll = False
    _attr_device_class = None

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
        self._attr_name = f"boiler_{device}_{key}"
        self._attr_unique_id = entity_id
        self._attr_icon = "mdi:toggle-switch-variant"
        self._attr_is_on = self._convert_to_boolean(initial_value)

    async def async_added_to_hass(self):
        """Write the latest state when the entity is added."""
        await super().async_added_to_hass()
        self.handle_event(None)

    @staticmethod
    def _convert_to_boolean(value):
        """Convert a value to a boolean."""
        return value in (1, "1", True)

    def handle_event(self, event):
        """Update the binary sensor from the latest integration data."""
        data = self._hass.data.get(DOMAIN, {}).get("data", {})
        if self._key in data:
            self._attr_is_on = self._convert_to_boolean(data[self._key])
        self.async_write_ha_state()
