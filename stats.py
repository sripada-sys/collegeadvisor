#!/usr/bin/env python3
"""
GradesGenie analytics — run from terminal.

Usage:
  python3 stats.py                  # full dashboard
  python3 stats.py --today          # today only
  python3 stats.py --live           # auto-refresh every 30s
  python3 stats.py --since 2026-05-01
  ssh root@65.20.85.241 'cd /opt/gradesgenie && python3 stats.py'
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tutor.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def print_section(title):
    print(f"\n\033[1;36m{'─' * 60}\033[0m")
    print(f"\033[1;36m  {title}\033[0m")
    print(f"\033[1;36m{'─' * 60}\033[0m")


def print_kv(label, value, color="37"):
    print(f"  \033[{color}m{label:<30}\033[0m {value}")


def print_table(headers, rows):
    if not rows:
        print("  (none)")
        return
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    fmt = "  " + "  ".join(f"{{:<{w}}}" for w in widths)
    print(f"\033[1m{fmt.format(*headers)}\033[0m")
    for row in rows:
        print(fmt.format(*[str(c) for c in row]))


def run_stats(since=None, db_path=None):
    global DB_PATH
    if db_path:
        DB_PATH = db_path
    if not os.path.exists(DB_PATH):
        print(f"\033[31mDB not found: {DB_PATH}\033[0m")
        sys.exit(1)

    conn = get_db()
    where = ""
    params = ()
    if since:
        where = "WHERE created_at >= ?"
        params = (since,)

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    # ── Page views ──
    print_section("PAGE VIEWS")

    pages = conn.execute(f"""
        SELECT json_extract(metadata, '$.path') as path,
               COUNT(*) as hits,
               COUNT(DISTINCT json_extract(metadata, '$.ip')) as unique_ips
        FROM events
        WHERE event = 'request'
        AND json_extract(metadata, '$.method') = 'GET'
        AND json_extract(metadata, '$.path') IN ('/', '/pc', '/phone')
        {f"AND created_at >= ?" if since else ""}
        GROUP BY path ORDER BY hits DESC
    """, params).fetchall()
    print_table(["Page", "Hits", "Unique IPs"], [(r["path"], r["hits"], r["unique_ips"]) for r in pages])

    # Today vs yesterday
    for label, day in [("Today", today), ("Yesterday", yesterday)]:
        row = conn.execute("""
            SELECT COUNT(*) as hits,
                   COUNT(DISTINCT json_extract(metadata, '$.ip')) as ips
            FROM events WHERE event = 'request' AND created_at >= ? AND created_at < ?
            AND json_extract(metadata, '$.path') IN ('/', '/pc', '/phone')
        """, (day, (datetime.strptime(day, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d"))).fetchone()
        print_kv(f"  {label}", f"{row['hits']} hits, {row['ips']} unique IPs")

    # ── User actions ──
    print_section("USER ACTIONS")

    actions = conn.execute(f"""
        SELECT event, COUNT(*) as cnt
        FROM events
        WHERE event != 'request'
        {f"AND created_at >= ?" if since else ""}
        GROUP BY event ORDER BY cnt DESC
    """, params).fetchall()
    print_table(["Action", "Count"], [(r["event"], r["cnt"]) for r in actions])

    # ── Students ──
    print_section("STUDENTS")

    student_count = conn.execute("SELECT COUNT(*) as c FROM students").fetchone()["c"]
    print_kv("Total students", student_count)

    if student_count > 0:
        plans = conn.execute("SELECT plan, COUNT(*) as c FROM students GROUP BY plan").fetchall()
        for p in plans:
            print_kv(f"  {p['plan']}", p["c"])

        recent = conn.execute("""
            SELECT name, email, plan, created_at FROM students
            ORDER BY created_at DESC LIMIT 5
        """).fetchall()
        print("\n  Recent signups:")
        print_table(["Name", "Email", "Plan", "Signed up"],
                    [(r["name"], r["email"], r["plan"], r["created_at"][:16]) for r in recent])

    # ── Evaluations ──
    print_section("EVALUATIONS")

    eval_count = conn.execute(f"SELECT COUNT(*) as c FROM evaluations {where}", params).fetchone()["c"]
    print_kv("Total evaluations", eval_count)

    if eval_count > 0:
        avg = conn.execute(f"SELECT AVG(CAST(json_extract(result, '$.correctness') AS REAL)) as avg FROM evaluations {where}", params).fetchone()
        print_kv("Avg correctness", f"{avg['avg']:.1f} / 5" if avg["avg"] else "N/A")

        by_subject = conn.execute(f"""
            SELECT subject, COUNT(*) as cnt,
                   AVG(CAST(json_extract(result, '$.correctness') AS REAL)) as avg
            FROM evaluations {where}
            GROUP BY subject ORDER BY cnt DESC
        """, params).fetchall()
        print_table(["Subject", "Count", "Avg Score"],
                    [(r["subject"], r["cnt"], f"{r['avg']:.1f}" if r["avg"] else "?") for r in by_subject])

        weak = conn.execute(f"""
            SELECT json_extract(result, '$.topic') as topic,
                   COUNT(*) as cnt,
                   AVG(CAST(json_extract(result, '$.correctness') AS REAL)) as avg
            FROM evaluations {where}
            GROUP BY topic HAVING avg < 3 AND cnt >= 2
            ORDER BY avg ASC LIMIT 10
        """, params).fetchall()
        if weak:
            print("\n  Weak topics (avg < 3, 2+ attempts):")
            print_table(["Topic", "Attempts", "Avg"],
                        [(r["topic"], r["cnt"], f"{r['avg']:.1f}") for r in weak])

    # ── Practice ──
    print_section("PRACTICE PROBLEMS")
    prac = conn.execute(f"SELECT COUNT(*) as c FROM practice_problems {where}", params).fetchone()["c"]
    print_kv("Total generated", prac)

    # ── Debates ──
    print_section("DEBATES")
    debates = conn.execute(f"SELECT COUNT(*) as c FROM debate_logs {where}", params).fetchone()["c"]
    print_kv("Total exchanges", debates)

    # ── Wow Notes ──
    print_section("WOW NOTES")
    wow = conn.execute(f"SELECT COUNT(*) as c FROM wow_notes {where}", params).fetchone()["c"]
    print_kv("Total saved", wow)

    # ── Traffic by hour (today) ──
    print_section(f"TRAFFIC BY HOUR — {today}")
    hours = conn.execute("""
        SELECT substr(created_at, 12, 2) as hour,
               COUNT(*) as hits,
               COUNT(DISTINCT json_extract(metadata, '$.ip')) as ips
        FROM events WHERE event = 'request' AND created_at >= ?
        AND json_extract(metadata, '$.path') IN ('/', '/pc', '/phone')
        GROUP BY hour ORDER BY hour
    """, (today,)).fetchall()
    if hours:
        print_table(["Hour", "Hits", "Unique IPs"], [(r["hour"] + ":00", r["hits"], r["ips"]) for r in hours])
    else:
        print("  No traffic today")

    # ── Top referrers ──
    print_section("TOP REFERRERS")
    refs = conn.execute(f"""
        SELECT json_extract(metadata, '$.referrer') as ref, COUNT(*) as cnt
        FROM events WHERE event = 'request'
        AND json_extract(metadata, '$.referrer') != ''
        {f"AND created_at >= ?" if since else ""}
        GROUP BY ref ORDER BY cnt DESC LIMIT 10
    """, params).fetchall()
    if refs:
        print_table(["Referrer", "Hits"], [(r["ref"][:60], r["cnt"]) for r in refs])
    else:
        print("  (none yet)")

    # ── Device breakdown ──
    print_section("DEVICES")
    devices = conn.execute(f"""
        SELECT
            CASE
                WHEN json_extract(metadata, '$.ua') LIKE '%iPhone%' OR json_extract(metadata, '$.ua') LIKE '%Android%' THEN 'Mobile'
                WHEN json_extract(metadata, '$.ua') LIKE '%iPad%' THEN 'Tablet'
                ELSE 'Desktop'
            END as device,
            COUNT(DISTINCT json_extract(metadata, '$.ip')) as unique_ips
        FROM events WHERE event = 'request'
        AND json_extract(metadata, '$.path') IN ('/', '/pc', '/phone')
        {f"AND created_at >= ?" if since else ""}
        GROUP BY device ORDER BY unique_ips DESC
    """, params).fetchall()
    print_table(["Device", "Unique IPs"], [(r["device"], r["unique_ips"]) for r in devices])

    # ── Daily trend (last 14 days) ──
    print_section("DAILY TREND (14 DAYS)")
    daily = conn.execute("""
        SELECT date(created_at) as day,
               COUNT(*) as hits,
               COUNT(DISTINCT json_extract(metadata, '$.ip')) as ips
        FROM events WHERE event = 'request'
        AND json_extract(metadata, '$.path') IN ('/', '/pc', '/phone')
        AND created_at >= ?
        GROUP BY day ORDER BY day
    """, ((now - timedelta(days=14)).strftime("%Y-%m-%d"),)).fetchall()
    if daily:
        max_hits = max(r["hits"] for r in daily)
        for r in daily:
            bar_len = int(40 * r["hits"] / max_hits) if max_hits > 0 else 0
            bar = "█" * bar_len
            print(f"  {r['day']}  {bar} {r['hits']} ({r['ips']} IPs)")
    else:
        print("  No data yet")

    # ── Model health ──
    print_section("MODEL HEALTH (from latest log)")
    log_file = os.path.join(os.path.dirname(DB_PATH), "app.log")
    if os.path.exists(log_file):
        with open(log_file) as f:
            lines = f.readlines()
        for line in reversed(lines):
            if "OK" in line or "ERROR" in line or "NO CREDITS" in line:
                status = line.strip().split("] ", 1)[-1] if "] " in line else line.strip()
                if any(k in status.lower() for k in ["openai", "gemini", "claude", "perplexity"]):
                    print(f"  {status}")
                    break
    else:
        print("  (no log file)")

    conn.close()
    print(f"\n\033[2m  DB: {DB_PATH}  |  Generated: {now.strftime('%Y-%m-%d %H:%M:%S')}\033[0m\n")


def main():
    parser = argparse.ArgumentParser(description="GradesGenie analytics")
    parser.add_argument("--today", action="store_true", help="Show today only")
    parser.add_argument("--since", type=str, help="Show data since date (YYYY-MM-DD)")
    parser.add_argument("--live", action="store_true", help="Auto-refresh every 30s")
    parser.add_argument("--db", type=str, help="Path to DB file (for remote)")
    args = parser.parse_args()

    since = None
    if args.today:
        since = datetime.now().strftime("%Y-%m-%d")
    elif args.since:
        since = args.since

    if args.live:
        try:
            while True:
                os.system("clear")
                print("\033[1;33m  ⟳ LIVE MODE — refreshing every 30s (Ctrl+C to stop)\033[0m")
                run_stats(since=since, db_path=args.db)
                time.sleep(30)
        except KeyboardInterrupt:
            print("\nStopped.")
    else:
        run_stats(since=since, db_path=args.db)


if __name__ == "__main__":
    main()
