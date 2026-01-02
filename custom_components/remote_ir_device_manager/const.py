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

# Command types
COMMAND_TYPE_IR: Final = "ir"
COMMAND_TYPE_RF: Final = "rf"

# Defaults
DEFAULT_LEARN_TIMEOUT: Final = 30

# Platforms
PLATFORMS: Final = ["button", "remote"]

# Storage
STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = DOMAIN
