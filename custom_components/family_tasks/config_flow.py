"""Config flow: one click, nothing to fill in. Options: who gets approval pushes."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import CONF_NOTIFY, DOMAIN, NAME


class FamilyTasksConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add the Family Task Card Integration."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title=NAME, data={})
        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> FamilyTasksOptionsFlow:
        return FamilyTasksOptionsFlow()


class FamilyTasksOptionsFlow(OptionsFlow):
    """Pick the notify services (parents' phones) for reward approvals."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        targets = sorted(self.hass.services.async_services_for_domain("notify"))
        current = [t for t in self.config_entry.options.get(CONF_NOTIFY, []) if t in targets]
        schema = vol.Schema(
            {
                vol.Optional(CONF_NOTIFY, default=current): SelectSelector(
                    SelectSelectorConfig(
                        options=targets, multiple=True, mode=SelectSelectorMode.LIST
                    )
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
