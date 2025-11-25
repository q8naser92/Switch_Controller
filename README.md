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

2️⃣ Install Required Packages


