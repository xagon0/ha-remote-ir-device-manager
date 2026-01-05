"""Constants for the Remote IR Device Manager integration."""

from typing import Final

DOMAIN: Final = "remote_ir_device_manager"

# Config keys
CONF_IR_BLASTER: Final = "ir_blaster_entity_id"
CONF_VIRTUAL_DEVICES: Final = "virtual_devices"
CONF_COMMANDS: Final = "commands"
CONF_COMMAND_NAME: Final = "command_name"
CONF_COMMAND_CODE: Final = "code"
CONF_COMMAND_TYPE: Final = "command_type"
CONF_DEVICE_ID: Final = "device_id"
CONF_DEVICE_NAME: Final = "device_name"
CONF_DEVICE_TYPE: Final = "device_type"

# Command types
COMMAND_TYPE_IR: Final = "ir"
COMMAND_TYPE_RF: Final = "rf"

# Device types
DEVICE_TYPE_GENERIC: Final = "generic"
DEVICE_TYPE_LIGHT: Final = "light"
DEVICE_TYPE_COVER: Final = "cover"
DEVICE_TYPE_FAN: Final = "fan"

DEVICE_TYPES: Final = {
    DEVICE_TYPE_GENERIC: "Generic (buttons only)",
    DEVICE_TYPE_LIGHT: "Light",
    DEVICE_TYPE_COVER: "Cover (blinds, projector screen)",
    DEVICE_TYPE_FAN: "Fan",
}

# Light-specific constants
BRIGHTNESS_MODE_NONE: Final = "none"
BRIGHTNESS_MODE_DISCRETE: Final = "discrete"
BRIGHTNESS_MODE_RELATIVE: Final = "relative"
BRIGHTNESS_MODE_BOTH: Final = "both"

COLOR_TEMP_PRESETS: Final = ["cool", "daylight", "neutral", "warm_white", "warm"]

# Defaults
DEFAULT_LEARN_TIMEOUT: Final = 30

# Platforms
PLATFORMS: Final = ["button", "remote", "light", "cover"]

# Storage
STORAGE_VERSION: Final = 2
STORAGE_KEY: Final = DOMAIN
