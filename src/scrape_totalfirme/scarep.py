"""
Scrape every CUI from the totalfirme.ro county listing
through the Tor network.

Requirements:
    pip install requests[socks] beautifulsoup4
    # Tor must be running and exposing a SOCKS port:
    #   Linux   : systemctl start tor          -> SOCKS 127.0.0.1:9050
    #   Tor Br. : Tor Browser running          -> SOCKS 127.0.0.1:9150

Usage:
    python scrape_cui.py                          # all pages -> cui_buzau.csv
    python scrape_cui.py --max-pages 5
    python scrape_cui.py --socks-port 9150        # Tor Browser's port
    python scrape_cui.py --rotate                 # new circuit every page
    python scrape_cui.py --rotate --control-port 9051 --control-password secret
"""

import argparse
import csv
import re
import socket
import sys
import time

import requests
from bs4 import BeautifulSoup

BASE = "https://www.totalfirme.ro/judet-BUCURE%C8%98TI"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
    "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8",
}

CUI_RE = re.compile(r"^\d{6,10}$")


# --------------------------------------------------------------------------
# Tor helpers
# --------------------------------------------------------------------------
def tor_session(socks_host: str, socks_port: int) -> requests.Session:
    """A requests.Session whose entire traffic goes through Tor.

    socks5h:// is important: the 'h' makes the *hostname* be resolved by Tor,
    not locally, so no DNS leak.
    """
    proxy = f"socks5h://{socks_host}:{socks_port}"
    s = requests.Session()
    s.proxies = {"http": proxy, "https": proxy}
    return s


def check_tor(session: requests.Session) -> None:
    """Fail fast if Tor isn't reachable, and report the exit IP."""
    try:
        r = session.get("https://check.torproject.org/api/ip", timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        sys.exit(f"[!] Cannot reach Tor SOCKS proxy / check service: {e}\n"
                 f"    Is Tor running and is the SOCKS port correct?")
    if not data.get("IsTor"):
        sys.exit("[!] Traffic is NOT going through Tor. Aborting.")
    print(f"[tor] exit node IP: {data.get('IP')}")


def new_circuit(host: str = "127.0.0.1", port: int = 9051,
                password: str | None = None, timeout: float = 10.0) -> None:
    """Ask the Tor control port for a fresh circuit (NEWNYM).

    Requires ControlPort + CookieAuthentication/HashedControlPassword in
    torrc. If anything fails we just warn and keep the current circuit.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            s.settimeout(timeout)

            def cmd(line: str) -> str:
                s.sendall((line + "\r\n").encode())
                time.sleep(0.1)
                return s.recv(4096).decode(errors="replace")

            if password:
                reply = cmd(f'AUTHENTICATE "{password}"')
                if not reply.startswith("250"):
                    print(f"  [tor] control auth failed: {reply.strip()}",
                          file=sys.stderr)
                    return
            else:
                # try cookie / null auth
                cmd("AUTHENTICATE")

            cmd("SIGNAL NEWNYM")
        print("  [tor] requested new circuit")
        time.sleep(1.0)  # give Tor a moment to switch
    except Exception as e:
        print(f"  [tor] could not rotate circuit: {e}", file=sys.stderr)


# --------------------------------------------------------------------------
# Scraping
# --------------------------------------------------------------------------
def fetch(session: requests.Session, url: str, retries: int = 3,
          timeout: int = 45) -> str:
    """GET a URL through Tor with retries. Tor is slow, so timeout is high."""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        except requests.RequestException as e:
            last_err = e
            print(f"  ! attempt {attempt}/{retries} failed: {e}",
                  file=sys.stderr)
            time.sleep(3 * attempt)
    raise RuntimeError(f"Could not fetch {url}") from last_err


def parse_rows(html: str):
    soup = BeautifulSoup(html, "html.parser")
    tbody = soup.select_one("table.table tbody")
    rows = []
    if tbody is None:
        return rows

    for tr in tbody.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue

        cui = tds[-1].get_text(strip=True)
        if not CUI_RE.match(cui):
            continue

        rows.append({"cui": cui})
    return rows


def has_next_page(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    return soup.select_one('a[rel="next"]') is not None


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Scrape CUIs via Tor")
    ap.add_argument("-o", "--output", default="cui.csv")
    ap.add_argument("--max-pages", type=int, default=None)
    ap.add_argument("--delay", type=float, default=3.0,
                    help="seconds between page requests (Tor is slow; default 3)")
    ap.add_argument("--socks-host", default="127.0.0.1")
    ap.add_argument("--socks-port", type=int, default=9050,
                    help="9050 (tor daemon) or 9150 (Tor Browser)")
    ap.add_argument("--rotate", action="store_true",
                    help="request a NEWNYM circuit before each page")
    ap.add_argument("--control-port", type=int, default=9051)
    ap.add_argument("--control-password", default=None)
    args = ap.parse_args()

    session = tor_session(args.socks_host, args.socks_port)
    check_tor(session)

    seen = set()
    empty_streak = 0
    page = 1

    try:
        f = open(args.output, "w", newline="", encoding="utf-8")
    except OSError as e:
        sys.exit(f"[!] cannot open output file: {e}")

    with f:
        writer = csv.DictWriter(
            f, fieldnames=["cui"])
        writer.writeheader()

        while True:
            if args.max_pages is not None and page > args.max_pages:
                print(f"Reached --max-pages ({args.max_pages}), stopping.")
                break

            if args.rotate and page > 1:
                new_circuit("127.0.0.1", args.control_port,
                            args.control_password)

            url = BASE if page == 1 else f"{BASE}?page={page}"
            print(f"[page {page}] {url}")

            try:
                html = fetch(session, url)
            except RuntimeError as e:
                print(f"  {e} -- stopping.", file=sys.stderr)
                break

            rows = parse_rows(html)
            if not rows:
                print("  no rows found -- stopping.")
                break

            new = 0
            for row in rows:
                if row["cui"] in seen:
                    continue
                seen.add(row["cui"])
                writer.writerow(row)
                new += 1
            f.flush()

            if not has_next_page(html):
                print("  no 'next' link -- end of list.")
                break

            page += 1
            time.sleep(args.delay)

    print(f"\nDone. {len(seen)} unique CUIs written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
