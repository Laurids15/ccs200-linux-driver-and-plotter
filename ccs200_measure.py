#!/usr/bin/env python3
"""Thorlabs CCS200 compact spectrometer on Linux: live view + saving spectra.

Built on the pure-pyUSB driver from ThorPy (https://github.com/ElTinmar/CCS100).

The CCS200 keeps its firmware in RAM. This script uploads it automatically
the first time you run it after plugging the spectrometer in (green READY LED
turns on). After that the firmware stays loaded until the USB cable is
unplugged, so closing and restarting the script is instant and never needs
a replug.

Usage:
    python ccs200_measure.py                    # live view, 0.1 s integration
    python ccs200_measure.py -t 0.5 -n 10       # 0.5 s, saved spectra = mean of 10 scans
    python ccs200_measure.py --single -n 10 -o sample.csv   # one spectrum, no window

Keys in the live window:
    s / Save button   save spectrum (mean of -n scans) to spectra/<timestamp>.csv
    d                 record dark spectrum (block the light first), then subtract it
    c                 clear dark spectrum
    + / -             double / halve integration time
    p                 pause / resume
    q                 quit (closing the window or Ctrl+C also works)
"""
import argparse
import signal
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Button
import usb.core
import usb.util
import thorlabs_ccs.tlccs as tl

HERE = Path(__file__).resolve().parent
FIRMWARE = HERE / "ccs_firmware" / "CCS200.spt"
STOP = {"flag": False}          # set by Ctrl+C, closing the window or 'q'


class ScanTimeout(Exception):
    pass


# --------------------------------------------------------------------------
# Device handling
# --------------------------------------------------------------------------
class CCS200:
    """Minimal wrapper around ThorPy's low-level functions.

    Unlike ThorPy's TLCCS class, this never sends a USB port reset or the
    device RESET command, so the firmware stays loaded between runs.
    """

    def __init__(self):
        dev = usb.core.find(idVendor=tl.THORLABS_VID, idProduct=tl.CCS200_PID)
        if dev is None:
            dev = self._load_firmware()
        self.dev = dev
        try:
            dev.get_active_configuration()
        except usb.core.USBError:
            dev.set_configuration()
        self._drain()
        self.data = tl.TLCCS_DATA()
        tl.initialize(dev, self.data)          # reads calibration from EEPROM
        self.wavelength = np.array(tl.get_wavelength(self.data))

    @staticmethod
    def _load_firmware():
        raw = usb.core.find(idVendor=tl.THORLABS_VID, idProduct=tl.CCS200_PID_U)
        if raw is None:
            raise SystemExit("No CCS200 found. Check the USB cable and the udev rule "
                             "(see README).")
        if not FIRMWARE.exists():
            raise SystemExit(f"Firmware not found: {FIRMWARE}\n"
                             "Run 'python get_firmware.py' first (see README).")
        print("First run since plug-in: uploading firmware...")
        dev = tl.renumerate(PID=tl.CCS200_PID_U, port_numbers=raw.port_numbers,
                            firmware_file=FIRMWARE)
        time.sleep(0.5)
        return dev

    def _drain(self):
        """Throw away a half-finished scan left over from an interrupted run."""
        try:
            while True:
                self.dev.read(0x86, tl.TLCCS_NUM_RAW_PIXELS * 2, timeout=100)
        except usb.core.USBError:
            pass

    def set_integration_time(self, t):
        tl.set_integration_time(self.dev, t)

    def scan_once(self, t_int):
        """One single-shot scan with timeout, so a stuck device can't hang us."""
        tl.start_single_scan(self.dev)
        deadline = time.monotonic() + t_int + 2.0
        while not (tl.get_device_status(self.dev) & tl.TLCCS_STATUS_SCAN_TRANSFER):
            if STOP["flag"]:
                self._drain()
                raise KeyboardInterrupt
            if time.monotonic() > deadline:
                raise ScanTimeout("Spectrometer did not finish the scan")
            time.sleep(0.002)
        try:
            return np.array(tl.get_scan_data_factory(self.dev, self.data))
        except tl.Overexposure:
            return np.full(tl.TLCCS_NUM_PIXELS, np.nan)

    def scan(self, t_int, n=1):
        """Mean of n scans."""
        return np.mean([self.scan_once(t_int) for _ in range(n)], axis=0)

    def close(self):
        """Release the USB handle only. The firmware stays loaded."""
        try:
            usb.util.dispose_resources(self.dev)
        except Exception:
            pass


# --------------------------------------------------------------------------
# Saving
# --------------------------------------------------------------------------
def save(path, wl, spectrum, t_int, n, dark_subtracted):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (f"# Thorlabs CCS200, {datetime.now().isoformat(timespec='seconds')}\n"
              f"# integration_time_s={t_int}, averages={n}, "
              f"dark_subtracted={dark_subtracted}\n"
              "wavelength_nm,intensity")
    np.savetxt(path, np.column_stack([wl, spectrum]), delimiter=",",
               header=header, comments="", fmt="%.6g")
    print(f"Saved {path}")


