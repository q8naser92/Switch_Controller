# NXBT Hold State Layer

This document describes the hold state layer added to NXBT, which allows buttons and sticks to be held persistently across frames without needing to re-specify them in macros.

## Overview

The hold state layer is a non-intrusive addition to NXBT that sits on top of the existing input system. It provides:

1. **Persistent button holds** - Mark buttons as "held" and they remain pressed until explicitly released
2. **Persistent stick positions** - Set stick positions that persist across frames
3. **Frame-by-frame control** - Manually control input packets at ~120Hz for Pro Controller

## Key Features

- **Non-breaking**: Existing NXBT functionality remains unchanged
- **Flexible**: Mix held inputs with momentary inputs in the same frame
- **Simple API**: Intuitive methods following NXBT conventions
- **Thread-safe**: Works with NXBT's multiprocessing architecture

## API Reference

### Button Control

#### `hold_buttons(controller_index, buttons)`
Mark one or more buttons as held down until released.

**Parameters:**
- `controller_index` (int): The index of the controller
- `buttons` (list): List of button names to hold (e.g., `["x", "a", "b"]`)

**Example:**
```python
nx.hold_buttons(idx, ["x", "a"])  # Hold X and A buttons
```

#### `release_buttons(controller_index, buttons=None)`
Release one or more held buttons, or all buttons if `buttons` is None.

**Parameters:**
- `controller_index` (int): The index of the controller
- `buttons` (list or None): List of button names to release, or None for all

**Example:**
```python
nx.release_buttons(idx, ["x"])    # Release just X
nx.release_buttons(idx)           # Release all buttons
```

### Stick Control

#### `hold_stick(controller_index, stick, x, y, pressed=False)`
Hold a stick at a specific position.

**Parameters:**
- `controller_index` (int): The index of the controller
- `stick` (str): "L_STICK" or "R_STICK"
- `x` (int): X-axis position (-100 to 100)
- `y` (int): Y-axis position (-100 to 100)
- `pressed` (bool): Whether the stick press button is held (default: False)

**Example:**
```python
nx.hold_stick(idx, "L_STICK", 0, 100)      # Hold stick up
nx.hold_stick(idx, "R_STICK", 50, -50)     # Hold stick diagonal
nx.hold_stick(idx, "L_STICK", 0, 0, True)  # Hold stick centered and pressed
```

#### `release_stick(controller_index, stick=None)`
Release a held stick, or all sticks if `stick` is None.

**Parameters:**
- `controller_index` (int): The index of the controller
- `stick` (str or None): "L_STICK" or "R_STICK", or None for all sticks

**Example:**
```python
nx.release_stick(idx, "L_STICK")  # Release left stick
nx.release_stick(idx)             # Release all sticks
```

### Packet Management

#### `apply_hold_state(controller_index, packet)`
Apply held inputs to an input packet.

**Parameters:**
- `controller_index` (int): The index of the controller
- `packet` (dict): The input packet to modify (from `create_input_packet()`)

**Returns:**
- `dict`: The modified packet with hold state applied

**Example:**
```python
packet = nx.create_input_packet()
packet = nx.apply_hold_state(idx, packet)
nx.set_controller_input(idx, packet)
```

## Supported Buttons

All standard Nintendo Switch controller buttons are supported:

- **Face buttons**: `"x"`, `"y"`, `"a"`, `"b"`
- **Triggers**: `"l"`, `"r"`, `"zl"`, `"zr"`
- **D-pad**: `"dpad_up"`, `"dpad_down"`, `"dpad_left"`, `"dpad_right"`
- **System buttons**: `"home"`, `"plus"`, `"minus"`, `"capture"`
- **Joy-Con shoulder buttons**: `"jcl_sr"`, `"jcl_sl"`, `"jcr_sr"`, `"jcr_sl"`

Button names are case-insensitive.

## Usage Examples

### Example 1: Basic Button Hold

```python
import time
import nxbt

nx = nxbt.Nxbt()
idx = nx.create_controller(nxbt.PRO_CONTROLLER)
nx.wait_for_connection(idx)

# Start holding X button
nx.hold_buttons(idx, ["x"])

try:
    while True:
        # Create and send frames at 120Hz
        packet = nx.create_input_packet()
        packet = nx.apply_hold_state(idx, packet)
        nx.set_controller_input(idx, packet)
        time.sleep(1 / 120.0)

except KeyboardInterrupt:
    # Release when done
    nx.release_buttons(idx, ["x"])
```

### Example 2: Stick Movement

