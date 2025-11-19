#!/usr/bin/env python3
"""
NXBT New Loop - Uses the hold state API for persistent button/stick holds.

This script manages controller input using the new hold state layer, which allows
buttons and sticks to be held persistently across frames without needing to
continuously re-specify them in macros.

Modes:
  - manual: Wait for commands via stdin or FIFO
  - mode a: Run init.txt once, then loop loop.txt repeatedly
  - mode b: Loop loop.txt repeatedly (no init)
  - mode c: Run init.txt once, then return to manual

Commands:
  - hold <buttons>: Start holding buttons (e.g., "hold x a")
  - release [buttons]: Release buttons (or all if no buttons specified)
  - hold_stick <stick> <x> <y> [pressed]: Hold stick position (e.g., "hold_stick L_STICK 0 100")
  - release_stick [stick]: Release stick (or all sticks if not specified)
  - send <macro>: Send traditional macro command
  - mode <manual|a|b|c>: Change operating mode
  - status: Show current mode and configuration
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
INIT_FILE = "/opt/nxbt/config/init_new.txt"
LOOP_FILE = "/opt/nxbt/config/loop_new.txt"
SLEEP_BETWEEN_LOOPS = 2.0  # seconds
FIFO_PATH = "/tmp/nxbt_cmd"  # external control pipe
FRAME_RATE = 120  # Hz for Pro Controller

HELP_BANNER = """
Available commands (type directly or echo into /tmp/nxbt_cmd):

  mode manual      # stop everything and wait for commands
  mode a           # run init.txt once, then loop.txt repeatedly
  mode b           # loop loop.txt repeatedly (no init)
  mode c           # run init.txt once, then return to manual

  hold <buttons>   # example: hold x a b
  release [btns]   # example: release x (or just: release)
  hold_stick <stick> <x> <y> [pressed]  # example: hold_stick L_STICK 0 100
  release_stick [stick]  # example: release_stick L_STICK (or just: release_stick)
  
  send <macros>    # example: send A 0.3s, B 0.3s
  status           # show current mode and line counts
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


def exec_command(nx, cid, line, tag=""):
    """Execute a command from config file (could be hold/release or traditional macro)."""
    try:
        line = line.strip()
        if not line or line.startswith("#"):
            return True
            
        parts = line.split(maxsplit=1)
        cmd = parts[0].lower()
        
        # Handle hold state commands
        if cmd == "hold" and len(parts) >= 2:
            buttons = parts[1].split()
            print(f"[{tag}] Holding buttons: {buttons}")
            nx.hold_buttons(cid, buttons)
            return True
            
        elif cmd == "release":
            if len(parts) >= 2:
                buttons = parts[1].split()
                print(f"[{tag}] Releasing buttons: {buttons}")
                nx.release_buttons(cid, buttons)
            else:
                print(f"[{tag}] Releasing all buttons")
                nx.release_buttons(cid)
            return True
            
        elif cmd == "hold_stick" and len(parts) >= 2:
            stick_parts = parts[1].split()
            if len(stick_parts) >= 3:
                stick = stick_parts[0]
                x = int(stick_parts[1])
                y = int(stick_parts[2])
                pressed = bool(stick_parts[3].lower() == "true") if len(stick_parts) > 3 else False
                print(f"[{tag}] Holding stick {stick} at ({x}, {y}), pressed={pressed}")
                nx.hold_stick(cid, stick, x, y, pressed)
                return True
            
        elif cmd == "release_stick":
            if len(parts) >= 2:
                stick = parts[1]
                print(f"[{tag}] Releasing stick: {stick}")
                nx.release_stick(cid, stick)
            else:
                print(f"[{tag}] Releasing all sticks")
                nx.release_stick(cid)
            return True
        
        # Otherwise, treat as traditional macro
        print(f"[{tag}] {line}" if tag else f"{line}")
        nx.macro(cid, line)
        return True
        
    except Exception as e:
        print(f"[!] Error executing '{line}': {e}")
        return False


