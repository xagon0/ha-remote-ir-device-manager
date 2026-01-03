"""Config flow for Remote IR Device Manager."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import IconSelector, IconSelectorConfig

from .const import (
    CONF_COMMAND_CODE,
    CONF_COMMAND_NAME,
    CONF_COMMAND_TYPE,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_IR_BLASTER,
    COMMAND_TYPE_IR,
    COMMAND_TYPE_RF,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class RemoteIRDeviceManagerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Remote IR Device Manager."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        # Only allow one instance
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(
                title="Remote IR Device Manager",
                data={},
            )

        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlow:
        """Get the options flow for this handler."""
        return RemoteIRDeviceManagerOptionsFlow(config_entry)


class RemoteIRDeviceManagerOptionsFlow(OptionsFlow):
    """Handle options flow for Remote IR Device Manager."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self._selected_device_id: str | None = None

    def _get_coordinator(self) -> "IRDeviceCoordinator":
        """Get the coordinator from hass.data."""
        from .coordinator import IRDeviceCoordinator

        coordinator: IRDeviceCoordinator = self.hass.data[DOMAIN][self._config_entry.entry_id]["coordinator"]
        return coordinator

    def _get_ir_blasters(self) -> dict[str, str]:
        """Get available IR blaster entities."""
        blasters = {}
        entity_ids = self.hass.states.async_entity_ids("remote")

        for entity_id in entity_ids:
            state = self.hass.states.get(entity_id)
            if state:
                friendly_name = state.attributes.get("friendly_name", entity_id)
                blasters[entity_id] = friendly_name

        return blasters

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial options step - show menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_device", "manage_device", "delete_device"],
        )

    async def async_step_add_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle adding a new virtual device."""
        errors: dict[str, str] = {}

        ir_blasters = self._get_ir_blasters()
        if not ir_blasters:
            errors["base"] = "no_ir_blasters"
            return self.async_show_form(
                step_id="add_device",
                data_schema=vol.Schema({}),
                errors=errors,
            )

        if user_input is not None:
            coordinator = self._get_coordinator()

            # Check if name already exists
            if coordinator.get_device_by_name(user_input[CONF_DEVICE_NAME]):
                errors[CONF_DEVICE_NAME] = "device_name_exists"
            else:
                try:
                    await coordinator.async_add_device(
                        name=user_input[CONF_DEVICE_NAME],
                        ir_blaster_entity_id=user_input[CONF_IR_BLASTER],
                    )
                    return self.async_create_entry(title="", data={})
                except HomeAssistantError as err:
                    _LOGGER.error("Failed to add device: %s", err)
                    errors["base"] = "unknown"
                except Exception:
                    _LOGGER.exception("Unexpected error adding device")
                    errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_NAME): str,
                vol.Required(CONF_IR_BLASTER): vol.In(ir_blasters),
            }
        )

        return self.async_show_form(
            step_id="add_device",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_manage_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle selecting a device to manage."""
        errors: dict[str, str] = {}
        coordinator = self._get_coordinator()

        devices = {
            device.id: device.name
            for device in coordinator.devices.values()
        }

        if not devices:
            errors["base"] = "no_devices"
            return self.async_show_form(
                step_id="manage_device",
                data_schema=vol.Schema({}),
                errors=errors,
            )

        if user_input is not None:
            self._selected_device_id = user_input[CONF_DEVICE_ID]
            return await self.async_step_device_menu()

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): vol.In(devices),
            }
        )

        return self.async_show_form(
            step_id="manage_device",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_device_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show menu for managing a specific device."""
        coordinator = self._get_coordinator()
        device = coordinator.get_device(self._selected_device_id)

        if device is None:
            return await self.async_step_init()

        return self.async_show_menu(
            step_id="device_menu",
            menu_options=[
                "learn_command",
                "add_command_manual",
                "delete_command",
                "back",
            ],
            description_placeholders={"device_name": device.name},
        )

    async def async_step_back(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Go back to main menu."""
        self._selected_device_id = None
        return await self.async_step_init()

    async def async_step_learn_command(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle learning a new command."""
        errors: dict[str, str] = {}
        coordinator = self._get_coordinator()
        device = coordinator.get_device(self._selected_device_id)

        if device is None:
            return await self.async_step_init()

        if user_input is not None:
            command_name = user_input[CONF_COMMAND_NAME]
            command_type = user_input.get(CONF_COMMAND_TYPE, COMMAND_TYPE_IR)
            icon = user_input.get("icon")

            # Check for duplicate command
            if command_name.lower() in device.commands:
                errors[CONF_COMMAND_NAME] = "command_name_exists"
            else:
                try:
                    result = await coordinator.async_learn_command(
                        self._selected_device_id,
                        command_name,
                        command_type,
                        timeout=30,
                    )

                    if result:
                        # Update icon if provided
                        if icon and result.icon != icon:
                            await coordinator.async_update_command(
                                self._selected_device_id, command_name, icon=icon
                            )

                        return self.async_create_entry(title="", data={})
                    else:
                        # Learning succeeded but code retrieval failed
                        # Redirect to manual input with pre-filled name
                        return await self.async_step_add_command_manual(
                            user_input={
                                CONF_COMMAND_NAME: command_name,
                                CONF_COMMAND_TYPE: command_type,
                                "icon": icon or "",
                                "_prefilled": True,
                            }
                        )
                except HomeAssistantError as err:
                    _LOGGER.error("Learning failed: %s", err)
                    if "timeout" in str(err).lower():
                        errors["base"] = "learn_timeout"
                    else:
                        errors["base"] = "learn_failed"
                except Exception:
                    _LOGGER.exception("Unexpected error during learning")
                    errors["base"] = "learn_failed"

        schema = vol.Schema(
            {
                vol.Required(CONF_COMMAND_NAME): str,
                vol.Optional(CONF_COMMAND_TYPE, default=COMMAND_TYPE_IR): vol.In(
                    {COMMAND_TYPE_IR: "IR (Infrared)", COMMAND_TYPE_RF: "RF (Radio Frequency)"}
                ),
                vol.Optional("icon"): IconSelector(IconSelectorConfig()),
            }
        )

        return self.async_show_form(
            step_id="learn_command",
            data_schema=schema,
            errors=errors,
            description_placeholders={"device_name": device.name},
        )

    async def async_step_add_command_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle adding a command manually with base64 code."""
        errors: dict[str, str] = {}
        coordinator = self._get_coordinator()
        device = coordinator.get_device(self._selected_device_id)

        if device is None:
            return await self.async_step_init()

        # Check if this is a prefilled redirect from learn_command
        # Use .get() to avoid mutating the original dict
        prefilled = user_input.get("_prefilled", False) if user_input else False
        if prefilled and user_input:
            # Create a copy without the internal key for processing
            user_input = {k: v for k, v in user_input.items() if k != "_prefilled"}

        if user_input is not None and not prefilled:
            command_name = user_input[CONF_COMMAND_NAME]
            code = user_input[CONF_COMMAND_CODE]
            command_type = user_input.get(CONF_COMMAND_TYPE, COMMAND_TYPE_IR)
            icon = user_input.get("icon")

            # Check for duplicate command
            if command_name.lower() in device.commands:
                errors[CONF_COMMAND_NAME] = "command_name_exists"
            else:
                try:
                    await coordinator.async_add_command(
                        self._selected_device_id,
                        command_name,
                        code,
                        command_type,
                        icon,
                    )
                    return self.async_create_entry(title="", data={})
                except HomeAssistantError as err:
                    _LOGGER.error("Failed to add command: %s", err)
                    if "base64" in str(err).lower():
                        errors[CONF_COMMAND_CODE] = "invalid_code"
                    else:
                        errors["base"] = "unknown"
                except Exception:
                    _LOGGER.exception("Unexpected error adding command")
                    errors["base"] = "unknown"

        # Build schema with prefilled values if available
        defaults = user_input or {}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_COMMAND_NAME,
                    default=defaults.get(CONF_COMMAND_NAME, ""),
                ): str,
                vol.Required(CONF_COMMAND_CODE): str,
                vol.Optional(
                    CONF_COMMAND_TYPE,
                    default=defaults.get(CONF_COMMAND_TYPE, COMMAND_TYPE_IR),
                ): vol.In(
                    {COMMAND_TYPE_IR: "IR (Infrared)", COMMAND_TYPE_RF: "RF (Radio Frequency)"}
                ),
                vol.Optional("icon"): IconSelector(IconSelectorConfig()),
            }
        )

        return self.async_show_form(
            step_id="add_command_manual",
            data_schema=schema,
            errors=errors,
            description_placeholders={"device_name": device.name},
        )

    async def async_step_delete_command(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle deleting a command."""
        errors: dict[str, str] = {}
        coordinator = self._get_coordinator()
        device = coordinator.get_device(self._selected_device_id)

        if device is None:
            return await self.async_step_init()

        commands = {
            cmd.name: f"{cmd.name} ({cmd.command_type.upper()})"
            for cmd in device.commands.values()
        }

        if not commands:
            errors["base"] = "no_commands"
            return self.async_show_form(
                step_id="delete_command",
                data_schema=vol.Schema({}),
                errors=errors,
                description_placeholders={"device_name": device.name},
            )

        if user_input is not None:
            command_name = user_input[CONF_COMMAND_NAME]
            try:
                await coordinator.async_delete_command(
                    self._selected_device_id,
                    command_name,
                )
                return self.async_create_entry(title="", data={})
            except HomeAssistantError as err:
                _LOGGER.error("Failed to delete command: %s", err)
                errors["base"] = "unknown"
            except Exception:
                _LOGGER.exception("Unexpected error deleting command")
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(CONF_COMMAND_NAME): vol.In(commands),
            }
        )

        return self.async_show_form(
            step_id="delete_command",
            data_schema=schema,
            errors=errors,
            description_placeholders={"device_name": device.name},
        )

    async def async_step_delete_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle deleting a virtual device."""
        errors: dict[str, str] = {}
        coordinator = self._get_coordinator()

        devices = {
            device.id: f"{device.name} ({len(device.commands)} commands)"
            for device in coordinator.devices.values()
        }

        if not devices:
            errors["base"] = "no_devices"
            return self.async_show_form(
                step_id="delete_device",
                data_schema=vol.Schema({}),
                errors=errors,
            )

        if user_input is not None:
            device_id = user_input[CONF_DEVICE_ID]
            try:
                await coordinator.async_remove_device(device_id)
                return self.async_create_entry(title="", data={})
            except HomeAssistantError as err:
                _LOGGER.error("Failed to delete device: %s", err)
                errors["base"] = "unknown"
            except Exception:
                _LOGGER.exception("Unexpected error deleting device")
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): vol.In(devices),
            }
        )

        return self.async_show_form(
            step_id="delete_device",
            data_schema=schema,
            errors=errors,
        )
