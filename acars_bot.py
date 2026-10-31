"""Watch VATSIM for CVY<digit>* flights; send a random Hoppie ACARS telex on climb and after landing.

Stdlib only. Config via environment variables:
  HOPPIE_LOGON   Hoppie ACARS logon code (required, keep it a secret)
  CALLSIGN_REGEX   callsigns to watch by pattern (default ^CVY[0-9])
  EXTRA_CALLSIGNS  comma-separated exact callsigns to watch as well (e.g. QFA7344,JST675)
  FROM_STATION   sender name shown on telex   (default COMPANY)
  POLL_SECONDS   delay between polls          (default 20)
  DRY_RUN        "1" = print instead of send
"""
import json
import os
import random
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

VATSIM_URL = "https://data.vatsim.net/v3/vatsim-data.json"
HOPPIE_URL = "https://www.hoppie.nl/acars/system/connect.html"
HERE = Path(__file__).parent
STATE_FILE = HERE / "state.json"
ADS_FILE = HERE / "ads.json"


def load_dotenv():
    """Load KEY=VALUE lines from .env for local runs; real env vars win."""
    try:
        for line in (HERE / ".env").read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    except FileNotFoundError:
        pass


load_dotenv()

EXTRA_CALLSIGNS = {c.strip().upper() for c in os.environ.get("EXTRA_CALLSIGNS", "").split(",") if c.strip()}
CALLSIGN_RE = re.compile(os.environ.get("CALLSIGN_REGEX", r"^CVY[0-9]"))
FROM_STATION = os.environ.get("FROM_STATION", "COMPANY").upper()
POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "20"))
DRY_RUN = os.environ.get("DRY_RUN") == "1"

FOOTER = "\nAUTOMATED PARODY. NOT AFFILIATED."
# One telex only: the client shows just the newest message per poll, and Hoppie caps packets at ~220.
TELEX_MAX = 220

GROUND_SPEED_MAX = 40       # kt; at or below this we treat the aircraft as on the ground
AIRBORNE_SPEED_MIN = 50     # kt
TAKEOFF_CLIMB_FT = 100      # ft above recorded field altitude = airborne
CLIMB_MSG_ALT = 10000       # ft; sterile cockpit, send the climb ad above this
LANDING_SPEED_MAX = 50      # kt; below this after flying = landed / taxiing in
LANDING_HOLD_SECONDS = 60   # must stay below LANDING_SPEED_MAX this long
LANDING_ALT_MAX = 5000      # ft; ignore a paused sim at altitude
RESET_AFTER_MISSING = 30 * 60  # s offline before a flight's state is dropped
DISCONNECT_POLLS = 3        # empty polls in a row before a flight counts as disconnected


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"flights": {}}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def get_pilots():
    req = urllib.request.Request(VATSIM_URL, headers={"User-Agent": "acars-bot/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    return [p for p in data["pilots"]
            if CALLSIGN_RE.match(p["callsign"].upper()) or p["callsign"].upper() in EXTRA_CALLSIGNS]


def send_telex(to, message):
    params = {
        "logon": os.environ.get("HOPPIE_LOGON", ""),
        "from": FROM_STATION,
        "to": to,
        "type": "telex",
        "packet": " ".join(message.upper().split()),  # client drops telex containing line breaks
    }
    if DRY_RUN:
        print(f"[dry run] would send to {to}: {params['packet']}")
        return "ok"
    body = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(HOPPIE_URL, data=body, timeout=20) as r:
        return r.read().decode().strip()


def pick_ad(kind, avoid=None):
    """Random ad from the `kind` category plus 'general', avoiding `avoid` if possible."""
    cats = json.loads(ADS_FILE.read_text(encoding="utf-8"))
    pool = cats.get(kind, []) + cats.get("general", [])
    return random.choice([a for a in pool if a != avoid] or pool)


def send_ad(callsign, kind, st):
    """Send a random ad of `kind` (climb|landing) or general. True if Hoppie said ok."""
    ad = pick_ad(kind, st.get("last_ad"))
    text = ad + FOOTER
    if len(text) > TELEX_MAX:
        print(f"{callsign}: ad too long ({len(text)} > {TELEX_MAX}), not sent: {ad[:40]}")
        return False
    result = send_telex(callsign, text)
    print(f"{callsign}: sent {kind} ad ({len(text)} chars) -> {result}")
    if result.lower().startswith("ok"):
        st["last_ad"] = ad
        return True
    return False


def update_flight(callsign, st, p, now):
    alt, gs = p["altitude"], p["groundspeed"]
    st["last_seen"] = now

    if not st.get("flew"):
        if gs <= GROUND_SPEED_MAX:
            st["ground_alt"] = alt  # field altitude (VATSIM reports MSL)
            st["seen_ground"] = True
        # Only count a takeoff if we saw it on the ground first (ignores mid-flight joins).
        elif (st.get("seen_ground") and gs >= AIRBORNE_SPEED_MIN
              and alt > st["ground_alt"] + TAKEOFF_CLIMB_FT):
            st["flew"] = True
            print(f"{callsign}: airborne")

    if not st.get("flew"):
        return

    if alt >= CLIMB_MSG_ALT and not st.get("climb_sent"):
        if send_ad(callsign, "climb", st):
            st["climb_sent"] = True

    if gs < LANDING_SPEED_MAX and alt < LANDING_ALT_MAX:
        st.setdefault("slow_since", now)
        if now - st["slow_since"] >= LANDING_HOLD_SECONDS:
            if send_ad(callsign, "landing", st):
                # Flight complete; start fresh so the next leg works too.
                st.clear()
                st.update(last_seen=now, seen_ground=True, ground_alt=alt)
    else:
        st.pop("slow_since", None)


def poll(state):
    now = time.time()
    flights = state.setdefault("flights", {})
    seen = set()
    for p in get_pilots():
        cs = p["callsign"].upper()
        seen.add(cs)
        st = flights.setdefault(cs, {})
        update_flight(cs, st, p, now)
        print(f"{cs}: alt={p['altitude']} gs={p['groundspeed']} state={ {k: v for k, v in st.items() if k != 'last_seen'} }")
    for cs in list(flights):
        if cs not in seen and now - flights[cs].get("last_seen", 0) > RESET_AFTER_MISSING:
            print(f"{cs}: offline long enough, dropping state")
            del flights[cs]
    if not seen:
        print("No matching callsigns on VATSIM.")
    return seen


def main():
    # One scan; if a matching flight is online, keep polling until it disconnects.
    state = load_state()
    flying = False
    missing = 0
    while True:
        try:
            seen = poll(state)
            save_state(state)
        except Exception as e:  # network blips shouldn't end a flight
            print(f"Error: {e}")
            seen = flying
        if seen:
            flying, missing = True, 0
        elif flying:
            missing += 1
        if not flying or missing >= DISCONNECT_POLLS:
            break
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
