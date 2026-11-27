"""Airfit Airtub Partner integration."""

import asyncio
import binascii
import json
import logging
import socket
import struct
import zlib
from contextlib import suppress
from itertools import cycle

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE, CONF_MODE, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError

from .const import (
    DEFAULT_DATA,
    DOMAIN,
    EVENT_NEW_DATA,
    PLATFORMS,
    UDP_GROUP,
    UDP_PORT,
)

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


def xor_crypt(a: str, b: str):
    """XOR encode/decode."""
    return "".join(chr(ord(x) ^ ord(y)) for x, y in zip(a, cycle(b)))


def pack_data(msgtype: int, message: str, secret: str):
    """Encode data to send over UDP."""
    len_num = len(message)
    crypt_data = xor_crypt(message, secret).encode("ascii")
    crc = zlib.crc32(crypt_data).to_bytes(4, "little")
    if len_num > 180:
        raise ValueError("Airtub UDP payload exceeds 180 bytes")

    send_data = bytearray(struct.pack("BB2x", msgtype, len_num))
    send_data.extend(crc)
    send_data.extend(crypt_data)
    send_data.extend(bytearray(180 - len_num))
    return bytes(send_data)


def unpack_data(data: bytes, secret: str):
    """Decode data received from UDP."""
    if len(data) != 0:
        msgtype, datalen = struct.unpack("BB2x", data[:4])
        crc1 = binascii.hexlify(data[4:8][::-1]).decode()
        realdata = data[8 : datalen + 8]
        crc2 = f"{zlib.crc32(realdata):08x}"
        realdata = xor_crypt(realdata.decode("ascii"), secret).encode("ascii")
        return msgtype, datalen, realdata, crc1, crc2
    return 0, 0, b"", "", ""


