from __future__ import annotations

from app.database import SessionLocal
from app.dfcom_poll import poll_once


def run() -> None:
    db = SessionLocal()
    try:
        report = poll_once(db)
        if report.error:
            print(f"dfcom-poll: {report.error}")
        for device in report.devices:
            state = device.error or "ok"
            print(
                f"dfcom-poll {device.host}: {state} read={device.read} stored={device.stored} preview={device.preview} quit={device.quit} lists={device.lists_written}"
            )
    finally:
        db.close()


if __name__ == "__main__":
    run()
