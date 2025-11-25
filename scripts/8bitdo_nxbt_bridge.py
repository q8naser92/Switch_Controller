#!/usr/bin/env python3
import os
import time
from typing import Optional

from evdev import InputDevice, list_devices, ecodes


# --------- CONFIG ---------

# Name reported by the controller (from /proc/bus/input/devices)
TARGET_NAME_SUBSTRING = "8BitDo Ultimate Wireless / Pro 2 Wired Controller"

# Where NXBT reads commands from (FIFO or file, e.g. your /tmp/cmd)
CMD_PATH = "/tmp/nxbt_cmd"

# Stick normalization / deadzone
STICK_DEADZONE = 10  # in [-100..100] normalized coords

# Trigger: treat analog axis as "pressed" if above this
TRIGGER_THRESHOLD = 200  # tune if needed


# Map EV_KEY codes -> NXBT button names for hold/release commands
BUTTON_MAP = {
    ecodes.BTN_SOUTH: "B",         # 304
    ecodes.BTN_EAST:  "A",         # 305
    ecodes.BTN_NORTH: "Y",         # 308
    ecodes.BTN_WEST:  "X",         # 307

    ecodes.BTN_TL:    "L",
    ecodes.BTN_TR:    "R",
    # Triggers handled via ABS_Z / ABS_RZ as ZL/ZR (digital), so we don't map BTN_TL2 / BTN_TR2

    ecodes.BTN_SELECT: "MINUS",    # 314
    ecodes.BTN_START:  "PLUS",     # 315
    ecodes.BTN_MODE:   "HOME",     # 316

    ecodes.BTN_THUMBL: "L_STICK_PRESS",  # left stick click
    # ecodes.BTN_THUMBR is *not* here – we use it as P1/P2 mode toggle
}


def find_8bitdo_device() -> Optional[InputDevice]:
    """Return the InputDevice for the 8BitDo controller, or None if not found."""
    for path in list_devices():
        try:
            dev = InputDevice(path)
            if TARGET_NAME_SUBSTRING in dev.name:
                return dev
        except Exception:
            continue
    return None


def normalize_axis(raw: int) -> int:
    """
    Map raw axis (usually [-32768..32767]) to [-100..100].
    """
    if raw >= 32767:
        return 100
    if raw <= -32768:
        return -100
    norm = int(round(raw / 32767.0 * 100))
    return max(-100, min(100, norm))


# Keep a persistent writer across calls
_NXBT_FD = None
_NXBT_FILE = None

def _open_nxbt_writer():
    """
    Open the FIFO in blocking mode and keep it open.
    This will block until NXBT opens the FIFO for reading.
    """
    global _NXBT_FD, _NXBT_FILE

    while True:
        try:
            print(f"[NXBT-BRIDGE] Waiting for NXBT reader on {CMD_PATH}...", flush=True)
            fd = os.open(CMD_PATH, os.O_WRONLY)  # BLOCKING open
            f = os.fdopen(fd, "w", buffering=1)  # line-buffered
            _NXBT_FD = fd
            _NXBT_FILE = f
            print(f"[NXBT-BRIDGE] Connected to NXBT via {CMD_PATH}", flush=True)
            return
        except FileNotFoundError:
            print(f"[NXBT-BRIDGE] {CMD_PATH} does not exist yet, retrying in 1s...", flush=True)
            time.sleep(1)
        except OSError as e:
            # ENXIO = no reader on FIFO
            print(f"[NXBT-BRIDGE] Failed to open {CMD_PATH} for write ({e}), retrying in 1s...", flush=True)
            time.sleep(1)

def send_to_nxbt(cmd: str):
    """
    Send a single command line to NXBT via CMD_PATH and also print it.
    Keeps the FIFO open persistently and reconnects on BrokenPipe.
    """
    global _NXBT_FILE

    line = cmd.strip()
    if not line:
        return

    print(f"[NXBT] {line}", flush=True)
    line = line + "\n"

    if _NXBT_FILE is None:
        _open_nxbt_writer()

    try:
        _NXBT_FILE.write(line)
        _NXBT_FILE.flush()
    except (BrokenPipeError, OSError) as e:
        # Reader disappeared (NXBT restarted or crashed). Reconnect.
        print(f"[NXBT-BRIDGE] Pipe error while sending '{cmd}': {e}. Reconnecting...", flush=True)
        try:
            _NXBT_FILE.close()
        except Exception:
            pass
        _NXBT_FILE = None
        _open_nxbt_writer()
        # Try once more
        try:
            _NXBT_FILE.write(line)
            _NXBT_FILE.flush()
        except Exception as e2:
            print(f"[NXBT-BRIDGE] Failed again sending '{cmd}' after reconnect: {e2}", flush=True)

