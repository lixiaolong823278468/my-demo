from __future__ import annotations

import sys
import traceback
import faulthandler
import platform
from pathlib import Path


def main() -> None:
    log_path = Path(__file__).resolve().with_name("server_runtime.log")
    with log_path.open("a", encoding="utf-8", buffering=1) as log:
        sys.stdout = log
        sys.stderr = log
        faulthandler.enable(file=log)
        faulthandler.dump_traceback_later(10, repeat=False, file=log)
        platform.machine = lambda: "AMD64"
        print("starting api_server...")
        try:
            from api_server import main as api_main

            faulthandler.cancel_dump_traceback_later()
            print("api_server imported, entering main...")
            api_main()
        except Exception:
            traceback.print_exc()
            raise


if __name__ == "__main__":
    main()