def main():
    print("[*] Starting NXBT controller with hold state support…")
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
    
    # Track if we're in loop mode to send frames
    in_loop_mode = False

    fifo_rfd, fifo_wfd = ensure_fifo(FIFO_PATH)
    stdin_buf, fifo_buf = "", ""

    def run_line(line):
        """Process one command line."""
        nonlocal mode, ran_init, should_quit, in_loop_mode

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
            in_loop_mode = (mode in ("a", "b"))
            return

        elif cmd == "hold":
            if len(parts) < 2 or not parts[1].strip():
                print("[!] Usage: hold <button1> [button2 ...]")
                return
            buttons = parts[1].split()
            nx.hold_buttons(cid, buttons)
            print(f"[*] Holding: {buttons}")
            return

        elif cmd == "release":
            if len(parts) >= 2:
                buttons = parts[1].split()
                nx.release_buttons(cid, buttons)
                print(f"[*] Released: {buttons}")
            else:
                nx.release_buttons(cid)
                print(f"[*] Released all buttons")
            return

        elif cmd == "hold_stick":
            if len(parts) < 2:
                print("[!] Usage: hold_stick <stick> <x> <y> [pressed]")
                return
            stick_parts = parts[1].split()
            if len(stick_parts) < 3:
                print("[!] Usage: hold_stick <stick> <x> <y> [pressed]")
                return
            stick = stick_parts[0]
            x = int(stick_parts[1])
            y = int(stick_parts[2])
            pressed = bool(stick_parts[3].lower() == "true") if len(stick_parts) > 3 else False
            nx.hold_stick(cid, stick, x, y, pressed)
            print(f"[*] Holding stick {stick} at ({x}, {y}), pressed={pressed}")
            return

        elif cmd == "release_stick":
            if len(parts) >= 2:
                stick = parts[1]
                nx.release_stick(cid, stick)
                print(f"[*] Released stick: {stick}")
            else:
                nx.release_stick(cid)
                print(f"[*] Released all sticks")
            return

        elif cmd == "send":
            if len(parts) < 2 or not parts[1].strip():
                print("[!] Usage: send <macro>")
                return
            nx.macro(cid, parts[1].strip())
            print(f"[*] Sent macro: {parts[1].strip()}")
            return

        elif cmd == "status":
            print(f"[*] Mode={mode}, init={len(init_cmds)}, loop={len(loop_cmds)}")
            return

        elif cmd in ("quit", "exit"):
            print("[*] Quitting…")
            should_quit = True
            return

        else:
            print("[!] Invalid command. Use: mode, hold, release, hold_stick, release_stick, send, status, or quit.")

    def poll_inputs(timeout=0.05):
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
                        run_line(one)
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
                        run_line(one)

    def send_frame():
        """Send a frame with hold state applied."""
        packet = nx.create_input_packet()
        packet = nx.apply_hold_state(cid, packet)
        nx.set_controller_input(cid, packet)

    try:
        frame_time = 1.0 / FRAME_RATE
        last_frame = time.perf_counter()
        
        while not should_quit:
            poll_inputs(0.01)
            
            current_time = time.perf_counter()
            
            # Send frames continuously when in loop modes
            if in_loop_mode and (current_time - last_frame) >= frame_time:
                send_frame()
                last_frame = current_time

            if mode == "manual":
                # Still send frames in manual mode to maintain connection
                if (current_time - last_frame) >= frame_time:
                    send_frame()
                    last_frame = current_time
                time.sleep(0.01)
                continue

            # Refresh command files
            init_cmds = read_commands(INIT_FILE)
            loop_cmds = read_commands(LOOP_FILE)

            # --- Mode C: init only ---
            if mode == "c":
                in_loop_mode = False
                print("[*] Running init sequence (mode c)…")
                for cmd in init_cmds:
                    if mode != "c" or should_quit:
                        print("[!] Mode changed during init — stopping immediately.")
                        break
                    exec_command(nx, cid, cmd, tag="init")
                    poll_inputs(0.0)
                print("[*] Init complete. Returning to manual mode.")
                mode = "manual"
                continue

            # --- Mode A: init + loop ---
            if mode == "a" and not ran_init:
                in_loop_mode = True
                print("[*] Running init sequence…")
                for cmd in init_cmds:
                    if mode != "a" or should_quit:
                        print("[!] Mode changed during init — stopping immediately.")
                        break
                    exec_command(nx, cid, cmd, tag="init")
                    poll_inputs(0.0)
                ran_init = True
                if mode != "a" or should_quit:
                    continue

            # --- Mode B: just loop ---
            if mode == "b":
                in_loop_mode = True

            # --- Loop section (A and B) ---
            if loop_cmds and (mode == "a" or mode == "b"):
                print("[*] Starting loop pass…")
                for cmd in loop_cmds:
                    if mode == "manual" or should_quit:
                        print("[!] Mode switched to manual — stopping loop immediately.")
                        in_loop_mode = False
                        break
                    exec_command(nx, cid, cmd, tag="loop")
                    poll_inputs(0.0)
                    
                    # Send frames during loop execution
                    current_time = time.perf_counter()
                    if (current_time - last_frame) >= frame_time:
                        send_frame()
                        last_frame = current_time

                # Sleep between passes
                slept = 0.0
                while slept < SLEEP_BETWEEN_LOOPS:
                    if mode == "manual" or should_quit:
                        in_loop_mode = False
                        break
                    poll_inputs(0.01)
                    
                    # Send frames during sleep
                    current_time = time.perf_counter()
                    if (current_time - last_frame) >= frame_time:
                        send_frame()
                        last_frame = current_time
                    
                    time.sleep(0.01)
                    slept += 0.01

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
