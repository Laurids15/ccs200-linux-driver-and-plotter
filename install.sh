#!/usr/bin/env bash
# One-time setup for the Thorlabs CCS200 on Linux (Fedora / Debian / Ubuntu).
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Installing system packages (libusb, innoextract)"
if command -v dnf >/dev/null; then
    sudo dnf install -y libusb1 innoextract python3
elif command -v apt-get >/dev/null; then
    sudo apt-get update
    sudo apt-get install -y libusb-1.0-0 innoextract python3-venv
else
    echo "Unknown package manager: install libusb-1.0 and innoextract yourself."
fi

echo "==> Creating Python virtual environment in .venv"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "==> Installing udev rule (USB access without sudo)"
sudo cp 99-thorlabs-ccs.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger

if [ ! -f ccs_firmware/CCS200.spt ]; then
    echo "==> Fetching firmware from Thorlabs' installer"
    .venv/bin/python get_firmware.py || echo "Firmware download failed - see README."
fi

echo
echo "Done. Unplug and replug the spectrometer once, then run:"
echo "    source .venv/bin/activate"
echo "    python ccs200_measure.py"
