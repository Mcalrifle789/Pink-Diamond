"""Python binding for the C++ ad engine (core/ad_engine.cpp).

Loads the shared library when it has been built (cmake --build core) and falls
back to an identical pure-Python implementation otherwise, so the API behaves
the same on every machine.
"""

from __future__ import annotations

import ctypes
import pathlib

MAX_POPUPS_PER_SESSION = 2
MIN_POPUP_GAP_SECONDS = 90
DISMISS_SUPPRESSION_SECONDS = 12 * 3600

_INVENTORY = {
    "rail_left": ("black", 400),
    "rail_right": ("black", 400),
    "bottom": ("black", 350),
    "popup": ("grey", 0),
}


def _load_lib():
    lib_dir = pathlib.Path(__file__).resolve().parent.parent / "core" / "build"
    names = ["pd_ad_engine.dll", "libpd_ad_engine.so", "libpd_ad_engine.dylib"]
    for name in names:
        path = lib_dir / name
        if path.exists():
            lib = ctypes.CDLL(str(path))
            lib.pd_engine_new.restype = ctypes.c_void_p
            lib.pd_next_creative.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
            lib.pd_next_creative.restype = ctypes.c_long
            lib.pd_popup_allowed.argtypes = [ctypes.c_void_p, ctypes.c_long]
            lib.pd_popup_allowed.restype = ctypes.c_int
            lib.pd_popup_shown.argtypes = [ctypes.c_void_p, ctypes.c_long]
            lib.pd_popup_dismiss.argtypes = [ctypes.c_void_p, ctypes.c_long]
            lib.pd_slot_price.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
            lib.pd_slot_price.restype = ctypes.c_int
            return lib, lib.pd_engine_new()
    return None, None


class AdEngine:
    """Rotation for the black boxes and the pop-up policy for the grey ones."""

    def __init__(self) -> None:
        self._lib, self._handle = _load_lib()
        self._cursors = {placement: 0 for placement in _INVENTORY}
        self._popup_shown = 0
        self._popup_last = 0
        self._suppressed_until = 0

    def price(self, placement: str) -> int:
        if placement not in _INVENTORY:
            raise KeyError(placement)
        if self._lib:
            return self._lib.pd_slot_price(self._handle, placement.encode())
        return _INVENTORY[placement][1]

    def next_creative(self, placement: str) -> int:
        if placement not in _INVENTORY:
            raise KeyError(placement)
        if _INVENTORY[placement][0] != "black":
            raise ValueError("rotation applies to black boxes only")
        if self._lib:
            return self._lib.pd_next_creative(self._handle, placement.encode())
        current = self._cursors[placement]
        self._cursors[placement] += 1
        return current

    def popup_allowed(self, now: int) -> bool:
        if self._lib:
            return bool(self._lib.pd_popup_allowed(self._handle, now))
        if now < self._suppressed_until:
            return False
        if self._popup_shown >= MAX_POPUPS_PER_SESSION:
            return False
        if self._popup_shown and now - self._popup_last < MIN_POPUP_GAP_SECONDS:
            return False
        return True

    def record_popup_shown(self, now: int) -> None:
        if self._lib:
            self._lib.pd_popup_shown(self._handle, now)
            return
        self._popup_shown += 1
        self._popup_last = now

    def dismiss_popup(self, now: int) -> None:
        if self._lib:
            self._lib.pd_popup_dismiss(self._handle, now)
            return
        self._suppressed_until = now + DISMISS_SUPPRESSION_SECONDS