# --------------------------------------------------------------------------
# Live view
# --------------------------------------------------------------------------
def live(ccs, args):
    wl = ccs.wavelength
    state = {"dark": None, "paused": False, "t": args.integration}

    for key in ("keymap.save", "keymap.quit"):   # free 's' and 'q' for our own use
        plt.rcParams[key] = []

    fig, ax = plt.subplots(figsize=(10, 5))
    fig.subplots_adjust(bottom=0.18)
    line, = ax.plot(wl, np.zeros_like(wl), lw=0.8)
    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Intensity (a.u.)")
    ax.set_xlim(wl.min(), wl.max())
    ax.grid(alpha=0.3)

    def title(msg=None, color="black"):
        if msg is None:
            msg = (f"CCS200 live | t = {state['t']*1e3:g} ms | avg = {args.average} | "
                   f"dark: {'on' if state['dark'] is not None else 'off'}"
                   f"{' | PAUSED' if state['paused'] else ''}    "
                   "[s]ave [d]ark [c]lear [+/-] time [p]ause [q]uit")
        ax.set_title(msg, fontsize=9, color=color)
        fig.canvas.draw_idle()
        fig.canvas.flush_events()

    def do_save(_=None):
        title(f"Saving (averaging {args.average} scans)...", "blue")
        s = ccs.scan(state["t"], args.average)
        if state["dark"] is not None:
            s = s - state["dark"]
        fname = HERE / "spectra" / f"spectrum_{datetime.now():%Y%m%d_%H%M%S}.csv"
        save(fname, wl, s, state["t"], args.average, state["dark"] is not None)
        title(f"Saved {fname.relative_to(HERE)}", "green")

    def set_time(t):
        t = float(np.clip(t, tl.TLCCS_MIN_INT_TIME, tl.TLCCS_MAX_INT_TIME))
        ccs.set_integration_time(t)
        state["t"] = t
        state["dark"] = None                     # dark depends on integration time
        title()

    def on_key(ev):
        k = ev.key
        if k == "s":
            do_save()
        elif k == "d":
            title("Recording dark spectrum...", "blue")
            state["dark"] = ccs.scan(state["t"], max(args.average, 5))
            title()
        elif k == "c":
            state["dark"] = None
            title()
        elif k in ("+", "="):
            set_time(state["t"] * 2)
        elif k == "-":
            set_time(state["t"] / 2)
        elif k == "p":
            state["paused"] = not state["paused"]
            title()
        elif k == "q":
            STOP["flag"] = True

    fig.canvas.mpl_connect("key_press_event", on_key)
    fig.canvas.mpl_connect("close_event", lambda _: STOP.update(flag=True))
    btn = Button(fig.add_axes([0.85, 0.03, 0.1, 0.06]), "Save")
    btn.on_clicked(do_save)
    title()
    plt.show(block=False)

    while plt.fignum_exists(fig.number) and not STOP["flag"]:
        if not state["paused"]:
            s = ccs.scan_once(state["t"])
            if state["dark"] is not None:
                s = s - state["dark"]
            line.set_ydata(s)
            if np.isnan(s).all():
                title("SATURATED - press '-' to lower the integration time", "red")
            else:
                ax.set_ylim(min(0, np.nanmin(s)) - 0.01, 1.1 * max(np.nanmax(s), 1e-3))
                if np.nanmax(s) > 0.98:
                    title("Near saturation - press '-' to lower the integration time", "red")
                elif ax.title.get_color() == "red":
                    title()
        plt.pause(0.01)


# --------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="Thorlabs CCS200 live view and logger")
    p.add_argument("-t", "--integration", type=float, default=0.1,
                   help="integration time in seconds (10 µs - 60 s, default 0.1)")
    p.add_argument("-n", "--average", type=int, default=1,
                   help="number of scans averaged per saved spectrum (default 1)")
    p.add_argument("-o", "--output", default="spectrum.csv",
                   help="output file for --single (default spectrum.csv)")
    p.add_argument("--single", action="store_true",
                   help="take one (averaged) spectrum, save it and exit")
    p.add_argument("--live", action="store_true", help="live view (this is the default)")
    args = p.parse_args()

    signal.signal(signal.SIGINT, lambda *_: STOP.update(flag=True))

    ccs = CCS200()
    try:
        ccs.set_integration_time(args.integration)
        if args.single:
            spectrum = ccs.scan(args.integration, args.average)
            save(args.output, ccs.wavelength, spectrum, args.integration,
                 args.average, False)
        else:
            live(ccs, args)
    except KeyboardInterrupt:
        pass
    finally:
        ccs.close()
        plt.close("all")
        print("Stopped. (Firmware stays loaded - next start is instant.)")


if __name__ == "__main__":
    main()
