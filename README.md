# Thorlabs CCS200 spectrometer on Linux

A simple way to use the **Thorlabs CCS200 compact spectrometer** on Linux,
with no Windows, no VM and no NI-VISA. You get a live spectrum window and can
save spectra to CSV with one key press.

Tested on Fedora KDE. Should work on any distro with libusb (Ubuntu, Debian, Mint, Arch…).

## How it works

Thorlabs only ships Windows software (ThorSpectra), and the official driver
depends on NI-VISA. This repo uses the pure-Python pyUSB re-implementation of
Thorlabs' TLCCS library from [ThorPy](https://github.com/ElTinmar/CCS100)
by Martin Privat, and adds a small live-view and logging script on top.

The CCS200 has no firmware in flash. It contains a Cypress EZ-USB chip that starts as
a "blank" USB device (`1313:8088`). The firmware has to be uploaded to its RAM,
after which it re-enumerates as `1313:8089` and the green **READY** LED turns on.

- `ccs200_measure.py` uploads the firmware **automatically** the first time
  you run it after plugging in.
- The firmware then **stays loaded until you unplug the USB cable**, so you can
  close and restart the script as often as you like. There's no re-upload and no replug.

## Installation

```bash
git clone https://github.com/laurids15/css200-linux-driver-and-plotter.git
cd ccs200-linux
./install.sh
```

`install.sh` does the following:
1. Installs `libusb` and `innoextract` (via `dnf` or `apt`).
2. Creates a Python virtual environment in `.venv` and installs the requirements.
3. Installs a udev rule so the spectrometer can be used without `sudo`.
4. Downloads Thorlabs' installer and extracts the firmware into `ccs_firmware/`.

Unplug and replug the spectrometer once after installing, so the udev rule applies.

<details>
<summary>Manual installation</summary>

```bash
# Fedora
sudo dnf install libusb1 innoextract
# Debian/Ubuntu
sudo apt install libusb-1.0-0 innoextract python3-venv

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

sudo cp 99-thorlabs-ccs.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger

python get_firmware.py
```
</details>

### Firmware

The firmware file `CCS200.spt` belongs to Thorlabs and is **not included** in
this repo. `get_firmware.py` downloads it from Thorlabs' public OSA software
installer. If that link stops working, copy it from any Windows PC with
[ThorSpectra](https://www.thorlabs.com/software_pages/viewsoftwarepage.cfm?code=CCS) installed:

```
C:\Program Files\Thorlabs\CCS\inf\Loader\CCS200.spt   →   ccs_firmware/CCS200.spt
```

## Usage

```bash
source .venv/bin/activate

python ccs200_measure.py                  # live view, 100 ms integration
python ccs200_measure.py -t 0.5 -n 10     # 500 ms, saved spectra = mean of 10 scans
python ccs200_measure.py --single -n 10 -o sample.csv   # one spectrum, no window
```

| Option | Meaning |
|---|---|
| `-t` | Integration time in seconds (10 µs – 60 s, default 0.1) |
| `-n` | Number of scans averaged for each saved spectrum (default 1) |
| `--single` | Take one spectrum, save it to `-o` and exit |
| `-o` | Output file for `--single` (default `spectrum.csv`) |

### Keys in the live window

| Key | Action |
|---|---|
| `s` or **Save** button | Save the spectrum (mean of `-n` scans) to `spectra/spectrum_<timestamp>.csv` |
| `d` | Record a dark spectrum (block the light first). It is subtracted from then on |
| `c` | Clear the dark spectrum |
| `+` / `-` | Double / halve the integration time |
| `p` | Pause / resume |
| `q` | Quit. Closing the window or pressing `Ctrl+C` works too |

The title turns red if the signal is near saturation. Lower the integration time with `-`.
Changing the integration time clears the dark spectrum, because the dark level depends on it.

### Output format

```
# Thorlabs CCS200, 2026-11-26T10:52:59
# integration_time_s=0.5, averages=10, dark_subtracted=True
wavelength_nm,intensity
200.12,0.0123
...
```

3648 rows. The wavelength comes from the factory calibration stored in the device.
The intensity is normalised to 0–1 (1 = ADC full scale), with Thorlabs' factory amplitude correction applied.

Loading it:

```python
import numpy as np
wl, I = np.loadtxt("spectra/spectrum_20261126_105259.csv", delimiter=",", skiprows=3, unpack=True)
```
```python
import pandas as pd
df = pd.read_csv("spectra/spectrum_20261126_105259.csv", comment="#")
```
```matlab
d = readmatrix("spectrum_20261126_105259.csv", "NumHeaderLines", 3);
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `No CCS200 found` | Check with `lsusb \| grep 1313`. If nothing shows up, try another cable or port |
| `Access denied` / `Errno 13` | The udev rule isn't active. Re-run the `udevadm` commands and replug |
| `Firmware not found` | Run `python get_firmware.py`, or copy `CCS200.spt` manually (see above) |
| READY LED is off | The firmware isn't loaded. Just run the script and it uploads it |
| Plot is empty / "SATURATED" | Too much light. Lower the integration time or attenuate the input |
| Device doesn't respond at all | Unplug and replug, which resets it to the blank state, then run the script again |

## Other CCS models

The same approach works for the CCS100/125/150/175. Change `CCS200_PID`,
`CCS200_PID_U` and `CCS200.spt` in `ccs200_measure.py` to the matching model
(see the PID list in ThorPy's `tlccs.py`).

## Credits & license

- USB driver: [ThorPy](https://github.com/ElTinmar/CCS100) by Martin Privat, a
  re-implementation of Thorlabs' TLCCS library (LGPL-2.1).
- Firmware and calibration: © Thorlabs. Not redistributed here.
- This project has no affiliation with Thorlabs.
