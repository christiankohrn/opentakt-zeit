import sqlite3
from datetime import date

from app.jobs.backup import _copy_sqlite, _prune


def test_copy_sqlite_roundtrip(tmp_path):
    src = tmp_path / "app.db"
    con = sqlite3.connect(src)
    con.execute("create table t(x int)")
    con.execute("insert into t values (7)")
    con.commit()
    con.close()
    dest = tmp_path / "daily" / "2026-09-04.db"
    _copy_sqlite(src, dest)
    copied = sqlite3.connect(dest)
    assert copied.execute("select x from t").fetchone() == (7,)
    copied.close()


def test_prune_keeps_newest(tmp_path):
    folder = tmp_path / "daily"
    folder.mkdir()
    for i in range(35):
        day = date(2026, 1, 1).toordinal() + i
        name = date.fromordinal(day).isoformat()
        (folder / f"{name}.db").write_bytes(b"x")
    _prune(folder, 30)
    kept = sorted(p.name for p in folder.iterdir())
    assert len(kept) == 30
    assert kept[0] == "2026-01-06.db"
    assert kept[-1] == "2026-02-04.db"
