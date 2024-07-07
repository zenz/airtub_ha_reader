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
MSG_TYPE = 4
ATTR_JSON_DATA = "cmd"
SERVICE_RECEIVE_JSON = "sender"
SERVICE_RECEIVE_JSON_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_JSON_DATA): cv.string,
    }
)

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

RETRY_MAX = 5
msg_recevied = False
sock = None


def xor_crypt(a: str, b: str):
    """XOR decode."""
    return "".join(chr(ord(x) ^ ord(y)) for x, y in zip(a, cycle(b)))


def pack_data(msgtype: int, message: str, secret: str):
    """Data encode."""
    len_num = len(message)
    crypt_data = xor_crypt(message, secret).encode("ascii")
    crc = zlib.crc32(crypt_data).to_bytes(4, "little")

    send_data = bytearray()
    send_data.extend(bytearray([msgtype, len_num, 0, 0]))
    send_data.extend(crc)
    send_data.extend(crypt_data)

    empty_len = 180 - len_num
    empty_array = bytearray(empty_len)
    send_data.extend(empty_array)

    return bytes(send_data)


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
    global msg_received
    global sock
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", multicast_port))
    mreq = struct.pack("=4sl", socket.inet_aton(multicast_group), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    sock.setblocking(False)

    loop = asyncio.get_running_loop()

    _LOGGER.debug(f"Registered udp listener")

    while True:
        try:
            data, addr = await loop.sock_recvfrom(sock, 1024)
            if len(data) != 0:
                dataid, datalen, realdata, crc1, crc2 = unpack_data(data, secret)
                if crc1 == crc2 and device in realdata.decode("ascii", errors="ignore"):
                    data_content = realdata.decode("ascii", errors="ignore").replace(
                        f'"dev":"{device}",', ""
                    )
                    if (
                        hass.data[DOMAIN].get("ip") is None
                        or hass.data[DOMAIN]["ip"] != addr[0]
                    ):
                        hass.data[DOMAIN]["ip"] = addr[0]
                    data_dict = json.loads(data_content)
                    if "rec" in data_dict:
                        _LOGGER.debug(f"Command confirmed!")
                        msg_received = True
                        hass.states.async_set(f"{DOMAIN}.status", "ready")
                    # Ensure 'mod' and 'flt' keys are present
                    if "mod" not in data_dict:
                        data_dict["mod"] = 0
                    if "flt" not in data_dict:
                        data_dict["flt"] = 0
                    hass.data[DOMAIN]["data"] = data_dict
                    hass.bus.async_fire(EVENT_NEW_DATA)
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
    async def handle_json_service(call):
        global msg_received
        global sock
        json_data = call.data.get(ATTR_JSON_DATA)
        remote_ip = hass.data[DOMAIN]["ip"]
        if remote_ip == None:
            return True
        try:
            parsed_data = json.loads(json_data)
            parsed_data["tar"] = device
            parsed_data["dev"] = f"{DOMAIN}"
            parsed_data["pwr"] = 5

            hass.states.async_set(f"{DOMAIN}.status", "received")
            loop = asyncio.get_running_loop()
            retry = 0
            msg_received = False
            try:
                while (not msg_received) and retry < RETRY_MAX:
                    parsed_data["try"] = retry
                    retry = retry + 1
                    encrypted_data = pack_data(
                        MSG_TYPE, json.dumps(parsed_data, separators=(",", ":")), secret
                    )
                    await asyncio.sleep(1)  # 延时1秒
                    # await loop.sock_sendto(sock, encrypted_data, (multicast_group, multicast_port))
                    await loop.sock_sendto(
                        sock, encrypted_data, (remote_ip, multicast_port)
                    )
                    hass.states.async_set(f"{DOMAIN}.status", "ready")
                _LOGGER.debug(
                    f"Sending JSON cmd to:{multicast_group} port:{multicast_port} with data:{parsed_data}"
                )
            except OSError as e:
                _LOGGER.error(f"OS error occurred while sending data: {e}")
            except socket.gaierror as e:
                _LOGGER.error(f"Socket address error occurred while sending data: {e}")

        except json.JSONDecodeError as e:
            _LOGGER.error(f"Error decoding JSON: {e}")
            hass.states.async_set(f"{DOMAIN}.status", "error")

    try:
        hass.data[DOMAIN] = {"device": device, "data": {}, "ip": None}

        hass.loop.create_task(
            udp_listener(hass, multicast_group, multicast_port, secret, device)
        )

        hass.async_create_task(
            discovery.async_load_platform(hass, "sensor", DOMAIN, {}, config)
        )

        hass.states.async_set(f"{DOMAIN}.status", "ready")
        hass.services.async_register(
            DOMAIN,
            SERVICE_RECEIVE_JSON,
            handle_json_service,
            schema=SERVICE_RECEIVE_JSON_SCHEMA,
        )

    except Exception as e:
        _LOGGER.error(f"Error during setup: {e}")
        return False

    return True
