# Ocypus L36 Linux

A userspace Linux driver to control the **Ocypus Iota L36** LCD display (CachyOS/Arch tested).  
It shows system temperature on the cooler display via **USB HID** and can auto-start on boot using **systemd**.

> The device often appears in `lsusb` as **SEMICO / "USB Gaming Keyboard"** with VID:PID `1a2c:434d`.

## Credits

This project is inspired by and based on work from the following repositories/users:

- **moyunkz** — original Linux driver/research for Ocypus HID display devices:  
  https://github.com/moyunkz/ocypus-a40-digital-linux

- **ibnusurkati** — fixes/adjustments that helped validate the correct message format (write/output reports, 64-byte payload, etc.):  
  https://github.com/ibnusurkati/ocypus-a40-digital-linux


## Requirements

- Linux with `systemd` (CachyOS/Arch tested)
- Python 3
- Dependencies (installed automatically by `install.sh`):
  - `python-hidapi`
  - `python-psutil`
  - `usbutils`
  - `git` (only needed to clone the repo)

---

## Install (recommended)

### 1) Clone + install

```bash
sudo pacman -Syu --needed git
git clone https://github.com/henriquetl/Ocypus-L36-Linux.git
cd Ocypus-L36-Linux
sudo bash install.sh
