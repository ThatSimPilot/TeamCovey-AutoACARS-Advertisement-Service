# TeamCovey AutoACARS Advertisement Service

A small bot that watches [VATSIM](https://www.vatsim.net/) for flights with a matching callsign, and sends a random parody advertisement as an ACARS telex (via [Hoppie](https://www.hoppie.nl/acars/)) when the aircraft climbs through 10,000 ft and again after it lands.

It is an automated parody. It is not affiliated with any airline or advertiser.

## How it works

1. Every 5 minutes, a GitHub Actions workflow runs `acars_bot.py`, which scans the VATSIM live data feed once.
2. If a matching flight is online, the bot keeps polling until that flight has been offline for about 60 seconds. The poll rate follows the flight:
   - **1 minute:** on the ground, and climbing up to 5,000 ft.
   - **10 seconds:** from 5,000 ft until the climb ad is sent, and below 5,000 ft (for the landing ad).
   - **2 minutes:** while descending above 5,000 ft.
   - **5 minutes:** cruise after the climb ad, and when levelled off for 10 minutes or climbing again during a descent.
   - Climbing or descending means a 1,000 ft change from the last reference altitude.
3. Pilots whose callsign matches `CALLSIGN_REGEX` (default `^CVY[0-9]`) or appears in `EXTRA_CALLSIGNS` are tracked.
4. Per flight, the bot follows a small state machine:
   - **Ground:** the aircraft is at or below 40 kt. The bot records the field altitude.
   - **Airborne:** after being seen on the ground, the aircraft reaches at least 50 kt and climbs 100 ft above field altitude. Flights that are first seen in the air are ignored.
   - **Climb ad:** once above 10,000 ft, one climb ad is sent.
   - **Landing ad:** below 50 kt and under 5,000 ft for 60 seconds, one landing ad is sent. The flight state is then reset, so a following leg works too.
5. Each ad is sent as a telex from `FROM_STATION` (default `COMPANY`), with the footer `AUTOMATED PARODY. NOT AFFILIATED.`. Telex text is uppercased, and messages longer than 220 characters are not sent.
6. Flight state is saved to `state.json`. The workflow commits that file back to the repo so the next run can pick up where the last one stopped. Flights offline for more than 30 minutes are dropped.

## Repository layout

| File | Purpose |
| --- | --- |
| `acars_bot.py` | The bot. Standard library only, no dependencies to install. |
| `ads.json` | The ad pool, grouped into `climb`, `landing` and `general`. Gitignored, so you supply it yourself. |
| `ads_template.json` | Empty template with the same structure as `ads.json`. |
| `state.json` | Per-flight state written by the bot. Committed by the workflow. |
| `.github/workflows/acars.yml` | Scheduled GitHub Actions workflow. Runs every 5 minutes and on manual dispatch. |
| `.env` | Local configuration for manual runs. Gitignored. Never commit it. |

## Setup

### Requirements

- Python 3.12 or newer. The bot uses only the standard library.
- A Hoppie ACARS logon code.

### Ad pool

Copy the template and fill in your ads:

```bash
cp ads_template.json ads.json
```

Each category is a list of strings. Keep every ad short enough that `ad + "\nAUTOMATED PARODY. NOT AFFILIATED."` fits in 220 characters. Ads that are too long are skipped and logged.

### Local configuration

Create a `.env` file in the repo root:

```ini
HOPPIE_LOGON=your-logon-code
CALLSIGN_REGEX=^CVY[0-9]
EXTRA_CALLSIGNS=QFA7344,JST675
FROM_STATION=COMPANY
DRY_RUN=1
```

Real environment variables take precedence over `.env`.

### GitHub Actions

Add `HOPPIE_LOGON` as a repository secret under **Settings → Secrets and variables → Actions**. The workflow reads it from there. It also sets `CALLSIGN_REGEX` and `FROM_STATION` directly. Push access is needed because the workflow commits `state.json` with `contents: write`.

## Configuration reference

| Variable | Default | Description |
| --- | --- | --- |
| `HOPPIE_LOGON` | (none) | Hoppie logon code. Required to send. Keep it secret. |
| `CALLSIGN_REGEX` | `^CVY[0-9]` | Regex matched against upper-cased callsigns. |
| `EXTRA_CALLSIGNS` | (empty) | Comma-separated exact callsigns to watch as well. |
| `FROM_STATION` | `COMPANY` | Sender name shown on the telex. |
| `DRY_RUN` | (unset) | Set to `1` to print telexes instead of sending them. |

## Running

Dry run, with no telex sent:

```bash
DRY_RUN=1 python acars_bot.py
```

Live run, using the `.env` file:

```bash
python acars_bot.py
```

The bot prints one status line per matching pilot on each poll, showing altitude, groundspeed and flight state.

## Notes and limitations

- **`ads.json` is gitignored, but the workflow needs it.** The GitHub Actions run checks out the repo without `ads.json`, so ad selection will fail there with `FileNotFoundError`. The error is caught and logged as `Error: ...`, so nothing is sent. To make the scheduled run work, either commit `ads.json` (it has no secrets) or add it to the workflow from a secret.
- **Telex limits.** Hoppie caps packets at about 220 characters, and the client only shows the newest message per poll. The bot sends at most one telex per event.
- **Parody content.** The ads are fiction. Do not present them as real offers from real companies.
- **Ad repeats.** The bot avoids repeating the last ad it sent in the same category, when the pool allows it.

## License

No license has been specified yet.
