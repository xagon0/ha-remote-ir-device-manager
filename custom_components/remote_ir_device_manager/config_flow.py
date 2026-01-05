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
    CONF_DEVICE_TYPE,
    CONF_IR_BLASTER,
    COMMAND_TYPE_IR,
    COMMAND_TYPE_RF,
    DEVICE_TYPE_GENERIC,
    DEVICE_TYPE_LIGHT,
    DEVICE_TYPE_COVER,
    DEVICE_TYPE_FAN,
    DEVICE_TYPES,
    BRIGHTNESS_MODE_NONE,
    BRIGHTNESS_MODE_DISCRETE,
    BRIGHTNESS_MODE_RELATIVE,
    BRIGHTNESS_MODE_BOTH,
    DOMAIN,
)
from .storage import EntityConfig

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
        self._selected_command_name: str | None = None

    def _get_coordinator(self) -> "IRDeviceCoordinator":
        """Get the coordinator from hass.data."""
        from .coordinator import IRDeviceCoordinator

        coordinator: IRDeviceCoordinator = self.hass.data[DOMAIN][self._config_entry.entry_id]["coordinator"]
        return coordinator

    def _get_ir_blasters(self) -> dict[str, str]:
        """Get available IR blaster entities (excluding our own virtual remotes)."""
        from homeassistant.helpers import entity_registry as er

        blasters = {}
        entity_ids = self.hass.states.async_entity_ids("remote")

        # Get entity registry to filter out our own virtual remotes
        ent_reg = er.async_get(self.hass)

        for entity_id in entity_ids:
            # Skip entities created by this integration
            entry = ent_reg.async_get(entity_id)
            if entry and entry.platform == DOMAIN:
                continue

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
                "edit_command",
                "delete_command",
                "configure_device_type",
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

    async def async_step_command_added(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show menu after successfully adding a command."""
        coordinator = self._get_coordinator()
        device = coordinator.get_device(self._selected_device_id)

        if device is None:
            return self.async_create_entry(title="", data={})

        return self.async_show_menu(
            step_id="command_added",
            menu_options=["learn_command", "add_command_manual", "finish"],
            description_placeholders={"device_name": device.name},
        )

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Finish adding commands and exit."""
        return self.async_create_entry(title="", data={})

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

                        return await self.async_step_command_added()
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
                    return await self.async_step_command_added()
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

    async def async_step_edit_command(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle selecting a command to edit."""
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
                step_id="edit_command",
                data_schema=vol.Schema({}),
                errors=errors,
                description_placeholders={"device_name": device.name},
            )

        if user_input is not None:
            self._selected_command_name = user_input[CONF_COMMAND_NAME]
            return await self.async_step_edit_command_form()

        schema = vol.Schema(
            {
                vol.Required(CONF_COMMAND_NAME): vol.In(commands),
            }
        )

        return self.async_show_form(
            step_id="edit_command",
            data_schema=schema,
            errors=errors,
            description_placeholders={"device_name": device.name},
        )

    async def async_step_edit_command_form(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle editing a command's properties."""
        errors: dict[str, str] = {}
        coordinator = self._get_coordinator()
        device = coordinator.get_device(self._selected_device_id)

        if device is None:
            return await self.async_step_init()

        command = device.commands.get(self._selected_command_name.lower())
        if command is None:
            return await self.async_step_device_menu()

        if user_input is not None:
            new_icon = user_input.get("icon")
            try:
                await coordinator.async_update_command(
                    self._selected_device_id,
                    self._selected_command_name,
                    icon=new_icon,
                )
                self._selected_command_name = None
                return await self.async_step_device_menu()
            except Exception:
                _LOGGER.exception("Unexpected error updating command")
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Optional("icon", default=command.icon or ""): IconSelector(
                    IconSelectorConfig()
                ),
            }
        )

        return self.async_show_form(
            step_id="edit_command_form",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "device_name": device.name,
                "command_name": command.name,
            },
        )

    async def async_step_configure_device_type(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the device type (generic, light, cover, fan)."""
        errors: dict[str, str] = {}
        coordinator = self._get_coordinator()
        device = coordinator.get_device(self._selected_device_id)

        if device is None:
            return await self.async_step_init()

        if user_input is not None:
            device_type = user_input[CONF_DEVICE_TYPE]
            await coordinator.async_update_device_type(
                self._selected_device_id, device_type
            )
            # If not generic, proceed to entity configuration
            if device_type == DEVICE_TYPE_LIGHT:
                return await self.async_step_configure_light()
            elif device_type == DEVICE_TYPE_COVER:
                return await self.async_step_configure_cover()
            return await self.async_step_device_menu()

        schema = vol.Schema({
            vol.Required(CONF_DEVICE_TYPE, default=device.device_type): vol.In(DEVICE_TYPES)
        })

        return self.async_show_form(
            step_id="configure_device_type",
            data_schema=schema,
            errors=errors,
            description_placeholders={"device_name": device.name},
        )

    async def async_step_configure_light(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure light entity command mappings."""
        errors: dict[str, str] = {}
        coordinator = self._get_coordinator()
        device = coordinator.get_device(self._selected_device_id)

        if device is None:
            return await self.async_step_init()

        # Get list of available commands for selection
        commands = {"": "(Not configured)"}
        commands.update({cmd.name: cmd.name for cmd in device.commands.values()})

        light_config = device.entity_configs.get("light")
        current_mappings = light_config.command_mappings if light_config else {}
        current_options = light_config.options if light_config else {}

        if user_input is not None:
            # Build command mappings from user input
            mappings: dict[str, Any] = {}

            # Power commands
            if user_input.get("turn_on"):
                mappings["turn_on"] = user_input["turn_on"]
            if user_input.get("turn_off"):
                mappings["turn_off"] = user_input["turn_off"]

            # Brightness
            brightness_mode = user_input.get("brightness_mode", BRIGHTNESS_MODE_NONE)
            if brightness_mode in (BRIGHTNESS_MODE_DISCRETE, BRIGHTNESS_MODE_BOTH):
                # Parse comma-separated brightness level commands
                levels_str = user_input.get("brightness_levels", "")
                if levels_str:
                    levels = [l.strip() for l in levels_str.split(",") if l.strip()]
                    if levels:
                        mappings["brightness_levels"] = levels

            if brightness_mode in (BRIGHTNESS_MODE_RELATIVE, BRIGHTNESS_MODE_BOTH):
                if user_input.get("brightness_up"):
                    mappings["brightness_up"] = user_input["brightness_up"]
                if user_input.get("brightness_down"):
                    mappings["brightness_down"] = user_input["brightness_down"]

            # Color temp
            color_temp_mode = user_input.get("color_temp_mode", BRIGHTNESS_MODE_NONE)
            if color_temp_mode in (BRIGHTNESS_MODE_DISCRETE, BRIGHTNESS_MODE_BOTH):
                levels_str = user_input.get("color_temp_levels", "")
                if levels_str:
                    levels = [l.strip() for l in levels_str.split(",") if l.strip()]
                    if levels:
                        mappings["color_temp_levels"] = levels

            if color_temp_mode in (BRIGHTNESS_MODE_RELATIVE, BRIGHTNESS_MODE_BOTH):
                if user_input.get("color_temp_up"):
                    mappings["color_temp_up"] = user_input["color_temp_up"]
                if user_input.get("color_temp_down"):
                    mappings["color_temp_down"] = user_input["color_temp_down"]

            # Effects (nightlight)
            effects: dict[str, str] = {}
            if user_input.get("effect_nightlight"):
                effects["Nightlight"] = user_input["effect_nightlight"]
            if effects:
                mappings["effects"] = effects

            # Create or update config
            config = EntityConfig(
                entity_type="light",
                enabled=True,
                command_mappings=mappings,
                state=current_mappings.get("state", {"is_on": False, "brightness": 255, "color_temp_index": 2}),
                options={
                    "brightness_mode": brightness_mode,
                    "color_temp_mode": color_temp_mode,
                },
            )

            await coordinator.async_update_entity_config(
                self._selected_device_id, "light", config
            )

            return await self.async_step_device_menu()

        # Build form with current values
        current_brightness_levels = current_mappings.get("brightness_levels", [])
        current_color_temp_levels = current_mappings.get("color_temp_levels", [])
        current_effects = current_mappings.get("effects", {})

        schema = vol.Schema({
            vol.Optional("turn_on", default=current_mappings.get("turn_on", "")): vol.In(commands),
            vol.Optional("turn_off", default=current_mappings.get("turn_off", "")): vol.In(commands),
            vol.Optional("brightness_mode", default=current_options.get("brightness_mode", BRIGHTNESS_MODE_NONE)): vol.In({
                BRIGHTNESS_MODE_NONE: "No brightness control",
                BRIGHTNESS_MODE_DISCRETE: "Discrete levels",
                BRIGHTNESS_MODE_RELATIVE: "Up/Down buttons",
                BRIGHTNESS_MODE_BOTH: "Both",
            }),
            vol.Optional("brightness_levels", default=",".join(current_brightness_levels)): str,
            vol.Optional("brightness_up", default=current_mappings.get("brightness_up", "")): vol.In(commands),
            vol.Optional("brightness_down", default=current_mappings.get("brightness_down", "")): vol.In(commands),
            vol.Optional("color_temp_mode", default=current_options.get("color_temp_mode", BRIGHTNESS_MODE_NONE)): vol.In({
                BRIGHTNESS_MODE_NONE: "No color temp control",
                BRIGHTNESS_MODE_DISCRETE: "Discrete presets (cool to warm)",
                BRIGHTNESS_MODE_RELATIVE: "Warmer/Cooler buttons",
                BRIGHTNESS_MODE_BOTH: "Both",
            }),
            vol.Optional("color_temp_levels", default=",".join(current_color_temp_levels)): str,
            vol.Optional("color_temp_up", default=current_mappings.get("color_temp_up", "")): vol.In(commands),
            vol.Optional("color_temp_down", default=current_mappings.get("color_temp_down", "")): vol.In(commands),
            vol.Optional("effect_nightlight", default=current_effects.get("Nightlight", "")): vol.In(commands),
        })

        return self.async_show_form(
            step_id="configure_light",
            data_schema=schema,
            errors=errors,
            description_placeholders={"device_name": device.name},
        )

    async def async_step_configure_cover(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure cover entity command mappings."""
        errors: dict[str, str] = {}
        coordinator = self._get_coordinator()
        device = coordinator.get_device(self._selected_device_id)

        if device is None:
            return await self.async_step_init()

        # Get list of available commands for selection
        commands = {"": "(Not configured)"}
        commands.update({cmd.name: cmd.name for cmd in device.commands.values()})

        cover_config = device.entity_configs.get("cover")
        current_mappings = cover_config.command_mappings if cover_config else {}

        if user_input is not None:
            mappings: dict[str, str] = {}
            if user_input.get("open"):
                mappings["open"] = user_input["open"]
            if user_input.get("close"):
                mappings["close"] = user_input["close"]
            if user_input.get("stop"):
                mappings["stop"] = user_input["stop"]

            config = EntityConfig(
                entity_type="cover",
                enabled=True,
                command_mappings=mappings,
                state={"position": 50},
                options={"device_class": "shade"},
            )

            await coordinator.async_update_entity_config(
                self._selected_device_id, "cover", config
            )

            return await self.async_step_device_menu()

        schema = vol.Schema({
            vol.Optional("open", default=current_mappings.get("open", "")): vol.In(commands),
            vol.Optional("close", default=current_mappings.get("close", "")): vol.In(commands),
            vol.Optional("stop", default=current_mappings.get("stop", "")): vol.In(commands),
        })

        return self.async_show_form(
            step_id="configure_cover",
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