def main():
    print("[*] 8BitDo → NXBT bridge starting...", flush=True)
    print(f"    Target device name contains: '{TARGET_NAME_SUBSTRING}'", flush=True)
    print(f"    NXBT command path: {CMD_PATH}", flush=True)

    # ---- MODE STATE (persists across disconnects) ----
    #
    # We want:
    #   First RS-click (P1/P2) => mode manual
    #   Second RS-click       => mode b
    #   Third                 => mode manual
    #   ...
    #
    # Easiest way: start as if we are on "b".
    current_mode = "b"

    while True:
        # ---- Wait for controller ----
        dev = None
        while dev is None:
            dev = find_8bitdo_device()
            if dev is None:
                print("[*] Waiting for 8BitDo controller...", flush=True)
                time.sleep(0.5)
            else:
                print(f"[+] Detected 8BitDo device: {dev.name} at {dev.path}", flush=True)

        # ---- Grab device to keep it awake ----
        try:
            dev.grab()
            print(f"[+] Grabbing {dev.path} to keep controller awake...", flush=True)
        except Exception as e:
            print(f"[!] Failed to grab {dev.path}: {e}", flush=True)
            time.sleep(1)
            continue

        print("[✓] Device grabbed. Listening for input events...", flush=True)
        print(f"[STATE] Current mode (before any P1/P2 press) is '{current_mode}'", flush=True)

        # ---- State ----
        left_raw_x = 0
        left_raw_y = 0
        right_raw_x = 0
        right_raw_y = 0

        left_norm = {"x": 0, "y": 0}
        right_norm = {"x": 0, "y": 0}

        dpad_state = {
            "left": False,
            "right": False,
            "up": False,
            "down": False,
        }

        # Triggers: digital behavior via analog axis
        zl_pressed = False
        zr_pressed = False

        button_state = {}

        try:
            for event in dev.read_loop():
                if event.type == ecodes.EV_SYN:
                    continue

                code = event.code
                value = event.value

                # ---------- Digital buttons ----------
                if event.type == ecodes.EV_KEY:
                    # Use Right Stick Button (BTN_THUMBR) as P1/P2 mode toggle
                    if code == ecodes.BTN_THUMBR:
                        if value != 0:  # only on press, ignore release
                            # Toggle mode
                            new_mode = "manual" if current_mode == "b" else "b"
                            print(
                                f"[TOGGLE] RS-click detected -> switching mode "
                                f"from '{current_mode}' to '{new_mode}'",
                                flush=True,
                            )
                            current_mode = new_mode
                            send_to_nxbt(f"mode {current_mode}")
                        continue  # don't treat it as a normal button

                    # Normal buttons
                    if code in BUTTON_MAP:
                        btn_name = BUTTON_MAP[code]
                        pressed = value != 0

                        prev = button_state.get(btn_name, False)
                        if pressed == prev:
                            # no state change
                            continue
                        button_state[btn_name] = pressed

                        action = "hold" if pressed else "release"
                        cmd = f"{action} {btn_name}"
                        print(
                            f"[INPUT] Button {'pressed' if pressed else 'released'}: "
                            f"{btn_name} (code={code}) -> {cmd}",
                            flush=True,
                        )
                        send_to_nxbt(cmd)
                    else:
                        if value != 0:
                            print(f"[DEBUG] Unknown button code={code} value={value}", flush=True)

                # ---------- Analog (sticks, dpad, triggers) ----------
                elif event.type == ecodes.EV_ABS:
                    # D-Pad (hat)
                    if code == ecodes.ABS_HAT0X:
                        # value: -1 (left), 0 (center), 1 (right)
                        if value == -1:
                            new_left = True
                            new_right = False
                        elif value == 1:
                            new_left = False
                            new_right = True
                        else:
                            new_left = False
                            new_right = False

                        if new_left != dpad_state["left"]:
                            dpad_state["left"] = new_left
                            action = "hold" if new_left else "release"
                            cmd = f"{action} DPAD_LEFT"
                            print(f"[DPAD] {action.upper()} LEFT -> {cmd}", flush=True)
                            send_to_nxbt(cmd)

                        if new_right != dpad_state["right"]:
                            dpad_state["right"] = new_right
                            action = "hold" if new_right else "release"
                            cmd = f"{action} DPAD_RIGHT"
                            print(f"[DPAD] {action.upper()} RIGHT -> {cmd}", flush=True)
                            send_to_nxbt(cmd)

                        continue

                    if code == ecodes.ABS_HAT0Y:
                        # value: -1 (up), 0 (center), 1 (down)
                        if value == -1:
                            new_up = True
                            new_down = False
                        elif value == 1:
                            new_up = False
                            new_down = True
                        else:
                            new_up = False
                            new_down = False

                        if new_up != dpad_state["up"]:
                            dpad_state["up"] = new_up
                            action = "hold" if new_up else "release"
                            cmd = f"{action} DPAD_UP"
                            print(f"[DPAD] {action.upper()} UP -> {cmd}", flush=True)
                            send_to_nxbt(cmd)

                        if new_down != dpad_state["down"]:
                            dpad_state["down"] = new_down
                            action = "hold" if new_down else "release"
                            cmd = f"{action} DPAD_DOWN"
                            print(f"[DPAD] {action.upper()} DOWN -> {cmd}", flush=True)
                            send_to_nxbt(cmd)

                        continue

                    # -------- Triggers as digital (ZL / ZR) --------
                    if code == ecodes.ABS_Z:
                        # Left trigger (ZL)
                        now_pressed = value > TRIGGER_THRESHOLD
                        if now_pressed != zl_pressed:
                            zl_pressed = now_pressed
                            action = "hold" if now_pressed else "release"
                            cmd = f"{action} ZL"
                            print(
                                f"[TRIGGER] {action.upper()} ZL (ABS_Z={value}) -> {cmd}",
                                flush=True,
                            )
                            send_to_nxbt(cmd)
                        continue

                    if code == ecodes.ABS_RZ:
                        # Right trigger (ZR)
                        now_pressed = value > TRIGGER_THRESHOLD
                        if now_pressed != zr_pressed:
                            zr_pressed = now_pressed
                            action = "hold" if now_pressed else "release"
                            cmd = f"{action} ZR"
                            print(
                                f"[TRIGGER] {action.upper()} ZR (ABS_RZ={value}) -> {cmd}",
                                flush=True,
                            )
                            send_to_nxbt(cmd)
                        continue

                    # -------- Sticks: left & right --------
                    # Left stick
                    if code == ecodes.ABS_X:
                        left_raw_x = value
                    elif code == ecodes.ABS_Y:
                        left_raw_y = value
                    # Right stick
                    elif code == ecodes.ABS_RX:
                        right_raw_x = value
                    elif code == ecodes.ABS_RY:
                        right_raw_y = value
                    else:
                        axis_name = ecodes.ABS.get(code, f"ABS_{code}")
                        print(f"[ANALOG] {axis_name} moved to {value}", flush=True)
                        continue

                    # --- Normalize and send for LEFT stick ---
                    new_lx = normalize_axis(left_raw_x)
                    new_ly_raw = normalize_axis(left_raw_y)
                    new_ly = -new_ly_raw  # invert so up is +100

                    if new_lx != left_norm["x"] or new_ly != left_norm["y"]:
                        left_norm["x"] = new_lx
                        left_norm["y"] = new_ly

                        if abs(new_lx) <= STICK_DEADZONE and abs(new_ly) <= STICK_DEADZONE:
                            cmd = "release_stick L_STICK"
                            print(f"[STICK] L_STICK released (center)", flush=True)
                            send_to_nxbt(cmd)
                        else:
                            cmd = f"hold_stick L_STICK {new_lx} {new_ly}"
                            print(f"[STICK] L_STICK -> {new_lx}, {new_ly} -> {cmd}", flush=True)
                            send_to_nxbt(cmd)

                    # --- Normalize and send for RIGHT stick ---
                    new_rx = normalize_axis(right_raw_x)
                    new_ry_raw = normalize_axis(right_raw_y)
                    new_ry = -new_ry_raw

                    if new_rx != right_norm["x"] or new_ry != right_norm["y"]:
                        right_norm["x"] = new_rx
                        right_norm["y"] = new_ry

                        if abs(new_rx) <= STICK_DEADZONE and abs(new_ry) <= STICK_DEADZONE:
                            cmd = "release_stick R_STICK"
                            print(f"[STICK] R_STICK released (center)", flush=True)
                            send_to_nxbt(cmd)
                        else:
                            cmd = f"hold_stick R_STICK {new_rx} {new_ry}"
                            print(f"[STICK] R_STICK -> {new_rx}, {new_ry} -> {cmd}", flush=True)
                            send_to_nxbt(cmd)

                else:
                    # Other event types – ignore for now
                    pass

        except (OSError, IOError) as e:
            print(f"[!] Device disconnected or read error: {e}", flush=True)
        except KeyboardInterrupt:
            print("[*] KeyboardInterrupt – exiting bridge loop.", flush=True)
            try:
                dev.ungrab()
            except Exception:
                pass
            return
        finally:
            try:
                dev.ungrab()
                print("[*] Device ungrabbed.", flush=True)
            except Exception:
                pass

        print("[*] Waiting for controller to reconnect...", flush=True)
        time.sleep(1)


if __name__ == "__main__":
    main()
