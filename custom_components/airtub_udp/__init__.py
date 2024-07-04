"""UDP Multicast integration."""

import asyncio
import logging
import socket
import struct
import binascii
import zlib
import json
from itertools import cycle
from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery
import voluptuous as vol
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

DOMAIN = "airtub_udp"
EVENT_NEW_DATA = "airtub_new_data_received"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required("multicast_group"): cv.string,
                vol.Required("multicast_port"): cv.port,
                vol.Required("secret"): cv.string,
                vol.Required("device"): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


def xor_crypt(a: str, b: str):
    """XOR decode."""
    return "".join(chr(ord(x) ^ ord(y)) for x, y in zip(a, cycle(b)))


def unpack_data(pack_data: bytes, secret: str):
    """Data decode."""
    if len(pack_data) != 0:
        msgtype = pack_data[0]
        datalen = pack_data[1]
        crc1 = binascii.hexlify(pack_data[4:8][::-1]).decode()
        crc2 = hex(zlib.crc32(pack_data[8 : datalen + 8]))[2:]
        realdata = bytearray(pack_data[8 : datalen + 8])
        realdata = bytes(xor_crypt(realdata.decode("ascii"), secret), "ascii")
        return msgtype, datalen, realdata, crc1, crc2
    return 0, 0, b"", "", ""


async def udp_listener(
    hass: HomeAssistant,
    multicast_group: str,
    multicast_port: int,
    secret: str,
    device: str,
):
    """Listen for UDP multicast messages."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", multicast_port))
    mreq = struct.pack("=4sl", socket.inet_aton(multicast_group), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    loop = asyncio.get_running_loop()
    sock.setblocking(False)

    _LOGGER.debug(f"Registered udp listener")

    while True:
        try:
            data = await loop.sock_recv(sock, 1024)
            if len(data) != 0:
                dataid, datalen, realdata, crc1, crc2 = unpack_data(data, secret)
                if crc1 == crc2 and device in realdata.decode("ascii", errors="ignore"):
                    data_content = realdata.decode("ascii", errors="ignore").replace(
                        f'"dev":"{device}",', ""
                    )
                    data_dict = json.loads(data_content)
                    # Ensure 'mod' and 'flt' keys are present
                    if "mod" not in data_dict:
                        data_dict["mod"] = 0
                    if "flt" not in data_dict:
                        data_dict["flt"] = 0
                    hass.data[DOMAIN]["data"] = data_dict
                    hass.bus.async_fire(EVENT_NEW_DATA)
                    # _LOGGER.warning(f"Received data: {data_content}")
        except socket.error as e:
            _LOGGER.error(f"Socket error: {e}")
            await asyncio.sleep(1)  # Wait a bit before retrying in case of error
        await asyncio.sleep(0)  # Yield control to the event loop


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the UDP Multicast component."""
    conf = config[DOMAIN]
    multicast_group = conf["multicast_group"]
    multicast_port = conf["multicast_port"]
    secret = conf["secret"]
    device = conf["device"]

    # _LOGGER.warning(f"airtub_udp setup {device} with {multicast_group}:{multicast_port}")

    hass.data[DOMAIN] = {"device": device, "data": {}}

    hass.loop.create_task(
        udp_listener(hass, multicast_group, multicast_port, secret, device)
    )

    hass.async_create_task(
        discovery.async_load_platform(hass, "sensor", DOMAIN, {}, config)
    )

    return True
