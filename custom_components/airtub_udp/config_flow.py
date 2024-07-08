import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import config_entry_flow, config_validation as cv
from homeassistant.const import CONF_DEVICE, CONF_PASSWORD
from .const import DOMAIN
import os

_LOGGER = logging.getLogger(__name__)


@config_entries.HANDLERS.register(DOMAIN)
class AirtubUDPConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Airtub UDP."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self._errors = {}

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            device = user_input[CONF_DEVICE]
            password = user_input[CONF_PASSWORD]

            # Save the password to secrets.yaml
            secrets_path = self.hass.config.path("secrets.yaml")
            secrets = {}
            if os.path.exists(secrets_path):
                with open(secrets_path, "r") as secrets_file:
                    for line in secrets_file:
                        key, value = line.strip().split(": ", 1)
                        secrets[key] = value

            secrets["airtub_password"] = password

            with open(secrets_path, "w") as secrets_file:
                for key, value in secrets.items():
                    secrets_file.write(f"{key}: {value}\n")

            # Update configuration.yaml
            config_path = self.hass.config.path("configuration.yaml")
            with open(config_path, "a") as config_file:
                config_file.write(f"\n{DOMAIN}:\n")
                config_file.write(f'  multicast_group: "224.0.1.3"\n')
                config_file.write(f"  multicast_port: 4211\n")
                config_file.write(f"  device: {device}\n")
                config_file.write(f"  secret: !secret airtub_password\n")
                config_file.write(f"\nclimate:\n")
                config_file.write(f"  - platform: {DOMAIN}\n")
                config_file.write(f"    operate: auto\n")

            return self.async_create_entry(title="Airtub UDP", data=user_input)

        return self._show_config_form(user_input)

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
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=self._errors
        )
