"""Retain the UI workflow entry point while checking the telemetry-only patch."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).with_name('check_telemetry_preservation.py')),run_name='__main__')
