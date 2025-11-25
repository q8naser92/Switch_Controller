# Switch_Controller  
Raspberry Pi 5 • NXBT (Modified) • Nintendo Switch 2 • 8BitDo Ultimate (2.4GHz)

## 🎯 Project Objective

This project transforms a **Raspberry Pi 5** into a **smart Nintendo Switch 2 controller** using a customized fork of **NXBT**.  
The system allows you to:

- Connect a **virtual Nintendo Switch Pro Controller** to the **Nintendo Switch 2**.
- Run **init macros**, **infinite looping macros**, or **custom sequences**.
- Use an **8BitDo Ultimate 2.4GHz controller** to physically toggle:
  - Loop mode  
  - Manual mode  
  - Stop/start actions
- Control everything from a **browser-based Flask GUI**.

This repository includes **all scripts, NXBT modifications, presets, and configs** needed to operate the system end-to-end.

---

## 🧩 Hardware Used

| Hardware | Role |
|---------|------|
| **Raspberry Pi 5** | Runs NXBT, loop engine, Flask GUI |
| **Nintendo Switch 2 (latest firmware)** | Target console |
| **8BitDo Ultimate (2.4GHz mode)** | Physical controller to switch modes |
| **8BitDo 2.4GHz Dongle** | Provides stable input events on the Pi |
| **microSD card** | OS & project files |
| **Wi-Fi / Ethernet** | For GUI access (assumed already working) |

> **Note:**  
> 8BitDo controller is used strictly in **2.4GHz mode**, *not Bluetooth mode*.

---


---

## 🚀 Step-by-Step Setup Guide  
A **beginner-friendly** guide for setting up the Raspberry Pi 5 from scratch.

---

# 1️⃣ Prepare the Raspberry Pi 5

Flash Raspberry Pi OS **Bookworm Lite** → Boot → SSH in.

### ⚠️ DO NOT run:

apt update
apt upgrade


This project uses **kernel freeze** to prevent NXBT from breaking.

Run:

```bash
sudo apt-mark hold raspberrypi-kernel raspberrypi-kernel-headers bluez pi-bluetooth
```

# 2️⃣ Install Required Packages

```bash
sudo apt install -y screen git python3 python3-venv python3-dev build-essential libbluetooth-dev libdbus-1-dev libglib2.0-dev libhidapi-libusb0 libcap2-bin bluetooth bluez bluez-tools
```

# 3️⃣ Clone the Repository Into /opt/nxbt

```bash
sudo mkdir -p /opt/nxbt
sudo chown $USER:$USER /opt/nxbt
git clone https://github.com/q8naser92/Switch_Controller /opt/nxbt
```

# 4️⃣ Install pyenv and Create Two Python Environments

One for NXBT engine, one for Flask GUI.

Install pyenv
```bash
curl https://pyenv.run | bash
```

Append to ~/.bashrc if needed:
```bash
export PATH="$HOME/.pyenv/bin:$PATH"
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"
```

Reload shell:
```bash
exec $SHELL
```

Install Python 3.11
```bash
pyenv install 3.11.9
```

Create environments
```bash
pyenv virtualenv 3.11.9 nxbt-env
pyenv virtualenv 3.11.9 nxbt-gui-env
```

# 5️⃣ Install NXBT (Modified Fork)

```bash
pyenv activate nxbt-env
cd /opt/nxbt/src/nxbt
pip install -e .
```

Allow Python to use raw Bluetooth sockets:
```bash
sudo setcap 'cap_net_raw,cap_net_admin+eip' "$(readlink -f $(which python3))" || true
```

# 6️⃣ Configure BlueZ for NXBT

Enable experimental mode:
```bash
sudo systemctl edit bluetooth.service
```

Add:
```bash
[Service]
ExecStart=
ExecStart=/usr/lib/bluetooth/bluetoothd --experimental
```

Reload:
```bash
sudo systemctl daemon-reload
sudo systemctl restart bluetooth
```

# 7️⃣ Test NXBT Standalone

Put Switch 2 in pairing mode.

Run:
```bash
pyenv activate nxbt-env
python /opt/nxbt/scripts/nxbt_new_loop.py
```

Expected output:
```bash
[*] Starting NXBT controller…
[+] Controller created (id 0), waiting…
[✓] Switch connected!
```

If pairing fails, open Flask GUI Bluetooth screen (explained later).

⸻

# 8️⃣ Install Flask GUI
```bash
pyenv activate nxbt-gui-env
cd /opt/nxbt/gui
pip install -r requirements.txt
```

Test manually:
```bash
python app.py
```

Open in browser:
```bash
http://<pi-ip>:5000
```

GUI Screens:
	1.	NXBT Loop Screen
	•	Start loop
	•	Start init
	•	Stop
	•	Edit macros
	•	Load presets
	•	Send manual commands
	2.	Bluetooth Screen
	•	Runs bluetoothctl inside Flask
	•	Shows live pairing status
	•	Allows trust/remove devices


# 9️⃣ Systemd Services

This project includes systemd files (if missing, ask and I’ll generate them).

They auto-start on boot:
	•	NXBT loop
	•	Flask GUI
	•	8BitDo grabber

Example:
```bash
sudo systemctl enable nxbt-loop.service
sudo systemctl enable nxbt-gui.service
sudo systemctl enable 8bitdo-grabber.service

sudo systemctl start nxbt-loop
sudo systemctl start nxbt-gui
sudo systemctl start 8bitdo-grabber
```

# 🔟 8BitDo Controller (2.4GHz) Integration

The 8BitDo controller disconnects every ~5 seconds unless grabbed.
This is normal behavior.

Your script:
	•	Detects /dev/input/eventX or /dev/input/js0
	•	Grabs the device before it disappears
	•	Keeps it permanently connected
	•	Maps button presses → writes commands to /tmp/nxbt_cmd

Install udev rule
```bash
sudo cp config/99-8bitdo.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
```

Test grabber
```bash
sudo journalctl -f
```

When controller appears you should see:
```bash
event5 created
8bitdo_grabber activated
device grabbed
```

🧠 How the Loop Engine Works

The main loop engine:
```bash
scripts/nxbt_new_loop.py
```
It:
	•	Loads config/init.txt or config/loop.txt
	•	Listens to FIFO /tmp/nxbt_cmd
	•	Holds buttons or sticks using the modified NXBT fork
	•	Can run indefinitely without blocking

Example commands you can send:
```bash
echo "mode a" > /tmp/nxbt_cmd
echo "mode manual" > /tmp/nxbt_cmd
echo "hold A" > /tmp/nxbt_cmd
echo "release A" > /tmp/nxbt_cmd
```

❓ FAQ / Troubleshooting

NXBT won’t connect to Switch

Try:
	1.	Restart Pi
	2.	Restart Switch (Sometimes the Switch Bluetooth stack becomes stuck.)
	3.	Pair an original Switch controller

8BitDo disconnects every 5 seconds

This is expected until the grabber script grabs /dev/input/eventX.

Flask GUI buttons do nothing

The loop is not running.

Check:
```bash
systemctl status nxbt-loop
```

Or run manually:
```bash
pyenv activate nxbt-env
python /opt/nxbt/scripts/nxbt_new_loop.py
```

Switch shows connected but NXBT stuck

Restart the Switch. Bluetooth sometimes jams.

📜 License

NXBT is MIT-licensed.
Nintendo trademarks belong to Nintendo.
8BitDo trademarks belong to 8BitDo.

🤝 Contributions

Pull requests are welcome.
This repo is designed around Pi 5 + Switch 2 + 8BitDo Ultimate (2.4GHz).


