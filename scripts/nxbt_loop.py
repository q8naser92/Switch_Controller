#!/usr/bin/env python3
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

HELP_BANNER = """
Available commands (type directly or echo into /tmp/nxbt_cmd):

  mode manual      # stop everything and wait for commands
  mode a           # run init.txt once, then loop.txt repeatedly
  mode b           # loop loop.txt repeatedly (no init)
  mode c           # run init.txt once, then return to manual

  send <macros>    # example: send A 0.3s, B 0.3s, L_STICK@+000+100 1s
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


def exec_macro(nx, cid, line, tag=""):
    """Run a macro safely without crashing the loop."""
    try:
        print(f"[{tag}] {line}" if tag else f"{line}")
        nx.macro(cid, line)
        return True
    except Exception as e:
        print(f"[!] Error running '{line}': {e}")
        return False


def exec_macro_list(nx, cid, macro_line):
    """Split a 'send' line into multiple macros separated by commas."""
    macros = [m.strip() for m in macro_line.split(",") if m.strip()]
    if not macros:
        print("[!] No valid macros found.")
        return
    for i, macro in enumerate(macros, 1):
        print(f"[send:{i}/{len(macros)}] {macro}")
        exec_macro(nx, cid, macro, tag="send")


def main():
    print("[*] Starting NXBT controller…")
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

    def run_line(line):
        """Process one command line."""
        nonlocal mode, ran_init, should_quit

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

        elif cmd == "send":
            if len(parts) < 2 or not parts[1].strip():
                print("[!] Usage: send <macro> [, macro2, ...]")
                return
            exec_macro_list(nx, cid, parts[1].strip())
            return

        elif cmd == "status":
            print(f"[*] Mode={mode}, init={len(init_cmds)}, loop={len(loop_cmds)}")
            return

        elif cmd in ("quit", "exit"):
            print("[*] Quitting…")
            should_quit = True
            return

        else:
            print("[!] Invalid command. Use: mode, send, status, or quit.")

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

    try:
        while not should_quit:
            poll_inputs(0.05)

            if mode == "manual":
                time.sleep(0.05)
                continue

            # Refresh command files
            init_cmds = read_commands(INIT_FILE)
            loop_cmds = read_commands(LOOP_FILE)

            # --- Mode C: init only ---
            if mode == "c":
                print("[*] Running init sequence (mode c)…")
                for cmd in init_cmds:
                    if mode != "c" or should_quit:
                        print("[!] Mode changed during init — stopping immediately.")
                        break
                    exec_macro(nx, cid, cmd, tag="init")
                    poll_inputs(0.0)
                print("[*] Init complete. Returning to manual mode.")
                mode = "manual"
                continue

            # --- Mode A: init + loop ---
            if mode == "a" and not ran_init:
                print("[*] Running init sequence…")
                for cmd in init_cmds:
                    if mode != "a" or should_quit:
                        print("[!] Mode changed during init — stopping immediately.")
                        break
                    exec_macro(nx, cid, cmd, tag="init")
                    poll_inputs(0.0)
                ran_init = True
                if mode != "a" or should_quit:
                    continue

            # --- Loop section (A and B) ---
            if loop_cmds:
                print("[*] Starting loop pass…")
            for cmd in loop_cmds:
                if mode == "manual" or should_quit:
                    print("[!] Mode switched to manual — stopping loop immediately.")
                    break
                exec_macro(nx, cid, cmd, tag="loop")
                poll_inputs(0.0)

            # Sleep between passes
            slept = 0.0
            while slept < SLEEP_BETWEEN_LOOPS:
                if mode == "manual" or should_quit:
                    break
                poll_inputs(0.05)
                time.sleep(0.05)
                slept += 0.05

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
