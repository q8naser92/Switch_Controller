#!/usr/bin/env python3
import os, subprocess, shlex
from pathlib import Path
from flask import Flask, request, jsonify, render_template, send_from_directory

from flask import make_response  # already imported Flask; this just adds make_response

def _json_nocache(payload, status=200):
    resp = make_response(jsonify(payload), status)
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp

# ---- Paths & settings ----
INIT_PATH = Path("/root/init.txt")
LOOP_PATH = Path("/root/loop.txt")
PRESETS_DIR = Path("/root/presets")
LOG_DIR   = Path("/var/log/nxui")
BT_LOG    = LOG_DIR / "btctl.log"
PROG_LOG  = LOG_DIR / "nxloop.log"
API_LOG   = LOG_DIR / "api.log"

# Your NXBT loop runner
PYENV_PY  = "/root/.pyenv/versions/nxbt-3.11/bin/python"
NXBT_LOOP = "/root/nxbt_loop.py"

# screen session names
BT_SESSION   = "nxui_bt"
PROG_SESSION = "nxui_prog"

# Ensure dirs/files exist
LOG_DIR.mkdir(parents=True, exist_ok=True)
PRESETS_DIR.mkdir(parents=True, exist_ok=True)
for p in (INIT_PATH, LOOP_PATH):
    if not p.exists():
        p.write_text("", encoding="utf-8")
for p in (BT_LOG, PROG_LOG, API_LOG):
    if not p.exists():
        p.write_text("", encoding="utf-8")

app = Flask(__name__, template_folder="/opt/nxui/templates", static_folder=None)

# ---------- helpers ----------
def run(cmd, **kw):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **kw)
    out, err = p.communicate()
    return p.returncode, out, err

def screen_exists(name: str) -> bool:
    rc, out, _ = run(["screen", "-ls"])
    if rc != 0:
        return False
    return any((f".{name}\t" in line) or (f".{name} (" in line) for line in out.splitlines())

def log_api(msg: str):
    with API_LOG.open("a", encoding="utf-8") as f:
        f.write(msg.rstrip() + "\n")

def screen_start(name: str, shell_cmd: str):
    # robust: run through bash -lc to keep env/pyenv and quoting right
    cmd = ["screen", "-d", "-m", "-S", name, "bash", "-lc", shell_cmd]
    rc, out, err = run(cmd)
    if rc != 0:
        log_api(f"[screen_start:{name}] rc={rc}\nout={out}\nerr={err}")
    else:
        log_api(f"[screen_start:{name}] OK -> {shell_cmd}")
    return rc == 0

def screen_send(name: str, keys: str):
    if not screen_exists(name):
        return False
    rc, out, err = run(["screen", "-S", name, "-X", "stuff", keys])
    if rc != 0:
        log_api(f"[screen_send:{name}] rc={rc}\nout={out}\nerr={err}")
    return rc == 0

def screen_kill(name: str):
    if not screen_exists(name):
        return True
    rc, out, err = run(["screen", "-S", name, "-X", "quit"])
    if rc != 0:
        log_api(f"[screen_kill:{name}] rc={rc}\nout={out}\nerr={err}")
    else:
        log_api(f"[screen_kill:{name}] OK")
    return rc == 0

def tail(path: Path, n: int = 300) -> str:
    if not path.exists():
        return ""
    data = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return "\n".join(data[-n:])

# ---------- UI ----------
@app.get("/")
def index():
    return render_template("index.html")

