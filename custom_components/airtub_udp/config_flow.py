import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_DEVICE, CONF_PASSWORD, CONF_MODE
from .const import DOMAIN

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
        await self.async_set_unique_id("airtub_udp_config_flow")
        self._abort_if_unique_id_configured()

        if user_input is not None:
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
                vol.Optional(CONF_MODE, default=user_input.get(CONF_MODE, "auto")): str,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=self._errors
        )

    def async_remove(self):
        """Remove a config entry."""
        entry = self.async_get_entry()

        if entry:
            self.hass.config_entries.async_remove(entry.entry_id)

    async def async_get_entry(self):
        """Get the current config entry."""
        current_entries = self.hass.config_entries.async_entries(DOMAIN)
        if current_entries:
            return current_entries[0]
        return None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Airtub UDP."""

    def __init__(self, config_entry):
        """Initialize the options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            # 当用户提交新的配置时，更新配置项
            return self.async_create_entry(title="Airtub UDP", data=user_input)

        # 这里定义选项表单
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_MODE,
                        default=self.config_entry.options.get(CONF_MODE, "auto"),
                    ): str,
                }
            ),
        )
