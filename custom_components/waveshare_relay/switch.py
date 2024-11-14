import asyncio
import logging
import socket
from homeassistant.components.switch import SwitchEntity
from homeassistant.const import CONF_IP_ADDRESS
from homeassistant.helpers.event import async_track_state_change_event

_LOGGER = logging.getLogger(__name__)

CONF_PORT = "port"

async def async_setup_entry(hass, config_entry, async_add_entities):
    ip_address = config_entry.data[CONF_IP_ADDRESS]
    port = config_entry.data[CONF_PORT]

    # Create 8 switches for 8 relay channels
    switches = [
        WaveshareRelaySwitch(hass, ip_address, port, relay_channel)
        for relay_channel in range(8)
    ]

    async_add_entities(switches)

class WaveshareRelaySwitch(SwitchEntity):
    def __init__(self, hass, ip_address, port, relay_channel):
        self.hass = hass
        self._is_on = False
        self._ip_address = ip_address
        self._port = port
        self._relay_channel = relay_channel  # Unique channel for each switch
        self._status_task = None  # Task for checking relay status

    @property
    def name(self):
        return f"Waveshare Relay {self._relay_channel + 1} Switch"

    @property
    def is_on(self):
        return self._is_on

    async def async_turn_on(self, **kwargs):
        # Fetch the latest interval from the corresponding number entity
        interval_entity_id = f"number.waveshare_relay_{self._relay_channel + 1}_interval"
        interval_state = self.hass.states.get(interval_entity_id)
        if interval_state:
            try:
                # Convert the state to a float first, then to an integer
                interval = int(float(interval_state.state))
            except ValueError:
                _LOGGER.error("Invalid interval value for %s: %s", interval_entity_id, interval_state.state)
                interval = 5  # Default to 5 seconds if conversion fails
        else:
            interval = 5  # Default to 5 seconds if not found

        await self.hass.async_add_executor_job(self._send_modbus_command, interval * 10)  # Convert to 100ms units
        self._is_on = True
        self.async_write_ha_state()  # Notify Home Assistant of state change

        # Start the status check task
        if self._status_task is None or self._status_task.done():
            self._status_task = asyncio.create_task(self.check_relay_status())

    async def async_turn_off(self, **kwargs):
        await self.hass.async_add_executor_job(self._send_modbus_command, 0)
        self._is_on = False
        self.async_write_ha_state()  # Notify Home Assistant of state change
        if self._status_task:
            self._status_task.cancel()
            try:
                await self._status_task
            except asyncio.CancelledError:
                _LOGGER.info("Status check task for channel %d cancelled", self._relay_channel)

    def _send_modbus_command(self, interval):
        relay_address = self._relay_channel  # Use the relay channel as the address

        message = [
            0x00, 0x01,  # Transaction Identifier
            0x00, 0x00,  # Protocol Identifier
            0x00, 0x06,  # Length
            0x01,        # Unit Identifier
            0x05,        # Command
            0x02 if interval != 0 else 0x00,  # Flash Command (02 for on)
            relay_address,  # Relay Address
            (interval >> 8) & 0xFF if interval != 0 else 0x00,  # Interval Time
            interval & 0xFF if interval != 0 else 0x00  # Interval Time
        ]

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect((self._ip_address, self._port))
                sock.sendall(bytes(message))
                response = sock.recv(1024)
                _LOGGER.info("Received response: %s", response.hex())
        except Exception as e:
            _LOGGER.error("Socket error: %s", e)

    async def check_relay_status(self):
        """Continuously check the relay status every 1 second."""
        try:
            while self._is_on:
                await asyncio.sleep(1)  # Wait for 1 second
                try:
                    relay_status = await self.hass.async_add_executor_job(self._read_relay_status)
                    _LOGGER.info("Relay status for channel %d: %s", self._relay_channel, relay_status)

                    # Update the switch state based on the relay status
                    if relay_status[self._relay_channel] == 0:
                        self._is_on = False
                        self.async_write_ha_state()  # Notify Home Assistant of state change
                        _LOGGER.info("Relay channel %d is off", self._relay_channel)
                except Exception as e:
                    _LOGGER.error("Error reading relay status: %s", e)
        except asyncio.CancelledError:
            _LOGGER.info("Status check task for channel %d cancelled", self._relay_channel)

    def _read_relay_status(self):
        """Send a Modbus command to read the relay status."""
        sensing_code = [
            0x00, 0x01,  # Transaction Identifier
            0x00, 0x00,  # Protocol Identifier
            0x00, 0x06,  # Length
            0x01,        # Unit Identifier
            0x01,        # Command for reading status
            0x00, 0x00,  # Starting Address
            0x00, 0x08   # Quantity of Coils
        ]

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect((self._ip_address, self._port))
                sock.sendall(bytes(sensing_code))
                response = sock.recv(1024)
                _LOGGER.info("Received status response: %s", response.hex())

                # Interpret the response to get the relay status
                # The status byte is the last byte in the response
                status_byte = response[-1]

                # Analyze each bit of the status byte
                relay_status = [(status_byte >> bit) & 1 for bit in range(8)]
                _LOGGER.info("Relay statuses: %s", relay_status)
                return relay_status
        except Exception as e:
            _LOGGER.error("Socket error while reading status: %s", e)
            raise
