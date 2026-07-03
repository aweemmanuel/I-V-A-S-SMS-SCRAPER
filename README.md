# 🤖 IVASMS OTP Telegram Bot

A custom Telegram bot for fetching OTP codes from your **IVASMS.com** account.
Built with **aiogram 3.x** + **SQLite** + inline buttons (no slash commands
beyond the initial `/start`). Designed for **Railway** deployment.

> Built by analyzing 5 reference GitHub projects. See **Differences from the
> reference repos** below for what's new.

---

## ✨ Features

- **Button-driven UI** — main menu is a 2-column grid, every action is an
  inline button. Matches the "EMMY IVASMS BOT" screenshot style.
- **Multi-user** — each Telegram user links their own IVASMS account
  (email/password or cookies JSON). No shared credentials.
- **Auto-poll OTP** — once you pick a number, the bot polls IVASMS every 10s
  for 5 minutes and pushes the OTP to your chat the instant it arrives.
- **Pretty formatting** — OTP codes in `<code>` blocks (tap to copy), country
  flags next to phone ranges, card-style separators.
- **Two auth methods** — email+password (like 4 of 5 reference repos) **or**
  exported cookies JSON (like Arslan-MD/IvaSms-api). Cookies bypass
  reCAPTCHA / 2FA on IVASMS login.
- **Cloudflare bypass** — uses `cloudscraper` so it doesn't get blocked by
  IVASMS's Cloudflare protection.
- **Rate limiting** — per-user cooldown prevents IVASMS from banning your
  account for spammy API calls.
- **Persistent storage** — SQLite keeps your credentials, order history, and
  stats across redeploys.
- **Health endpoint** — Railway-friendly `/health` HTTP server so the
  container is marked healthy.

---

## 📂 Project structure

```
ivasms-bot/
├── bot/
│   ├── __init__.py
│   ├── main.py              # entry point: aiogram + uvicorn health server
│   ├── config.py            # env-driven settings (pydantic-settings)
│   ├── database.py          # async SQLite (aiosqlite) — users, orders, stats
│   ├── ivasms.py            # IVASMS.com client (cloudscraper + BeautifulSoup)
│   ├── otp_poller.py        # background auto-poll task per user
│   ├── keyboards.py         # inline keyboard builders (grid menu, pickers)
│   ├── messages.py          # pretty HTML message templates
│   └── handlers/
│       ├── __init__.py      # router registry
│       ├── common.py        # FSM states, rate limiter, decorators
│       ├── start.py         # /start + main menu + account-setup wizard
│       ├── numbers.py       # 📱 Get Number flow (ranges → numbers)
│       ├── otp.py           # 💬 Get OTP flow (auto-poll + push)
│       └── status.py        # 📊 Status + 📜 History
├── data/                    # SQLite file lives here (mounted as volume)
├── Dockerfile               # multi-stage Python 3.11 slim image
├── railway.toml             # Railway config-as-code (healthcheck + volume)
├── Procfile                 # alternative: `web: python -m bot.main`
├── requirements.txt
├── .env.example             # copy to .env and fill in
├── .dockerignore
├── .gitignore
└── start.sh                 # local dev convenience script
```

---

## 🚀 Quick start (local)

```bash
# 1. Clone & enter
git clone <your-fork-url> ivasms-bot
cd ivasms-bot

# 2. Copy env template and fill in your bot token
cp .env.example .env
#   → edit .env, set TELEGRAM_BOT_TOKEN (from @BotFather)

# 3. Install deps
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 4. Run
./start.sh
# or: python -m bot.main
```

Open Telegram → message your bot → `/start` → tap **🔑 Account** →
**➕ Add IVASMS Account** → pick **📧 Email + Password** (or **🍪 Cookies JSON**)
→ enter your IVASMS.com credentials.

---

## ☁️ Deploy to Railway

Railway is the recommended host — persistent volume for SQLite, automatic
HTTPS health check, and free hobby tier covers a single bot easily.

### Option A — one-click deploy via Dockerfile (recommended)

1. **Fork this repo** to your GitHub.
2. Go to <https://railway.app> → **New Project** → **Deploy from GitHub repo**
   → pick your fork.
3. Railway detects the `Dockerfile` and builds it automatically.
4. In the Railway service → **Variables** tab, add:
   | Variable | Value |
   |---|---|
   | `TELEGRAM_BOT_TOKEN` | your bot token from @BotFather |
   | `ADMIN_IDS` | your Telegram user ID (optional) |
   | `DATABASE_PATH` | `/data/ivasms_bot.db` |
   | `HEALTH_PORT` | `$PORT` (Railway auto-injects `$PORT`) |
5. In the Railway service → **Settings** → **Volumes** → **Add Volume**:
   - Mount path: `/data`
   - This makes the SQLite DB persist across redeploys.
6. Railway will rebuild & deploy. The **Deployments** tab shows logs.
7. Once `🤖 Bot started: @your_bot` appears in logs, message your bot on Telegram.

### Option B — Procfile deploy (if you skip Docker)

Railway also detects the `Procfile` and runs `web: python -m bot.main` directly
with a Python buildpack. Same env vars and volume as Option A.

### Verifying it's healthy

Railway pings `/health` every 30s. The **Deployments** tab shows a green
✓ when healthy. The endpoint returns:

```json
{ "status": "ok", "service": "ivasms-otp-bot", "active_polls": 0 }
```

---

## 🎮 Using the bot

After `/start` you'll see a 2-column grid menu:

