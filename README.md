# Remote IR Device Manager

A Home Assistant custom integration that provides a UI-driven workflow for managing IR remotes. Create virtual devices, learn IR commands, and control them as proper Home Assistant entities.

## Features

- **Universal IR Blaster Support**: Works with any IR blaster in Home Assistant (Broadlink, Tuya, Switchbot, etc.)
- **Virtual Device Creation**: Create named virtual remotes (e.g., "Living Room TV", "Toilet")
- **UI-Based Learning**: Learn IR commands directly from the Home Assistant UI
- **Button Entities**: Each learned command becomes a button entity you can use in dashboards and automations
- **Remote Entities**: Each virtual device also has a remote entity with all commands as activities
- **Services**: Full service support for automation (learn, add, delete, send commands)

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu → Custom repositories
3. Add this repository URL with category "Integration"
4. Search for "Remote IR Device Manager" and install
5. Restart Home Assistant
6. Go to Settings → Devices & Services → Add Integration → "Remote IR Device Manager"

### Manual

1. Copy the `custom_components/remote_ir_device_manager` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Go to Settings → Devices & Services → Add Integration → "Remote IR Device Manager"

## Usage

### Creating a Virtual Device

1. Go to Settings → Devices & Services
2. Find "Remote IR Device Manager" and click Configure
3. Select "Add new virtual device"
4. Choose your IR blaster and give it a name (e.g., "Toilet")

### Learning Commands

1. Configure the integration → Select "Manage existing device"
2. Choose your device → Select "Learn new command"
3. Enter a command name (e.g., "Power")
4. Point your physical remote at the IR blaster and press the button
5. The command is saved and a button entity is created

### Using Commands

- **Dashboard**: Add the button entities to your dashboard
- **Automations**: Use the `remote_ir_device_manager.send_command` service
- **Remote Entity**: Use `remote.send_command` with your virtual remote

## Services

### `remote_ir_device_manager.learn_command`
Trigger learning mode on an IR blaster.

### `remote_ir_device_manager.add_command`
Add a command with a base64-encoded IR code.

### `remote_ir_device_manager.delete_command`
Remove a learned command.

### `remote_ir_device_manager.send_command`
Send a learned IR command.

## Supported IR Blasters

### Full Support (Automatic Code Retrieval)
- **Broadlink** (RM4, RM Mini, etc.)

### Basic Support (Manual Code Input)
- Any integration that provides `remote.learn_command` and `remote.send_command` services
- Tuya IR blasters
- Switchbot Hub
- Others

## License

MIT