```python
import time
import nxbt

nx = nxbt.Nxbt()
idx = nx.create_controller(nxbt.PRO_CONTROLLER)
nx.wait_for_connection(idx)

# Hold stick forward
nx.hold_stick(idx, "L_STICK", 0, 100)

try:
    # Run for 5 seconds
    start = time.time()
    while time.time() - start < 5.0:
        packet = nx.create_input_packet()
        packet = nx.apply_hold_state(idx, packet)
        nx.set_controller_input(idx, packet)
        time.sleep(1 / 120.0)
finally:
    nx.release_stick(idx)
```

### Example 3: Combined Inputs

```python
import time
import nxbt

nx = nxbt.Nxbt()
idx = nx.create_controller(nxbt.PRO_CONTROLLER)
nx.wait_for_connection(idx)

# Hold B button and move stick right
nx.hold_buttons(idx, ["b"])
nx.hold_stick(idx, "L_STICK", 100, 0)

try:
    for i in range(600):  # 5 seconds at 120Hz
        packet = nx.create_input_packet()
        packet = nx.apply_hold_state(idx, packet)
        
        # Can still add momentary inputs
        if i == 300:  # Halfway through
            packet["A"] = True
        
        nx.set_controller_input(idx, packet)
        time.sleep(1 / 120.0)
finally:
    nx.release_buttons(idx)
    nx.release_stick(idx)
```

## New Scripts

### `nxbt_new_loop.py`

A new loop script that demonstrates the hold state API in action. It supports:

- **Modes**: manual, a, b, c (same as original `nxbt_loop.py`)
- **Commands via FIFO** (`/tmp/nxbt_cmd`) or stdin:
  - `hold <buttons>` - Hold buttons
  - `release [buttons]` - Release buttons
  - `hold_stick <stick> <x> <y> [pressed]` - Hold stick
  - `release_stick [stick]` - Release stick
  - `send <macro>` - Send traditional macro
  - `mode <mode>` - Change mode
  - `status` - Show status
  - `quit` - Exit

**Usage:**
```bash
# Run with Python
python3 /opt/nxbt/scripts/nxbt_new_loop.py

# Send commands via FIFO
echo "hold x a" > /tmp/nxbt_cmd
echo "hold_stick L_STICK 0 100" > /tmp/nxbt_cmd
echo "release" > /tmp/nxbt_cmd
```

### `hold_state_examples.py`

Example script demonstrating three different use cases:
1. Holding buttons persistently
2. Holding stick positions
3. Combining held buttons and sticks

**Usage:**
```bash
python3 /opt/nxbt/scripts/hold_state_examples.py
```

## Configuration Files

### `init_new.txt` and `loop_new.txt`

New configuration files that support hold state commands:

```
# Hold state commands
hold_stick L_STICK 0 100
hold x a
release_stick L_STICK
release

# Traditional macros still work
A 0.3s
0.4s
B 0.2s
```

## Design Philosophy

The hold state layer is designed to:

1. **Not change existing behavior** - All existing NXBT code continues to work unchanged
2. **Be optional** - You can use NXBT without ever using hold state
3. **Be composable** - Mix held inputs with momentary inputs in the same frame
4. **Be efficient** - Hold state is stored separately and applied only when needed
5. **Be simple** - Clear, intuitive API following NXBT conventions

## Implementation Details

- Hold state is stored in `_held_inputs` dictionary in the `Nxbt` class
- Each controller has its own hold state with `buttons` (set) and `sticks` (dict)
- `apply_hold_state()` merges hold state into a packet without modifying the original hold state
- Button names are normalized to lowercase for case-insensitive matching
- Stick positions are clamped to valid ranges (-100 to 100)

## Thread Safety

The hold state layer maintains NXBT's thread-safety:

- Hold state is stored locally in the `Nxbt` instance (not shared across processes)
- Hold state operations check `manager_state` to ensure controller exists
- No modifications to existing multiprocessing architecture

## Migration Guide

**From traditional macros:**

Before:
```python
# Need to repeat in a loop
while True:
    nx.macro(idx, "X 0.1s")
    nx.macro(idx, "0.1s")
```

After:
```python
# Hold once, send frames
nx.hold_buttons(idx, ["x"])
while True:
    packet = nx.create_input_packet()
    packet = nx.apply_hold_state(idx, packet)
    nx.set_controller_input(idx, packet)
    time.sleep(1 / 120.0)
```

## Limitations

- Hold state is per-controller and not shared across controllers
- Hold state is not persisted across `Nxbt` instance restarts
- Stick positions are in percentage (-100 to 100), not raw calibration values
- Frame rate must be maintained manually by the calling code

## Contributing

When adding new buttons or sticks, update `_HOLD_BUTTON_KEY_MAP` to include the mapping from lowercase name to packet key.

## License

Same license as NXBT (MIT).
