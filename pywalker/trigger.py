"""
EEG trigger via LabJack U3.

Sends an N-bit value on FIO pins, holds for pulse_ms, then resets to 0.
Falls back to console print if LabJack is not connected or not installed.

Trigger codes (4-bit scheme, max value 15):
    1  — fixation onset
    2  — maze start (easy)
    3  — maze start (hard)
    4  — easy: star 1 collected
    5  — hard: star 1 collected
    6  — hard: star 2 collected
    7  — hard: star 3 collected
    8  — trial complete
    9  — trial ended via ESC
    10 — block rest start
    11 — block rest end
"""

import gc
import time

try:
    import u3 as _u3
    _U3_AVAILABLE = True
except ImportError:
    _U3_AVAILABLE = False


def release_all_labjack() -> int:
    """Close every open U3 handle in the current process.

    Useful when a previous Jupyter cell or script left the device locked.
    Returns the number of handles closed.
    """
    if not _U3_AVAILABLE:
        return 0
    closed = 0
    for obj in gc.get_objects():
        try:
            if isinstance(obj, _u3.U3):
                try:
                    obj.close()
                    closed += 1
                except Exception:
                    pass
        except ReferenceError:
            pass
    if closed:
        print(f'[EEGTrigger] Released {closed} existing U3 handle(s).')
    return closed

# Trigger code constants (4-bit compatible: 1-15)
TRIG_FIXATION         = 1
TRIG_MAZE_START_EASY  = 2
TRIG_MAZE_START_HARD  = 3
TRIG_EASY_STAR_1      = 4   # easy condition: only 1 star
TRIG_HARD_STAR_1      = 5   # hard condition: star 1 of 3
TRIG_HARD_STAR_2      = 6
TRIG_HARD_STAR_3      = 7
TRIG_TRIAL_COMPLETE   = 8
TRIG_TRIAL_ESCAPE     = 9
TRIG_BLOCK_REST_START = 10
TRIG_BLOCK_REST_END   = 11


def star_trigger(condition: str, star_index: int) -> int:
    """Return trigger code for collecting a star.

    condition: 'easy' or 'hard'
    star_index: 0-indexed (0 = first star)
    """
    if condition not in ('easy', 'hard'):
        raise ValueError(f"star_trigger: unknown condition {condition!r}")
    if condition == 'easy':
        return TRIG_EASY_STAR_1
    else:
        return [TRIG_HARD_STAR_1, TRIG_HARD_STAR_2, TRIG_HARD_STAR_3][min(star_index, 2)]


class EEGTrigger:
    """Send EEG triggers via LabJack U3 FIO pins.

    Args:
        pulse_ms: Trigger pulse duration in milliseconds.
        bits: Number of output bits (4 for Turkey EEG, 8 for full range).
        verbose: Print trigger codes to console.
    """

    def __init__(self, pulse_ms: float = 2.0, bits: int = 4, verbose: bool = True):
        self.pulse_s = pulse_ms / 1000.0
        self.bits = bits
        self.verbose = verbose
        self._device = None
        self._silent = False

        # Compute mask based on bit count
        self._mask = (1 << bits) - 1  # 4 bits → 0x0F, 8 bits → 0xFF
        self._max_value = self._mask

        if not _U3_AVAILABLE:
            print('[EEGTrigger] LabJackPython not installed — console mode')
            self._silent = True
            return

        if not self._try_open(bits):
            self._device = None
            self._silent = True

    def _try_open(self, bits: int, _retry: bool = True) -> bool:
        """Open and configure the U3. Returns True on success.

        On first failure caused by "already open", releases existing handles
        in this process and retries once automatically.
        """
        try:
            self._device = _u3.U3()
            self._device.configIO(FIOAnalog=0, EIOAnalog=0)
            self._device.getFeedback(_u3.PortDirWrite(
                Direction=[self._mask, 0, 0], WriteMask=[self._mask, 0, 0]))
            self._device.getFeedback(_u3.PortStateWrite(
                State=[0, 0, 0], WriteMask=[self._mask, 0, 0]))
            print(f'[EEGTrigger] LabJack U3 connected ({bits}-bit mode, max={self._max_value})')
            return True
        except Exception as e:
            err = str(e)
            if _retry and 'already open' in err.lower():
                print(f'[EEGTrigger] Device busy — releasing existing handles and retrying...')
                released = release_all_labjack()
                if released:
                    return self._try_open(bits, _retry=False)
            print(f'[EEGTrigger] No LabJack found ({e}) — console mode')
            self._device = None
            return False

    def send(self, value: int):
        """Send trigger: set FIO pins = value, wait pulse_ms, reset to 0."""
        value = int(value) & self._mask
        if self.verbose:
            print(f'[EEGTrigger] TRIGGER {value}')
        if self._silent or self._device is None:
            return
        self._device.getFeedback(_u3.PortStateWrite(
            State=[value, 0, 0], WriteMask=[self._mask, 0, 0]))
        time.sleep(self.pulse_s)
        self._device.getFeedback(_u3.PortStateWrite(
            State=[0, 0, 0], WriteMask=[self._mask, 0, 0]))

    def close(self):
        """Reset pins and close device."""
        if self._device:
            try:
                self._device.getFeedback(_u3.PortStateWrite(
                    State=[0, 0, 0], WriteMask=[self._mask, 0, 0]))
                self._device.close()
            except Exception:
                pass
            self._device = None

    def __del__(self):
        self.close()
