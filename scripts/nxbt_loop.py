#!/usr/bin/env python3
"""
NXBT New Loop - Uses the hold state API for persistent button/stick holds.

This script manages controller input using the new hold state layer. It continuously
sends frames at 120Hz with apply_hold_state(), interpreting hold/release commands
from config files.

Config file format (new modal):
  hold <button>         # Hold button down
  release <button>      # Release button
  hold_stick <stick> <x> <y>  # Hold stick at position
  release_stick <stick> # Release stick
  0.5s                  # Sleep for duration (hold state persists during sleep)

Example conversion from old format:
  Old: B 0.2s
  New: hold B
       0.2s
       release B

Modes:
  - manual: Wait for commands via stdin or FIFO
  - mode a: Run init_new.txt once, then loop loop_new.txt repeatedly
  - mode b: Loop loop_new.txt repeatedly (no init)
  - mode c: Run init_new.txt once, then return to manual

Manual mode commands:
  - hold <button>: Hold button (e.g., "hold x")
  - release [button]: Release button or all buttons
  - hold_stick <stick> <x> <y>: Hold stick position
  - release_stick [stick]: Release stick or all sticks
  - mode <manual|a|b|c>: Change operating mode
  - status: Show current mode
  - quit: Exit program
"""

import os
import sys
import time
import select
import errno
import stat
import nxbt


# --- configuration ---
INIT_FILE = "/opt/nxbt/config/init.txt"
LOOP_FILE = "/opt/nxbt/config/loop.txt"
SLEEP_BETWEEN_LOOPS = 2.0  # seconds
FIFO_PATH = "/tmp/nxbt_cmd"  # external control pipe
FRAME_RATE = 120  # Hz for Pro Controller

HELP_BANNER = """
Available commands (type directly or echo into /tmp/nxbt_cmd):

  mode manual      # stop everything and wait for commands
  mode a           # run init.txt once, then loop loop.txt repeatedly
  mode b           # loop loop.txt repeatedly (no init)
  mode c           # run init.txt once, then return to manual

Manual mode commands (new format):
  hold <button>         # example: hold x
  release [button]      # example: release x (or just: release)
  hold_stick <stick> <x> <y>  # example: hold_stick L_STICK 0 100
  release_stick [stick] # example: release_stick L_STICK (or just: release_stick)
  
  status           # show current mode and state
  quit             # exit program
""".strip()


def read_commands(path):
    """Read non-empty, non-comment lines from a text file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
    except FileNotFoundError:
        print(f"[!] File not found: {path}")
        return []


def ensure_fifo(path):
    """Ensure a named pipe exists and open both ends."""
    try:
        st = os.stat(path)
        if not stat.S_ISFIFO(st.st_mode):
            os.remove(path)
            os.mkfifo(path, 0o600)
    except FileNotFoundError:
        os.mkfifo(path, 0o600)
    rfd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    wfd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
    return rfd, wfd


def parse_sleep_time(line):
    """Parse sleep time from format like '0.5s' or '1.2s'."""
    line = line.strip()
    if line.endswith('s') and line[:-1].replace('.', '', 1).replace('-', '', 1).isdigit():
        return float(line[:-1])
    return None


def exec_config_command(nx, cid, line, tag=""):
    """Execute a command from config file in new modal format.
    
    Returns (action, sleep_time):
        action: 'hold_button', 'release_button', 'hold_stick', 'release_stick', 'sleep', 'unknown'
        sleep_time: float or None
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return 'skip', None
    
    # Check if it's a sleep command
    sleep_time = parse_sleep_time(line)
    if sleep_time is not None:
        return 'sleep', sleep_time
    
    parts = line.split(maxsplit=1)
    cmd = parts[0].lower()
    
    try:
        # Handle button holds
        if cmd == "hold":
            if len(parts) < 2:
                print(f"[!] Invalid hold command: {line}")
                return 'unknown', None
            button = parts[1].strip()
            print(f"[{tag}] Holding button: {button}")
            nx.hold_buttons(cid, [button])
            return 'hold_button', None
        
        # Handle button releases
        elif cmd == "release":
            if len(parts) < 2:
                print(f"[{tag}] Releasing all buttons")
                nx.release_buttons(cid)
            else:
                button = parts[1].strip()
                print(f"[{tag}] Releasing button: {button}")
                nx.release_buttons(cid, [button])
            return 'release_button', None
        
        # Handle stick holds
        elif cmd == "hold_stick":
            if len(parts) < 2:
                print(f"[!] Invalid hold_stick command: {line}")
                return 'unknown', None
            stick_parts = parts[1].split()
            if len(stick_parts) < 3:
                print(f"[!] Invalid hold_stick command, need: hold_stick <stick> <x> <y>")
                return 'unknown', None
            stick = stick_parts[0]
            x = int(stick_parts[1])
            y = int(stick_parts[2])
            print(f"[{tag}] Holding stick {stick} at ({x}, {y})")
            nx.hold_stick(cid, stick, x, y)
            return 'hold_stick', None
        
        # Handle stick releases
        elif cmd == "release_stick":
            if len(parts) < 2:
                print(f"[{tag}] Releasing all sticks")
                nx.release_stick(cid)
            else:
                stick = parts[1].strip()
                print(f"[{tag}] Releasing stick: {stick}")
                nx.release_stick(cid, stick)
            return 'release_stick', None
        
        else:
            print(f"[!] Unknown command: {line}")
            return 'unknown', None
            
    except Exception as e:
        print(f"[!] Error executing '{line}': {e}")
        return 'error', None


