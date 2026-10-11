"""Build the Pink Diamond payment core (C + C++ + Zig) into one shared library.

    python -m pip install ziglang        # the Zig toolchain also compiles C/C++
    python native/payments/build.py              # host library
    python native/payments/build.py --vercel     # + linux x86_64 for the Vercel function

Outputs go to backend/native/, where backend/payments_core.py looks for them.
The linux build is committed so the deployed API runs the native core; the
Python mirror takes over anywhere the library is missing.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent.parent / "backend" / "native"
SOURCES = ["pd_money.zig", "pd_sig.c", "pd_lifecycle.cpp"]

TARGETS = {
    "host": (None, {"win32": "pd_pay.dll", "darwin": "libpd_pay.dylib"}.get(sys.platform, "libpd_pay.so")),
    # glibc 2.28 covers Vercel's Amazon Linux 2023 runtime and anything newer.
    "vercel": ("x86_64-linux-gnu.2.28", "libpd_pay-linux-x86_64.so"),
}


def zig(*args: str) -> None:
    cmd = [sys.executable, "-m", "ziglang", *args]
    subprocess.run(cmd, check=True, cwd=HERE)


def build(target: str | None, filename: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        args = ["build-lib", "-dynamic", "-OReleaseSafe", "-fstrip", "-lc", "-lc++", "-I", str(HERE),
                "-cflags", "-std=c11", "-Wall", "-Wextra", "-Werror", "--", "pd_sig.c",
                "-cflags", "-std=c++17", "-Wall", "-Wextra", "-Werror", "--", "pd_lifecycle.cpp",
                "pd_money.zig", "--name", "pd_pay", f"-femit-bin={Path(tmp) / filename}"]
        if target:
            args[1:1] = ["-target", target]
        zig(*args)
        dest = OUT / filename
        shutil.copy2(Path(tmp) / filename, dest)
    return dest


def main() -> None:
    zig("test", "pd_money.zig")
    wanted = ["host"] + (["vercel"] if "--vercel" in sys.argv else [])
    for name in wanted:
        target, filename = TARGETS[name]
        print("built", build(target, filename))


if __name__ == "__main__":
    main()