```
┌──────────────────┬──────────────────┐
│  📱 Get Number   │  💬 Get OTP      │
├──────────────────┼──────────────────┤
│  ❌ Cancel        │  📊 Status        │
├──────────────────┼──────────────────┤
│  🔑 Account      │  📜 History      │
└──────────────────┴──────────────────┘
```

| Button | What it does |
|---|---|
| 📱 **Get Number** | Fetches today's phone ranges from IVASMS → tap a range → tap a number |
| 💬 **Get OTP** | If you've picked a number, starts auto-polling for new SMS |
| ❌ **Cancel** | Stops any active polling session |
| 📊 **Status** | IVASMS stats for today + your personal counters |
| 🔑 **Account** | Add / test / remove your IVASMS credentials |
| 📜 **History** | Your 10 most recent OTP retrievals |

**Typical flow:** `/start` → 🔑 Account → add credentials → 📱 Get Number →
tap range → tap number → bot auto-polls → 🆕 OTP pushed to your chat.

---

## 🔑 Getting IVASMS cookies (alternative auth)

If IVASMS shows a reCAPTCHA on email/password login, use cookies instead:

1. Open <https://www.ivasms.com> in Chrome / Firefox and log in normally.
2. Install the **Cookie-Editor** extension
   ([Chrome](https://chrome.google.com/webstore/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm),
   [Firefox](https://addons.mozilla.org/en-US/firefox/addon/cookie-editor/)).
3. Click the extension icon on the IVASMS page → **Export** → **JSON**.
4. In the bot: 🔑 Account → ➕ Add IVASMS Account → 🍪 Cookies JSON →
   paste the JSON.

Cookies expire (usually after a few weeks). When they do, the bot will show
an auth error — just re-export and re-paste.

---

## 🧩 How it works (technical)

IVASMS.com **has no public API** — every reference implementation scrapes
the web portal. This bot uses the same approach, discovered from the 5
reference repos:

| IVASMS endpoint | Used for |
|---|---|
| `GET /portal/sms/received` | Pick up CSRF token + session cookies |
| `POST /portal/sms/received/getsms` | Today's SMS stats + list of phone ranges |
| `POST /portal/sms/received/getsms/number` | Phone numbers within a range |
| `POST /portal/sms/received/getsms/number/sms` | The actual OTP message body |

`cloudscraper` handles Cloudflare's challenge; `BeautifulSoup` parses the
HTML responses. All blocking HTTP calls run in a thread executor so the
aiogram event loop never stalls.

---

## 🆚 Differences from the reference repos

| Feature | Reference repos | This bot |
|---|---|---|
| UI | `/start`, `/status`, `/check` slash commands | Inline **button grid** — zero commands except `/start` |
| Auth | Email/password (4 repos) **or** cookies (1 repo) | **Both**, user picks per-account |
| Cloudflare | `requests` (gets blocked) | `cloudscraper` (bypasses CF challenge) |
| Per-user creds | Single shared `.env` credentials | **Multi-user** — each Telegram user has own DB row |
| OTP delivery | Polls every 60s, dumps to a group | **Auto-polls every 10s**, pushes directly to user's chat |
| Storage | JSON file / in-memory | **SQLite** (persistent, queryable) |
| Rate limit | None | Per-user cooldown protects IVASMS account |
| History | None | Last 10 OTP retrievals viewable in-bot |
| Deployment | Manual Flask + gunicorn | **Railway-ready** Dockerfile + `railway.toml` + `/health` |
| Pretty format | Plain text | `<code>` blocks (tap-to-copy), flags, separators |
| Background poll | Blocks forever in a thread | Per-user `asyncio.Task`, cancellable via button |

---

## 🛠️ Configuration reference

All settings come from env vars (see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | *(required)* | From @BotFather |
| `ADMIN_IDS` | *(empty)* | Comma-separated admin Telegram IDs |
| `IVASMS_DEFAULT_EMAIL` | *(empty)* | Fallback creds if user hasn't linked |
| `IVASMS_DEFAULT_PASSWORD` | *(empty)* | Fallback creds |
| `IVASMS_DEFAULT_COOKIES_JSON` | *(empty)* | Fallback cookies |
| `OTP_POLL_INTERVAL_SECONDS` | `10` | Polling frequency |
| `OTP_POLL_TIMEOUT_SECONDS` | `300` | Auto-poll session lifetime (5 min) |
| `USER_COOLDOWN_SECONDS` | `5` | Per-user cooldown between API calls |
| `DATABASE_PATH` | `data/ivasms_bot.db` | SQLite path |
| `HEALTH_PORT` | `8080` | Health server port (set to `$PORT` on Railway) |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

---

## 🧯 Troubleshooting

| Symptom | Fix |
|---|---|
| `Invalid TELEGRAM_BOT_TOKEN` | Get a fresh token from @BotFather |
| `IVASMS login failed` | Try 🍪 cookies auth instead of email/password |
| `Could not load IVASMS portal` | Cookies expired — re-export and re-paste |
| Bot is silent after Get OTP | Make sure IVASMS received an SMS today (check the web portal) |
| `getsms failed (HTTP 419)` | CSRF token mismatch — reconnect via 🔑 Account |
| Railway shows unhealthy | Confirm `HEALTH_PORT=$PORT` and the volume is mounted at `/data` |

---

## ⚠️ Disclaimer

This bot is an independent tool and is **not affiliated with IVASMS.com**.
It uses the same public web endpoints that the IVASMS dashboard uses in a
browser. Use it only with accounts you own. Scraping may break if IVASMS
changes their HTML structure — patches welcome.

---

## 📜 License

MIT — see `LICENSE` (or treat as MIT if no LICENSE file is present).
