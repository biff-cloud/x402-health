"""SQLite store for probe history and the crawled catalog. Ephemeral on free hosting (rebuilt by the crawler)."""
import json, os, sqlite3, threading, time

DB = os.getenv("DB_PATH", "/tmp/x402health.db")
_lock = threading.Lock()
_conn = sqlite3.connect(DB, check_same_thread=False)
_conn.executescript("""
CREATE TABLE IF NOT EXISTS probes(url TEXT, t INTEGER, ok INTEGER, valid INTEGER, status INTEGER, latency INTEGER);
CREATE INDEX IF NOT EXISTS probes_url ON probes(url, t);
CREATE TABLE IF NOT EXISTS services(url TEXT PRIMARY KEY, method TEXT, name TEXT, description TEXT, tags TEXT,
  category TEXT, networks TEXT, price_usd REAL, sources TEXT, updated INTEGER);
""")

def record(res):
    with _lock:
        _conn.execute("INSERT INTO probes VALUES(?,?,?,?,?,?)", (res["url"], res["checkedAt"], int(res["reachable"]),
                      int(res["validX402"]), res.get("status"), res.get("latencyMs")))
        _conn.execute("DELETE FROM probes WHERE t < ?", (int(time.time()) - 30 * 86400,))
        _conn.commit()

def history(url, days=7):
    since = int(time.time()) - days * 86400
    with _lock:
        rows = _conn.execute("SELECT t, ok, valid, status, latency FROM probes WHERE url=? AND t>=? ORDER BY t", (url, since)).fetchall()
    n = len(rows)
    lat = sorted(r[4] for r in rows if r[1] and r[4] is not None)
    return {"url": url, "windowDays": days, "checks": n,
            "uptimePct": round(100 * sum(r[1] for r in rows) / n, 1) if n else None,
            "validX402Pct": round(100 * sum(r[2] for r in rows) / n, 1) if n else None,
            "medianLatencyMs": lat[len(lat) // 2] if lat else None,
            "firstSeen": rows[0][0] if rows else None, "lastChecked": rows[-1][0] if rows else None,
            "recent": [{"t": r[0], "reachable": bool(r[1]), "validX402": bool(r[2]), "status": r[3], "latencyMs": r[4]} for r in rows[-20:]]}

def upsert_service(s):
    with _lock:
        old = _conn.execute("SELECT sources FROM services WHERE url=?", (s["url"],)).fetchone()
        src = sorted(set(json.loads(old[0]) if old else []) | {s["source"]})
        _conn.execute("INSERT OR REPLACE INTO services VALUES(?,?,?,?,?,?,?,?,?,?)", (s["url"], s["method"], s["name"], s["description"][:500],
                      json.dumps(s["tags"]), s["category"], json.dumps(s["networks"]), s["price_usd"], json.dumps(src), int(time.time())))
        _conn.commit()

def services():
    with _lock:
        return _conn.execute("SELECT url, method, name, description, tags, category, networks, price_usd, sources FROM services").fetchall()

def stats(url_list=None):
    with _lock:
        return {"services": _conn.execute("SELECT COUNT(*) FROM services").fetchone()[0],
                "probes": _conn.execute("SELECT COUNT(*) FROM probes").fetchone()[0]}
