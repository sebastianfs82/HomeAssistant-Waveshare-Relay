import logging
from homeassistant.components.number import NumberEntity
from homeassistant.helpers.restore_state import RestoreEntity

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    # Create 8 number entities for configuring the on-interval of each relay
    intervals = [
        WaveshareRelayInterval(f"Waveshare Relay {relay_channel + 1} Interval", relay_channel)
        for relay_channel in range(8)
    ]

    async_add_entities(intervals)

class WaveshareRelayInterval(RestoreEntity, NumberEntity):
    _attr_icon = "mdi:update"

    def __init__(self, name, relay_channel):
        self._attr_name = name
        self.relay_channel = relay_channel  # Store the relay channel
        self._attr_editable = True
        self._attr_mode = 'slider'
        self._attr_native_min_value = 0
        self._attr_native_max_value = 600
        self._attr_native_step = 10
        self._attr_device_class = "duration"  # Changed to duration for time intervals
        self._attr_native_unit_of_measurement = "s"  # Changed to seconds
        self._attr_native_value = None  # Start with None to ensure restoration

    async def async_added_to_hass(self):
        """Restore the previous state when Home Assistant starts."""
        last_state = await self.async_get_last_state()
        if last_state and last_state.state:
            try:
                self._attr_native_value = float(last_state.state)
                _LOGGER.info("Restored %s to %s seconds", self._attr_name, self._attr_native_value)
            except ValueError:
                _LOGGER.warning("Could not restore state for %s", self._attr_name)
                self._attr_native_value = 5  # Default to 5 if restoration fails
        else:
            self._attr_native_value = 5  # Default to 5 if no previous state exists

    @property
    def native_value(self):
        return self._attr_native_value

    async def async_set_native_value(self, value):
        self._attr_native_value = value
        self.async_write_ha_state()
        _LOGGER.info("Set interval for relay channel %d to %d seconds", self.relay_channel, value)

    @property
    def native_min_value(self):
        return self._attr_native_min_value

    @property
    def native_max_value(self):
        return self._attr_native_max_value

    @property
    def native_step(self):
        return self._attr_native_step

    @property
    def mode(self):
        return self._attr_mode

    @property
    def native_unit_of_measurement(self):
        return self._attr_native_unit_of_measurement
