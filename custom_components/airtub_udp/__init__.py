"""Airfit Airtub Partner integration."""

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
from homeassistant.helpers.entity import Entity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE, CONF_PASSWORD, CONF_MODE
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from .const import DOMAIN, EVENT_NEW_DATA

_LOGGER = logging.getLogger(__name__)

MSG_TYPE = 4
ATTR_JSON_DATA = "cmd"
SERVICE_RECEIVE_JSON = "sender"
SERVICE_RECEIVE_JSON_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_JSON_DATA): cv.string,
    }
)

RETRY_MAX = 5
msg_received = False
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

    _LOGGER.debug(f"AIRTUB: Registered udp listener")

    # 初始默认数据
    default_data = {
        "tcm": 0,
        "tct": 0,
        "ccm": 0,
        "cct": 0,
        "tdm": 0,
        "tdt": 0,
        "cdm": 0,
        "cdt": 0,
        "atm": 0,
        "trt": 0,
        "crt": 0,
        "pwr": 0,
        "odt": 0,
        "coe": 0,
        "fst": 0,
        "mod": 0,
        "flt": 0,
        "gas": 0.000001,  # 避免将gas设置为0
    }

    # 在未接收到数据前，填充默认值
    hass.data[DOMAIN]["data"] = default_data
    hass.states.async_set(f"{DOMAIN}.status", "waiting for data")

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
                        _LOGGER.debug(f"AIRTUB: Command confirmed!")
                        msg_received = True
                        del data_dict["rec"]
                        hass.states.async_set(f"{DOMAIN}.status", "ready")
                    # Ensure 'mod', 'flt', 'pwr', and 'gas' keys are present with default values if missing
                    data_dict.setdefault("mod", 0)
                    data_dict.setdefault("flt", 0)
                    data_dict.setdefault("pwr", 0)
                    if "gas" in data_dict and data_dict["gas"] == 0:
                        data_dict["gas"] = 0.000001

                    hass.data[DOMAIN]["data"] = data_dict
                    if "crt" in data_dict:
                        hass.bus.async_fire(EVENT_NEW_DATA)
        except socket.error as e:
            _LOGGER.error(f"Socket error: {e}")
            await asyncio.sleep(1)  # Wait a bit before retrying in case of error
        await asyncio.sleep(0)  # Yield control to the event loop


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Airtub UDP from a config entry."""
    multicast_group = "224.0.1.3"
    multicast_port = 4211
    device = entry.data.get(CONF_DEVICE)
    secret = entry.data.get(CONF_PASSWORD)
    _LOGGER.debug(f"Device: {device}, Secret: {secret}")
    

    async def handle_json_service(call):
        global msg_received
        global sock
        json_data = call.data.get(ATTR_JSON_DATA)
        remote_ip = hass.data[DOMAIN].get("ip")
        if remote_ip is None:
            return True
        try:
            parsed_data = json.loads(json_data)
            parsed_data["tar"] = device
            parsed_data["dev"] = f"{DOMAIN}"
            parsed_data["pwr"] = 5

            hass.states.async_set(f"{DOMAIN}.status", "busy")
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
                    await loop.sock_sendto(
                        sock, encrypted_data, (remote_ip, multicast_port)
                    )
                _LOGGER.debug(
                    f"AIRTUB: Sending JSON cmd to:{multicast_group} port:{multicast_port} with data:{parsed_data}"
                )
                hass.states.async_set(
                    f"{DOMAIN}.status", "ready"
                )  # 不管对方是否收到，都应当设置为ready
            except OSError as e:
                _LOGGER.error(f"AIRTUB: OS error occurred while sending data: {e}")
            except socket.gaierror as e:
                _LOGGER.error(
                    f"AIRTUB: Socket address error occurred while sending data: {e}"
                )

        except json.JSONDecodeError as e:
            _LOGGER.debug(f"AIRTUB: Error decoding JSON: {e}")
            hass.states.async_set(f"{DOMAIN}.status", "error")

    async def handle_data_received_event(event):
        """Handle the event when data is received."""
        _LOGGER.debug("UDP data received, starting sensor and climate setup.")
        try:
            await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
            await hass.config_entries.async_forward_entry_setups(entry, ["climate"])
        except Exception as e:
            _LOGGER.error(f"Error setting up platforms: {e}")
        hass.states.async_set(f"{DOMAIN}.status", "ready")

    try:
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN] = {"device": device, "data": {}, "ip": None}

        hass.loop.create_task(
            udp_listener(hass, multicast_group, multicast_port, secret, device)
        )
        
        hass.services.async_register(
            DOMAIN,
            SERVICE_RECEIVE_JSON,
            handle_json_service,
            schema=SERVICE_RECEIVE_JSON_SCHEMA,
        )
        

        # Register the event listener
        hass.bus.async_listen_once(EVENT_NEW_DATA, handle_data_received_event)

        

    except Exception as e:
        _LOGGER.error(f"Error during setup: {e}")
        return False

    return True


async def async_unload_entry(hass, entry):
    """Unload Airtub UDP config entry."""
    
    hass.services.async_remove(DOMAIN, SERVICE_RECEIVE_JSON)
    
    entity_id = f"{DOMAIN}.status"
    if hass.states.get(entity_id):
        hass.states.async_remove(entity_id)
        _LOGGER.debug(f"Removed entity: {entity_id}")
    else:
        _LOGGER.debug(f"No entity found with ID: {entity_id}")
        
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["climate", "sensor"])

    # If all platforms were successfully unloaded, remove the entry data.
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

        # Check if the domain is now empty, and if so, remove it.
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)

    return unload_ok