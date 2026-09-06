from __future__ import annotations

from sqlalchemy import select

from app.auth import as_local, local_day_bounds, now_utc
from app.config import get_config
from app.database import SessionLocal
from app.mail import send_mail
from app.models import Punch, User
from app.timecalc import status_from_punches


def run() -> None:
    cfg = get_config()
    now = now_utc()
    local_now = as_local(now)
    if local_now.hour < 18:
        print("checkout-reminder: too early, skip")
        return
    start, end = local_day_bounds(local_now.date())
    db = SessionLocal()
    try:
        users = list(db.scalars(select(User).where(User.active.is_(True))))
        for user in users:
            punches = list(
                db.scalars(
                    select(Punch).where(
                        Punch.user_id == user.id,
                        Punch.server_time >= start,
                        Punch.server_time < end,
                    )
                )
            )
            state = status_from_punches(punches)
            if state in {"in", "break"} and user.email:
                send_mail(
                    user.email,
                    f"{cfg.org_name}: Ausstempeln nicht vergessen",
                    f"Hallo {user.display_name},\n\n"
                    f"laut System bist du noch eingestempelt. "
                    f"Bitte gehe auf {cfg.public_url} und stemple aus, falls der Arbeitstag vorbei ist.\n",
                    db=db,
                    required=False,
                )
                print(f"reminded {user.username} state={state}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
