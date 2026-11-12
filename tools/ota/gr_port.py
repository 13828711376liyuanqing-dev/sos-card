"""SAM | 2026-11-09 | Find the GR debug/CLI serial port. The COM number changes between benches and days, so it is never hard-coded.

Order: explicit argument (--port) > environment YP_GR_PORT > the configured one if it is currently present > auto-detect.
Auto-detect skips the CAT1 USB ports (VID 19D1, or 17D1 in download mode; Luatools needs them) and the nRF dongle (VID 1915); exactly one candidate is used,
none or several is an error that lists the ports so the person can choose (then pass --port or set YP_GR_PORT).
"""
import os

CAT1_VID, CAT1_DL_VID, NRF_VID = 0x19D1, 0x17D1, 0x1915   # CAT1 runs as 19D1, in Luatools download mode as 17D1


class PortError(RuntimeError):
    pass


def _ports():
    from serial.tools import list_ports
    return list(list_ports.comports())


def listing(ports=None):
    ports = _ports() if ports is None else ports
    return '\n'.join(f'  {p.device}  {p.description}  VID:PID={p.vid or 0:04X}:{p.pid or 0:04X}' for p in ports) or '  (no serial port found)'


def resolve(explicit=None, configured=None):
    for v in (explicit, os.environ.get('YP_GR_PORT')):
        if v and v.lower() != 'auto':
            return v
    ports = _ports()
    if configured and configured.lower() != 'auto' and any(p.device.upper() == configured.upper() for p in ports):
        return configured
    cand = [p for p in ports if p.vid not in (CAT1_VID, CAT1_DL_VID, NRF_VID)]
    if len(cand) == 1:
        return cand[0].device
    why = 'no candidate GR port' if not cand else 'more than one candidate GR port'
    raise PortError(f'{why}; pass --port COMx or set YP_GR_PORT. Ports now:\n{listing(ports)}')


def pick(explicit=None, configured=None):
    """resolve() for command-line tools: print the reason and exit instead of a traceback."""
    try:
        return resolve(explicit, configured)
    except PortError as e:
        raise SystemExit('GR serial port: ' + str(e))
