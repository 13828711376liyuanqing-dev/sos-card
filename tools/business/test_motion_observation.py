"""SAM | 2026-10-25 +08:00 | Legacy entry now runs the complete actual observation service regression."""
import runpy
from pathlib import Path
runpy.run_path(str(Path(__file__).with_name('test_safety_observation_runtime.py')),run_name='__main__')
