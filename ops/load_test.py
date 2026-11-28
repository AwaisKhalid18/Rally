"""NFR-01 load test: 100 concurrent players searching 10,000 profiles (plan.md S16 AC1).

    NFR-01 — search results within 2 seconds for at least 95% of requests at 100
    concurrent users (PRD §12.6, ASR-01, QA-01).

Standard library only: `requirements.txt` may not grow without an approved ADR
(AGENTS.md rule 10), so there is no locust, no k6 and no requests.

    python ops/load_test.py --base http://127.0.0.1:8000 --users 100 --requests 500

It signs in as one real player, then replays an authenticated search from `--users`
threads at once and reports the percentiles and the error rate. Every request goes
through the whole stack the way a player's would: session middleware, M4's single
query, the response shaper and the template.

**Read the report honestly.** This measures the server it is pointed at. A development
server is not a production one, and the numbers say so in the output rather than being
quietly presented as a production result.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import re
import statistics
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

CSRF = re.compile(r'name="csrfmiddlewaretoken" value="([^"]+)"')


def opener_with_cookies():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)), jar


def sign_in(base: str, email: str, password: str):
    """Returns an opener carrying a real session cookie."""
    opener, _ = opener_with_cookies()
    with opener.open(f"{base}/sign-in/") as response:
        token = CSRF.search(response.read().decode()).group(1)

    body = urllib.parse.urlencode(
        {"csrfmiddlewaretoken": token, "email": email, "password": password}
    ).encode()
    request = urllib.request.Request(
        f"{base}/sign-in/", data=body, headers={"Referer": f"{base}/sign-in/"}
    )
    with opener.open(request) as response:
        if response.status not in (200, 302):
            raise SystemExit(f"could not sign in: HTTP {response.status}")
    return opener


def one_search(opener, url: str):
    """One timed request. Returns (seconds, ok)."""
    started = time.perf_counter()
    try:
        with opener.open(url, timeout=30) as response:
            response.read()
            ok = response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        ok = False
    return time.perf_counter() - started, ok


def percentile(values, fraction: float) -> float:
    """The value below which `fraction` of the samples fall, nearest-rank."""
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round(fraction * len(ordered)) - 1))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", default="longenough")
    parser.add_argument("--users", type=int, default=100, help="concurrent users")
    parser.add_argument("--requests", type=int, default=500, help="total requests")
    parser.add_argument("--date", required=True, help="search date, YYYY-MM-DD")
    parser.add_argument("--area", required=True, help="area code to search in")
    parser.add_argument("--start", default="18:00")
    parser.add_argument("--end", default="20:00")
    parser.add_argument("--server", default="unspecified", help="what is being measured")
    parser.add_argument("--out", default="", help="write the result as JSON here")
    options = parser.parse_args()

    base = options.base.rstrip("/")
    query = urllib.parse.urlencode(
        {
            "date": options.date,
            "start": options.start,
            "end": options.end,
            "area_code": options.area,
        }
    )
    url = f"{base}/search/?{query}"

    print(f"signing in {options.users} players...", flush=True)
    # One session per concurrent user, as 100 separate players would have.
    openers = [sign_in(base, options.email, options.password) for _ in range(options.users)]

    # A warm-up request: the first search of a process pays for connection setup and
    # query planning, and reporting that as a player's experience would be misleading.
    one_search(openers[0], url)

    print(f"running {options.requests} requests at {options.users} concurrent...", flush=True)
    lock = threading.Lock()
    durations: list[float] = []
    failures = 0
    counter = {"next": 0}

    def worker(index: int):
        nonlocal failures
        opener = openers[index % len(openers)]
        seconds, ok = one_search(opener, url)
        with lock:
            durations.append(seconds)
            if not ok:
                failures += 1
            counter["next"] += 1
            if counter["next"] % 100 == 0:
                print(f"  {counter['next']}/{options.requests}", flush=True)

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=options.users) as pool:
        list(pool.map(worker, range(options.requests)))
    wall = time.perf_counter() - started

    p50 = percentile(durations, 0.50)
    p95 = percentile(durations, 0.95)
    p99 = percentile(durations, 0.99)
    error_rate = failures / len(durations) if durations else 1.0
    passed = p95 <= 2.0 and error_rate == 0.0

    result = {
        "server": options.server,
        "concurrent_users": options.users,
        "requests": options.requests,
        "wall_seconds": round(wall, 2),
        "requests_per_second": round(len(durations) / wall, 1) if wall else None,
        "p50_seconds": round(p50, 3),
        "p95_seconds": round(p95, 3),
        "p99_seconds": round(p99, 3),
        "max_seconds": round(max(durations), 3) if durations else None,
        "errors": failures,
        "error_rate": round(error_rate, 4),
        "nfr_01_met": passed,
    }

    print()
    print("NFR-01: search within 2 s for >= 95% of requests at 100 concurrent users")
    print(f"  measured against : {options.server}")
    print(f"  concurrent users : {options.users}")
    print(f"  requests         : {len(durations)} in {wall:.1f} s "
          f"({result['requests_per_second']}/s)")
    print(f"  p50 / p95 / p99  : {p50:.3f} s / {p95:.3f} s / {p99:.3f} s")
    print(f"  slowest          : {result['max_seconds']} s")
    print(f"  errors           : {failures} ({error_rate:.2%})")
    print(f"  NFR-01 met       : {'YES' if passed else 'NO'}")
    print()
    print("  This measures the server named above. A development server is not a")
    print("  production one; the figure is evidence for this setup, not a claim about")
    print("  deployed performance.")

    if options.out:
        with open(options.out, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
        print(f"\nwritten to {options.out}")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
