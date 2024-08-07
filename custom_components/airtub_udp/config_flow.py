import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import config_entry_flow, config_validation as cv
from homeassistant.const import CONF_DEVICE, CONF_PASSWORD, CONF_MODE
from .const import DOMAIN
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor

_LOGGER = logging.getLogger(__name__)


@config_entries.HANDLERS.register(DOMAIN)
class AirtubUDPConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Airtub UDP."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self._errors = {}
        self._nane = "Airtub UDP Config Flow"
        self._unique_id = "airtub_udp_config_flow"

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        await self.async_set_unique_id(self._unique_id)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            device = user_input[CONF_DEVICE]
            password = user_input[CONF_PASSWORD]
            mode = user_input[CONF_MODE]

            # Save the password to secrets.yaml
            secrets_path = self.hass.config.path("secrets.yaml")
            secrets, original_lines = await self.hass.async_add_executor_job(
                self._read_secrets, secrets_path
            )
            secrets["airtub_password"] = password
            await self.hass.async_add_executor_job(
                self._write_secrets, secrets_path, secrets, original_lines
            )

            # Update configuration.yaml
            config_path = self.hass.config.path("configuration.yaml")
            await self.hass.async_add_executor_job(
                self._update_config, config_path, device, mode
            )

            return self.async_create_entry(title="Airtub UDP", data=user_input)

        return self._show_config_form(user_input)

    @staticmethod
    def _read_secrets(secrets_path):
        secrets = {}
        original_lines = []
        if os.path.exists(secrets_path):
            with open(secrets_path, "r") as secrets_file:
                for line in secrets_file:
                    original_lines.append(line)
                    stripped_line = line.strip()
                    if ": " in stripped_line:
                        key, value = stripped_line.split(": ", 1)
                        secrets[key] = value
        return secrets, original_lines

    @staticmethod
    def _write_secrets(secrets_path, secrets, original_lines):
        with open(secrets_path, "w") as secrets_file:
            keys_written = set()
            for line in original_lines:
                stripped_line = line.strip()
                if ": " in stripped_line:
                    key, _ = stripped_line.split(": ", 1)
                    if key in secrets:
                        secrets_file.write(f"{key}: {secrets[key]}\n")
                        keys_written.add(key)
                    else:
                        secrets_file.write(line)
                else:
                    secrets_file.write(line)
            # 写入新的键值对
            for key, value in secrets.items():
                if key not in keys_written:
                    secrets_file.write(f"{key}: {value}\n")

    @staticmethod
    def _update_config(config_path, device, mode):
        if os.path.exists(config_path):
            with open(config_path, "r") as config_file:
                lines = config_file.readlines()

            with open(config_path, "w") as config_file:
                inside_airtub_config = False
                previous_line_was_empty = False
                for line in lines:
                    if line.strip() == "# ----airtub-start----":
                        inside_airtub_config = True
                        continue
                    elif line.strip() == "# ----airtub-stop----":
                        inside_airtub_config = False
                        continue
                    if inside_airtub_config:
                        continue

                    if line.strip() == "":
                        if previous_line_was_empty:
                            continue
                        previous_line_was_empty = True
                    else:
                        previous_line_was_empty = False

                    config_file.write(line)

                config_file.write("\n# ----airtub-start----\n")
                config_file.write(f"\n{DOMAIN}:\n")
                config_file.write(f"  device: {device}\n")
                config_file.write("  secret: !secret airtub_password\n")
                config_file.write("\nclimate:\n")
                config_file.write(f"  - platform: {DOMAIN}\n")
                config_file.write(f"    operate: {mode}\n")
                config_file.write("\n# ----airtub-stop----\n")

    @callback
    def _show_config_form(self, user_input):
        """Show the configuration form to edit config data."""
        if user_input is None:
            user_input = {}
        data_schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE, default=user_input.get(CONF_DEVICE, "")): str,
                vol.Required(
                    CONF_PASSWORD, default=user_input.get(CONF_PASSWORD, "")
                ): str,
                vol.Optional(CONF_MODE, default=user_input.get(CONF_MODE, "auto")): str,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=self._errors
        )

    async def async_remove(self):
        """Remove a config entry."""
        _LOGGER.debug(f"AIRTUB: remove config")
        config_path = self.hass.config.path("configuration.yaml")
        await self.hass.async_add_executor_job(self._remove_config, config_path)

    @staticmethod
    def _remove_config(config_path):
        _LOGGER.debug(f"AIRTUB: delete airtub config from {config_path}")
        if os.path.exists(config_path):
            with open(config_path, "r") as file:
                lines = file.readlines()

            with open(config_path, "w") as file:
                inside_airtub_config = False
                for line in lines:
                    if line.strip() == "# ----airtub-start----":
                        inside_airtub_config = True
                        continue
                    elif line.strip() == "# ----airtub-stop----":
                        inside_airtub_config = False
                        continue
                    if not inside_airtub_config:
                        file.write(line)
        else:
            _LOGGER.debug(f"AIRTUB: Configuration file {config_path} does not exist")

    @property
    def name(self):
        """Return the name of the config flow."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._unique_id