def main():
    print("[*] Starting NXBT controller with hold state support (new modal)…")
    nx = nxbt.Nxbt()
    cid = nx.create_controller(nxbt.PRO_CONTROLLER)
    print(f"[+] Controller created (id {cid}), waiting for connection…")
    nx.wait_for_connection(cid)
    print("[✓] Switch connected!")
    print(HELP_BANNER)

    # State
    mode = "manual"
    init_cmds = read_commands(INIT_FILE)
    loop_cmds = read_commands(LOOP_FILE)
    ran_init = False
    should_quit = False

    fifo_rfd, fifo_wfd = ensure_fifo(FIFO_PATH)
    stdin_buf, fifo_buf = "", ""

    # Frame timing for continuous 120Hz sending
    frame_time = 1.0 / FRAME_RATE
    last_frame = time.perf_counter()

    def send_frame():
        """Send a frame with hold state applied at 120Hz."""
        nonlocal last_frame
        current_time = time.perf_counter()
        if (current_time - last_frame) >= frame_time:
            packet = nx.create_input_packet()
            packet = nx.apply_hold_state(cid, packet)
            nx.set_controller_input(cid, packet)
            last_frame = current_time
            return True
        return False

    def run_manual_command(line):
        """Process manual mode command."""
        nonlocal mode, should_quit, ran_init

        line = line.strip()
        if not line or line.startswith("#"):
            return

        parts = line.split(maxsplit=1)
        cmd = parts[0].lower()

        if cmd == "mode":
            if len(parts) < 2 or parts[1] not in ("manual", "a", "b", "c"):
                print("[!] Usage: mode manual|a|b|c")
                return
            new_mode = parts[1]
            print(f"[*] Changing mode → {new_mode}")
            mode = new_mode
            ran_init = False
            return

        elif cmd == "hold":
            if len(parts) < 2:
                print("[!] Usage: hold <button>")
                return
            button = parts[1].strip()
            nx.hold_buttons(cid, [button])
            print(f"[*] Holding: {button}")
            return

        elif cmd == "release":
            if len(parts) >= 2:
                button = parts[1].strip()
                nx.release_buttons(cid, [button])
                print(f"[*] Released: {button}")
            else:
                nx.release_buttons(cid)
                print(f"[*] Released all buttons")
            return

        elif cmd == "hold_stick":
            if len(parts) < 2:
                print("[!] Usage: hold_stick <stick> <x> <y>")
                return
            stick_parts = parts[1].split()
            if len(stick_parts) < 3:
                print("[!] Usage: hold_stick <stick> <x> <y>")
                return
            stick = stick_parts[0]
            x = int(stick_parts[1])
            y = int(stick_parts[2])
            nx.hold_stick(cid, stick, x, y)
            print(f"[*] Holding stick {stick} at ({x}, {y})")
            return

        elif cmd == "release_stick":
            if len(parts) >= 2:
                stick = parts[1].strip()
                nx.release_stick(cid, stick)
                print(f"[*] Released stick: {stick}")
            else:
                nx.release_stick(cid)
                print(f"[*] Released all sticks")
            return

        elif cmd == "status":
            print(f"[*] Mode={mode}, init={len(init_cmds)}, loop={len(loop_cmds)}")
            return

        elif cmd in ("quit", "exit"):
            print("[*] Quitting…")
            should_quit = True
            return

        else:
            print("[!] Invalid command. Use: mode, hold, release, hold_stick, release_stick, status, or quit.")

    def poll_inputs(timeout=0.001):
        """Check stdin and FIFO for commands."""
        nonlocal stdin_buf, fifo_buf
        rlist = []
        if sys.stdin and sys.stdin.isatty():
            rlist.append(sys.stdin)
        readable, _, _ = select.select(rlist + [fifo_rfd], [], [], timeout)
        for src in readable:
            if src == sys.stdin:
                chunk = sys.stdin.readline()
                if chunk:
                    stdin_buf += chunk
                    while "\n" in stdin_buf:
                        one, stdin_buf = stdin_buf.split("\n", 1)
                        run_manual_command(one)
            else:
                try:
                    chunk = os.read(fifo_rfd, 4096).decode("utf-8", errors="ignore")
                except OSError as e:
                    if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                        continue
                    else:
                        raise
                if chunk:
                    fifo_buf += chunk
                    while "\n" in fifo_buf:
                        one, fifo_buf = fifo_buf.split("\n", 1)
                        run_manual_command(one)

    def execute_sequence(commands, tag="seq"):
        """Execute a sequence of commands from config file."""
        nonlocal mode, should_quit
        
        for line in commands:
            # Check for mode changes or quit
            if mode == "manual" or should_quit:
                print(f"[!] Mode changed to manual or quit requested — stopping {tag}")
                return False
            
            # Poll for inputs
            poll_inputs(0.0)
            
            # Execute command
            action, sleep_time = exec_config_command(nx, cid, line, tag=tag)
            
            # Handle sleep while continuously sending frames
            if action == 'sleep' and sleep_time:
                end_time = time.perf_counter() + sleep_time
                while time.perf_counter() < end_time:
                    if mode == "manual" or should_quit:
                        return False
                    send_frame()
                    poll_inputs(0.001)
                    time.sleep(0.001)  # Small sleep to prevent tight loop
        
        return True

    try:
        while not should_quit:
            # Always send frames at 120Hz
            send_frame()
            
            # Poll for commands
            poll_inputs(0.001)

            if mode == "manual":
                time.sleep(0.001)
                continue

            # Refresh command files
            init_cmds = read_commands(INIT_FILE)
            loop_cmds = read_commands(LOOP_FILE)

            # --- Mode C: init only ---
            if mode == "c":
                print("[*] Running init sequence (mode c)…")
                if execute_sequence(init_cmds, tag="init"):
                    print("[*] Init complete. Returning to manual mode.")
                mode = "manual"
                continue

            # --- Mode A: init + loop ---
            if mode == "a" and not ran_init:
                print("[*] Running init sequence…")
                if execute_sequence(init_cmds, tag="init"):
                    ran_init = True
                else:
                    continue

            # --- Mode B: just loop ---
            # (mode b doesn't run init, just loops)

            # --- Loop section (A and B) ---
            if mode in ("a", "b") and loop_cmds:
                print("[*] Starting loop pass…")
                if not execute_sequence(loop_cmds, tag="loop"):
                    continue
                
                # Sleep between loop passes while sending frames
                print(f"[*] Sleeping {SLEEP_BETWEEN_LOOPS}s between loops…")
                end_time = time.perf_counter() + SLEEP_BETWEEN_LOOPS
                while time.perf_counter() < end_time:
                    if mode == "manual" or should_quit:
                        break
                    send_frame()
                    poll_inputs(0.001)
                    time.sleep(0.001)

    except KeyboardInterrupt:
        print("\n[!] Stopped by user")
    finally:
        try:
            os.close(fifo_rfd)
            os.close(fifo_wfd)
        except Exception:
            pass


if __name__ == "__main__":
    main()
