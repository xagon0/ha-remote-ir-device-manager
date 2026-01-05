"""Light platform for Remote IR Device Manager."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_EFFECT,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, DEVICE_TYPE_LIGHT, BRIGHTNESS_MODE_NONE, COLOR_TEMP_PRESETS
from .storage import VirtualDevice, EntityConfig

if TYPE_CHECKING:
    from .coordinator import IRDeviceCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up light entities from a config entry."""
    coordinator: IRDeviceCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities: list[IRLight] = []

    for device in coordinator.devices.values():
        # Only create light entity if device type is light AND light config exists
        if device.device_type == DEVICE_TYPE_LIGHT and "light" in device.entity_configs:
            light_config = device.entity_configs["light"]
            if light_config.enabled:
                entities.append(
                    IRLight(
                        coordinator=coordinator,
                        virtual_device=device,
                        config=light_config,
                        entry=entry,
                    )
                )

    async_add_entities(entities)


class IRLight(LightEntity):
    """Light entity for an IR-controlled light."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: IRDeviceCoordinator,
        virtual_device: VirtualDevice,
        config: EntityConfig,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the light."""
        self._coordinator = coordinator
        self._virtual_device = virtual_device
        self._config = config
        self._entry = entry

        # Assumed state (IR is one-way)
        self._attr_assumed_state = True
        self._is_on: bool = config.state.get("is_on", False)
        self._brightness: int = config.state.get("brightness", 255)
        self._color_temp_index: int = config.state.get("color_temp_index", 2)  # Default neutral
        self._effect: str | None = config.state.get("effect")

        # Unique ID
        self._attr_unique_id = f"{entry.entry_id}_{virtual_device.id}_light"
        self._attr_name = None  # Use device name

        # Device info - same identifier as other entities for grouping
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{virtual_device.id}")},
            name=virtual_device.name,
            manufacturer="Remote IR Device Manager",
            model="Virtual IR Light",
            sw_version="1.0",
        )

        # Configure supported features based on command mappings
        self._setup_features()

    def _setup_features(self) -> None:
        """Configure supported features based on available commands."""
        mappings = self._config.command_mappings
        options = self._config.options

        # Start with ONOFF as base
        supported_color_modes: set[ColorMode] = {ColorMode.ONOFF}
        self._attr_color_mode = ColorMode.ONOFF

        # Check for brightness support
        brightness_mode = options.get("brightness_mode", BRIGHTNESS_MODE_NONE)
        has_brightness = (
            brightness_mode != BRIGHTNESS_MODE_NONE
            and (mappings.get("brightness_levels") or mappings.get("brightness_up"))
        )

        if has_brightness:
            supported_color_modes.add(ColorMode.BRIGHTNESS)
            self._attr_color_mode = ColorMode.BRIGHTNESS

        # Check for color temp support
        has_color_temp = bool(
            mappings.get("color_temp_levels") or mappings.get("color_temp_up")
        )

        if has_color_temp:
            supported_color_modes.add(ColorMode.COLOR_TEMP)
            self._attr_color_mode = ColorMode.COLOR_TEMP
            # Set min/max color temp in mireds
            # 153 mireds = ~6500K (cool), 500 mireds = ~2000K (warm)
            self._attr_min_color_temp_kelvin = 2000
            self._attr_max_color_temp_kelvin = 6500

        self._attr_supported_color_modes = supported_color_modes

        # Check for effect support
        features = LightEntityFeature(0)
        effects = mappings.get("effects", {})
        if effects:
            features |= LightEntityFeature.EFFECT
            self._attr_effect_list = list(effects.keys())

        self._attr_supported_features = features

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Check if the IR blaster entity is available
        state = self._coordinator.hass.states.get(
            self._virtual_device.ir_blaster_entity_id
        )
        if state is None:
            return True
        return state.state != "unavailable"

    @property
    def is_on(self) -> bool:
        """Return True if light is on."""
        return self._is_on

    @property
    def brightness(self) -> int | None:
        """Return current brightness (1-255)."""
        if ColorMode.BRIGHTNESS in self._attr_supported_color_modes:
            return self._brightness
        return None

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return color temperature in Kelvin."""
        if ColorMode.COLOR_TEMP not in self._attr_supported_color_modes:
            return None
        return self._index_to_kelvin(self._color_temp_index)

    @property
    def effect(self) -> str | None:
        """Return current effect."""
        return self._effect

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        mappings = self._config.command_mappings

        # If light is off, turn it on first
        if not self._is_on:
            cmd = mappings.get("turn_on") or mappings.get("toggle")
            if cmd:
                await self._send_command(cmd)
            self._is_on = True

        # Handle brightness change
        if ATTR_BRIGHTNESS in kwargs:
            target_brightness = kwargs[ATTR_BRIGHTNESS]
            await self._set_brightness(target_brightness)
            self._brightness = target_brightness

        # Handle color temp change
        if ATTR_COLOR_TEMP in kwargs:
            # ATTR_COLOR_TEMP is in mireds, convert to kelvin
            target_kelvin = kwargs[ATTR_COLOR_TEMP]
            await self._set_color_temp_kelvin(target_kelvin)

        # Handle effect
        if ATTR_EFFECT in kwargs:
            effect_name = kwargs[ATTR_EFFECT]
            await self._set_effect(effect_name)
            self._effect = effect_name

        await self._save_state()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        mappings = self._config.command_mappings
        cmd = mappings.get("turn_off") or mappings.get("toggle")
        if cmd:
            await self._send_command(cmd)

        self._is_on = False
        self._effect = None
        await self._save_state()
        self.async_write_ha_state()

    async def _set_brightness(self, target_brightness: int) -> None:
        """Set brightness to target level (1-255)."""
        mappings = self._config.command_mappings
        options = self._config.options
        brightness_mode = options.get("brightness_mode", "discrete")

        levels = mappings.get("brightness_levels", [])

        if brightness_mode in ("discrete", "both") and levels:
            # Map 1-255 to discrete levels
            num_levels = len(levels)
            # Calculate target level index (0-based)
            target_index = round((target_brightness - 1) / 254 * (num_levels - 1))
            target_index = max(0, min(target_index, num_levels - 1))

            # Send the discrete level command
            cmd = levels[target_index]
            await self._send_command(cmd)

        elif brightness_mode == "relative":
            # Use up/down commands - this is approximate
            up_cmd = mappings.get("brightness_up")
            down_cmd = mappings.get("brightness_down")
            step_size = options.get("brightness_step_size", 25)

            if up_cmd and down_cmd:
                diff = target_brightness - self._brightness
                steps = round(abs(diff) / step_size)

                if diff > 0:
                    for _ in range(steps):
                        await self._send_command(up_cmd)
                elif diff < 0:
                    for _ in range(steps):
                        await self._send_command(down_cmd)

    async def _set_color_temp_kelvin(self, target_kelvin: int) -> None:
        """Set color temperature."""
        mappings = self._config.command_mappings
        levels = mappings.get("color_temp_levels", [])

        if levels:
            # Map Kelvin to discrete preset index
            num_levels = len(levels)
            # 6500K (cool) = index 0, 2000K (warm) = last index
            kelvin_range = self._attr_max_color_temp_kelvin - self._attr_min_color_temp_kelvin
            # Invert because higher Kelvin = cooler = lower index
            normalized = (self._attr_max_color_temp_kelvin - target_kelvin) / kelvin_range
            target_index = round(normalized * (num_levels - 1))
            target_index = max(0, min(target_index, num_levels - 1))

            cmd = levels[target_index]
            await self._send_command(cmd)
            self._color_temp_index = target_index

        elif mappings.get("color_temp_up") and mappings.get("color_temp_down"):
            # Use relative adjustment (less precise)
            current_kelvin = self._index_to_kelvin(self._color_temp_index)
            diff = target_kelvin - current_kelvin
            step_size = 500  # Kelvin per step

            steps = round(abs(diff) / step_size)
            if diff > 0:  # Cooler (higher Kelvin)
                for _ in range(steps):
                    await self._send_command(mappings["color_temp_up"])
            elif diff < 0:  # Warmer (lower Kelvin)
                for _ in range(steps):
                    await self._send_command(mappings["color_temp_down"])

    def _index_to_kelvin(self, index: int) -> int:
        """Convert color temp index to Kelvin."""
        levels = self._config.command_mappings.get("color_temp_levels", [])
        if not levels:
            return 4000  # Default neutral

        num_levels = len(levels)
        if num_levels == 1:
            return 4000

        # Index 0 = 6500K (cool), last index = 2000K (warm)
        kelvin_range = self._attr_max_color_temp_kelvin - self._attr_min_color_temp_kelvin
        return int(self._attr_max_color_temp_kelvin - (index / (num_levels - 1)) * kelvin_range)

    async def _set_effect(self, effect_name: str) -> None:
        """Activate an effect."""
        mappings = self._config.command_mappings
        effects = mappings.get("effects", {})

        if effect_name in effects:
            cmd = effects[effect_name]
            await self._send_command(cmd)

    async def _send_command(self, command_name: str) -> None:
        """Send an IR command."""
        await self._coordinator.async_send_command(
            self._virtual_device.id,
            command_name,
        )

    async def _save_state(self) -> None:
        """Persist assumed state to storage."""
        self._config.state["is_on"] = self._is_on
        self._config.state["brightness"] = self._brightness
        self._config.state["color_temp_index"] = self._color_temp_index
        self._config.state["effect"] = self._effect
        await self._coordinator.async_save_entity_state(
            self._virtual_device.id, "light", self._config.state
        )