@app.get("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("/opt/nxui/static", filename)

# ---------- Bluetooth pane ----------
@app.post("/bluetooth/start")
def bt_start():
    # util-linux script format: script [opts] FILE -c "CMD"
    shell_cmd = f'script -q -f {shlex.quote(str(BT_LOG))} -c "bluetoothctl"'
    ok = screen_exists(BT_SESSION) or screen_start(BT_SESSION, shell_cmd)
    return jsonify({"ok": ok, "running": screen_exists(BT_SESSION)})

@app.post("/bluetooth/stop")
def bt_stop():
    ok = screen_kill(BT_SESSION)
    return jsonify({"ok": ok, "running": screen_exists(BT_SESSION)})

@app.post("/bluetooth/pair")
def bt_pair():
    ok = screen_send(BT_SESSION, "yes\015")  # yes + Enter
    return jsonify({"ok": ok})

@app.get("/bluetooth/log")
def bt_log():
    return _json_nocache({"log": tail(BT_LOG, 300)})

# ---------- Program pane ----------
@app.post("/program/start")
def prog_start():
    # Use script too so *interactive output* is captured every time
    cmd = f'{shlex.quote(PYENV_PY)} {shlex.quote(NXBT_LOOP)}'
    shell_cmd = f"cd /root && script -q -f {shlex.quote(str(PROG_LOG))} -c {shlex.quote(cmd)}"
    ok = screen_exists(PROG_SESSION) or screen_start(PROG_SESSION, shell_cmd)
    return jsonify({"ok": ok, "running": screen_exists(PROG_SESSION)})

@app.post("/program/stop")
def prog_stop():
    sent = screen_send(PROG_SESSION, "\003")  # Ctrl-C
    ok = sent and screen_kill(PROG_SESSION)
    return jsonify({"ok": ok, "running": screen_exists(PROG_SESSION)})

@app.get("/program/log")
def prog_log():
    return _json_nocache({"log": tail(PROG_LOG, 300)})

# ---------- Files API ----------
@app.get("/files")
def files_get():
    which = request.args.get("which", "init")
    path = INIT_PATH if which == "init" else LOOP_PATH if which == "loop" else None
    if path is None or not path.exists():
        return _json_nocache({"error": "not found"}, 404)
    lines = [{"n": i+1, "t": t} for i, t in enumerate(path.read_text(encoding="utf-8").splitlines())]
    return jsonify({"path": str(path), "lines": lines})

@app.post("/files/append")
def files_append():
    data = request.get_json(force=True)
    which = data.get("which", "init")
    line  = (data.get("line") or "").rstrip("\n")
    if not line:
        return jsonify({"ok": False, "error": "empty"}), 400
    line = " ".join(line.split())
    path = INIT_PATH if which == "init" else LOOP_PATH
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return jsonify({"ok": True})

@app.post("/files/delete")
def files_delete():
    data = request.get_json(force=True)
    which = data.get("which", "init")
    ln    = int(data.get("line_number", 0))
    path = INIT_PATH if which == "init" else LOOP_PATH
    lines = path.read_text(encoding="utf-8").splitlines()
    if ln < 1 or ln > len(lines):
        return jsonify({"ok": False, "error": "bad line"}), 400
    del lines[ln-1]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return jsonify({"ok": True})

@app.post("/files/modify")
def files_modify():
    data = request.get_json(force=True) or {}
    which = (data.get("which") or "init").strip()
    ln    = int(data.get("line_number", 0))
    newt  = (data.get("new_text") or "").rstrip("\n")

    path = INIT_PATH if which == "init" else LOOP_PATH
    if not path.exists():
        return jsonify({"ok": False, "error": "not found"}), 404

    lines = path.read_text(encoding="utf-8").splitlines()
    if ln < 1 or ln > len(lines):
        return jsonify({"ok": False, "error": "bad line"}), 400

    lines[ln - 1] = newt
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return jsonify({"ok": True})

# ---------- Presets API ----------
@app.get("/presets/list")
def presets_list():
    """List all available preset files"""
    try:
        presets = []
        for p in PRESETS_DIR.glob("*.txt"):
            stat = p.stat()
            presets.append({
                "name": p.stem,
                "filename": p.name,
                "size": stat.st_size,
                "modified": stat.st_mtime
            })
        presets.sort(key=lambda x: x["modified"], reverse=True)
        return jsonify({"ok": True, "presets": presets})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.post("/presets/save")
def presets_save():
    """Save current loop.txt as a preset"""
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "name required"}), 400
    
    # Sanitize filename - only allow alphanumeric, dash, underscore
    safe_name = "".join(c for c in name if c.isalnum() or c in "-_")
    if not safe_name:
        return jsonify({"ok": False, "error": "invalid name"}), 400
    
    preset_path = PRESETS_DIR / f"{safe_name}.txt"
    try:
        # Copy loop.txt to preset
        content = LOOP_PATH.read_text(encoding="utf-8")
        preset_path.write_text(content, encoding="utf-8")
        return jsonify({"ok": True, "filename": preset_path.name})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.post("/presets/load")
def presets_load():
    """Load a preset into loop.txt"""
    data = request.get_json(force=True) or {}
    filename = (data.get("filename") or "").strip()
    if not filename:
        return jsonify({"ok": False, "error": "filename required"}), 400
    
    preset_path = PRESETS_DIR / filename
    if not preset_path.exists() or not preset_path.is_file():
        return jsonify({"ok": False, "error": "preset not found"}), 404
    
    # Ensure it's within presets directory (security check)
    try:
        preset_path.resolve().relative_to(PRESETS_DIR.resolve())
    except ValueError:
        return jsonify({"ok": False, "error": "invalid preset path"}), 403
    
    try:
        content = preset_path.read_text(encoding="utf-8")
        LOOP_PATH.write_text(content, encoding="utf-8")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.get("/presets/view")
def presets_view():
    """View contents of a preset file"""
    filename = request.args.get("filename", "").strip()
    if not filename:
        return jsonify({"error": "filename required"}), 400
    
    preset_path = PRESETS_DIR / filename
    if not preset_path.exists() or not preset_path.is_file():
        return jsonify({"error": "preset not found"}), 404
    
    # Ensure it's within presets directory (security check)
    try:
        preset_path.resolve().relative_to(PRESETS_DIR.resolve())
    except ValueError:
        return jsonify({"error": "invalid preset path"}), 403
    
    try:
        lines = [{"n": i+1, "t": t} for i, t in enumerate(preset_path.read_text(encoding="utf-8").splitlines())]
        return jsonify({"path": str(preset_path), "lines": lines})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.post("/presets/delete")
def presets_delete():
    """Delete a preset file"""
    data = request.get_json(force=True) or {}
    filename = (data.get("filename") or "").strip()
    if not filename:
        return jsonify({"ok": False, "error": "filename required"}), 400
    
    preset_path = PRESETS_DIR / filename
    if not preset_path.exists():
        return jsonify({"ok": False, "error": "preset not found"}), 404
    
    # Ensure it's within presets directory (security check)
    try:
        preset_path.resolve().relative_to(PRESETS_DIR.resolve())
    except ValueError:
        return jsonify({"ok": False, "error": "invalid preset path"}), 403
    
    try:
        preset_path.unlink()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "bt_running": screen_exists(BT_SESSION),
        "prog_running": screen_exists(PROG_SESSION),
        "init_path": str(INIT_PATH),
        "loop_path": str(LOOP_PATH),
    })

@app.get("/routes")
def routes():
    return jsonify(sorted([rule.rule for rule in app.url_map.iter_rules()]))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