async def udp_listener(
    hass: HomeAssistant,
    sock: socket.socket,
    secret: str,
    device: str,
):
    """Listen for UDP multicast messages."""
    runtime = hass.data[DOMAIN]
    loop = asyncio.get_running_loop()
    hass.states.async_set(f"{DOMAIN}.status", "waiting for data")

    try:
        while True:
            try:
                data, addr = await loop.sock_recvfrom(sock, 1024)
                if data:
                    _, _, realdata, crc1, crc2 = unpack_data(data, secret)
                    if crc1 != crc2:
                        await asyncio.sleep(0)
                        continue

                    data_dict = json.loads(realdata.decode("ascii"))
                    if not isinstance(data_dict, dict):
                        raise ValueError("UDP payload is not a JSON object")
                    if str(data_dict.get("dev", "")).lower() != device:
                        await asyncio.sleep(0)
                        continue

                    runtime["ip"] = addr[0]
                    if data_dict.get("rec"):
                        runtime["msg_received"] = True
                        hass.states.async_set(f"{DOMAIN}.status", "ready")
                        _LOGGER.debug("Airtub command acknowledged by %s", addr[0])
                        await asyncio.sleep(0)
                        continue

                    data_dict.pop("dev", None)
                    if "gas" in data_dict and data_dict["gas"] == 0:
                        data_dict["gas"] = 0.000001

                    runtime.setdefault("data", {}).update(data_dict)
                    hass.bus.async_fire(EVENT_NEW_DATA)
            except OSError as err:
                _LOGGER.error("Socket error: %s", err)
                await asyncio.sleep(1)
            except (
                json.JSONDecodeError,
                UnicodeDecodeError,
                struct.error,
                ValueError,
            ) as err:
                _LOGGER.warning("Invalid Airtub UDP data from %s: %s", addr[0], err)
            await asyncio.sleep(0)
    finally:
        sock.close()
        if runtime.get("sock") is sock:
            runtime["sock"] = None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Airtub UDP from a config entry."""
    device = entry.data[CONF_DEVICE].lower()
    secret = entry.data[CONF_PASSWORD]
    mode = entry.options.get(CONF_MODE, entry.data.get(CONF_MODE, "auto"))

    runtime = {
        "device": device,
        "mode": mode,
        "ip": None,
        "data": dict(DEFAULT_DATA),
        "msg_received": False,
        "command_lock": asyncio.Lock(),
        "sock": None,
        "udp_listen_task": None,
    }
    hass.data[DOMAIN] = runtime

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.bind(("0.0.0.0", UDP_PORT))
        mreq = struct.pack("=4sl", socket.inet_aton(UDP_GROUP), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 10)
        sock.setblocking(False)
    except OSError as err:
        sock.close()
        hass.data.pop(DOMAIN, None)
        raise ConfigEntryNotReady(f"Unable to open Airtub UDP listener: {err}") from err

    runtime["sock"] = sock
    udp_listen_task = None
    try:
        udp_listen_task = asyncio.create_task(
            udp_listener(hass, sock, secret, device),
            name=f"Airtub UDP listener {entry.entry_id}",
        )
        runtime["udp_listen_task"] = udp_listen_task

        async def handle_json_service(call):
            async with runtime["command_lock"]:
                json_data = call.data[ATTR_JSON_DATA]
                remote_ip = runtime.get("ip")
                current_sock = runtime.get("sock")
                if remote_ip is None or current_sock is None:
                    raise ServiceValidationError(
                        "Airtub device has not been discovered yet"
                    )

                try:
                    parsed_data = json.loads(json_data)
                except json.JSONDecodeError as err:
                    _LOGGER.warning("AIRTUB: Error decoding JSON: %s", err)
                    hass.states.async_set(f"{DOMAIN}.status", "error")
                    raise ServiceValidationError("cmd must be valid JSON") from err

                if not isinstance(parsed_data, dict):
                    raise ServiceValidationError("cmd must contain a JSON object")

                parsed_data.update({"tar": device, "dev": DOMAIN, "sta": 1})
                hass.states.async_set(f"{DOMAIN}.status", "busy")
                loop = asyncio.get_running_loop()
                retry = 0
                runtime["msg_received"] = False
                try:
                    while not runtime["msg_received"] and retry < RETRY_MAX:
                        parsed_data["try"] = retry
                        retry += 1
                        message = json.dumps(parsed_data, separators=(",", ":"))
                        if len(message) > 180:
                            hass.states.async_set(f"{DOMAIN}.status", "error")
                            raise ServiceValidationError(
                                "Airtub command exceeds the 180-byte UDP limit"
                            )
                        encrypted_data = pack_data(MSG_TYPE, message, secret)
                        destination = remote_ip if retry % 2 else UDP_GROUP
                        _LOGGER.debug(
                            "Sending Airtub command to %s:%s, attempt %s",
                            destination,
                            UDP_PORT,
                            retry,
                        )
                        await asyncio.sleep(1)
                        await loop.sock_sendto(
                            current_sock, encrypted_data, (destination, UDP_PORT)
                        )
                    if not runtime["msg_received"]:
                        _LOGGER.warning(
                            "Airtub command was not acknowledged after %s attempts",
                            retry,
                        )
                    hass.states.async_set(f"{DOMAIN}.status", "ready")
                except OSError as err:
                    _LOGGER.error("AIRTUB: Error occurred while sending data: %s", err)
                    hass.states.async_set(f"{DOMAIN}.status", "error")
                    raise

        hass.services.async_register(
            DOMAIN,
            SERVICE_RECEIVE_JSON,
            handle_json_service,
            schema=SERVICE_RECEIVE_JSON_SCHEMA,
        )
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        if udp_listen_task is not None:
            udp_listen_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await udp_listen_task
        sock.close()
        runtime["sock"] = None
        if hass.services.has_service(DOMAIN, SERVICE_RECEIVE_JSON):
            hass.services.async_remove(DOMAIN, SERVICE_RECEIVE_JSON)
        if hass.states.get(f"{DOMAIN}.status"):
            hass.states.async_remove(f"{DOMAIN}.status")
        hass.data.pop(DOMAIN, None)
        raise

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Airtub UDP config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    runtime = hass.data.get(DOMAIN, {})
    udp_listen_task = runtime.get("udp_listen_task")
    if udp_listen_task is not None:
        udp_listen_task.cancel()
        result = (await asyncio.gather(udp_listen_task, return_exceptions=True))[0]
        if isinstance(result, Exception):
            _LOGGER.warning("Airtub UDP listener stopped with an error: %s", result)

    sock = runtime.get("sock")
    if sock is not None:
        sock.close()
    runtime["sock"] = None

    if hass.services.has_service(DOMAIN, SERVICE_RECEIVE_JSON):
        hass.services.async_remove(DOMAIN, SERVICE_RECEIVE_JSON)

    entity_id = f"{DOMAIN}.status"
    if hass.states.get(entity_id):
        hass.states.async_remove(entity_id)

    hass.data.pop(DOMAIN, None)
    return True
