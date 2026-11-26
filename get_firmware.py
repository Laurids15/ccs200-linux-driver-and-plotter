#!/usr/bin/env python3
"""Download Thorlabs' OSA installer and extract the CCS firmware files.

The firmware (CCS200.spt) belongs to Thorlabs and is not included in this
repository. This script fetches it from Thorlabs' public installer using
innoextract and puts it in ./ccs_firmware/.

If the download link has changed, copy the file manually from a Windows PC
with ThorSpectra installed:
    C:\\Program Files\\Thorlabs\\CCS\\inf\\Loader\\CCS200.spt
"""
import os
from pathlib import Path

from thorlabs_ccs import extract_ccs_firmware

here = Path(__file__).resolve().parent
os.chdir(here)                      # extract_ccs_firmware writes to ./ccs_firmware
extract_ccs_firmware()

fw = here / "ccs_firmware" / "CCS200.spt"
print(f"OK: {fw}" if fw.exists() else "CCS200.spt not found - see the README.")
