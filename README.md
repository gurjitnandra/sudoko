# Multiplayer Sudoku

A LAN-friendly multiplayer Sudoku game. Players host or join a 6-character lobby,
share one board, race for points, and chat while they play. Wrong answers cost
you: three mistakes and you are out.

- **Backend:** FastAPI + Uvicorn (`app/`)
- **Frontend:** vanilla JS + CSS served by FastAPI (`templates/`, `static/`)
- **Gameplay state:** in-process memory (`session_manager.py`, `sudoku_core.py`)
- **Accounts / wallet / game records:** MongoDB (`app/services/`, optional for playing)

---

## 1. Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.12 | Older 3.10+ should work; 3.12 is what this is developed on |
| MongoDB 6+ | Only needed for accounts, credits, and saved game results — **not** for playing Sudoku |
| A browser | Chrome, Firefox, Edge… one per player |

MongoDB on Debian/Ubuntu:

```bash
sudo apt install -y mongodb-org   # or follow MongoDB's official install docs
sudo systemctl enable --now mongod
```

## 2. Clone and install

```bash
git clone https://github.com/gurjitnandra/sudoko.git
cd sudoko

python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt
```

## 3. Configure (optional)

Everything has a working default, so you can skip this for local play. To
override, create a `.env` file next to `app.py`:

```ini
APP_NAME=Sudoku Multiplayer Backend
ENVIRONMENT=development          # "production" makes session cookies HTTPS-only
DEBUG=false

MONGO_URI=mongodb://localhost:27017/sudoku
MONGO_DB_NAME=sudoku

# CHANGE THESE before exposing the app to anything but your own LAN
JWT_SECRET_KEY=replace-with-a-long-random-string
JWT_REFRESH_SECRET_KEY=replace-with-another-long-random-string
ACCESS_TOKEN_EXPIRE_MINUTES=15

BACKEND_CORS_ORIGINS=http://localhost:8000
```

> Keep `ENVIRONMENT=development` while testing over plain `http://` on a LAN IP.
> Cookies are marked `Secure` in any other environment, which means browsers
> silently drop them on non-HTTPS connections.

## 4. Set up MongoDB (only for accounts / credits)

Registration and wallet writes run inside a **MongoDB transaction**, and
transactions require a replica set. A standalone `mongod` will fail with
`Transaction numbers are only allowed on a replica set member or mongos`, and
no database or collections will ever be created.

Turn your single node into a one-member replica set:

```bash
# 1. enable replication
sudo tee -a /etc/mongod.conf >/dev/null <<'EOF'
replication:
  replSetName: rs0
EOF
sudo systemctl restart mongod

# 2. initiate the set (once, ever)
venv/bin/python - <<'EOF'
from pymongo import MongoClient
c = MongoClient("mongodb://localhost:27017", directConnection=True)
print(c.admin.command({"replSetInitiate": {"_id": "rs0",
      "members": [{"_id": 0, "host": "127.0.0.1:27017"}]}}))
EOF
```

Verify it became primary — this must print `rs0 True`:

```bash
venv/bin/python -c "
from pymongo import MongoClient
h = MongoClient('mongodb://localhost:27017', directConnection=True).admin.command('hello')
print(h.get('setName'), h.get('isWritablePrimary'))"
```

If it prints `None False` and the server logs `RSGhost`, `replSetName` is
configured but step 2 never ran.

There is no migration or seed script: the `sudoku` database and its
`users`, `wallets`, `transactions`, `refresh_tokens`, `games` collections are
created automatically on the first successful registration.

## 5. Run

```bash
venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then open:

- `http://localhost:8000/` — the game
- `http://<your-lan-ip>:8000/` — for other players on your network
- `http://localhost:8000/docs` — interactive API docs
- `http://localhost:8000/health` — liveness check

> **Run exactly one worker.** Lobbies live in the server process's memory, so
> multiple workers would put the host and the joiner on different processes
> ("Session not found"), and any restart ends all lobbies in progress.

During development, `--reload` saves you the manual restarts:

```bash
venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 6. Play

1. **Host:** enter a name, pick a difficulty, click *Create & Host*. A
   6-character session ID appears in the sidebar.
2. **Everyone else:** enter a name plus that session ID and click *Join Game*.
3. Click a cell and type `1`–`9` (or use the number pad). Arrow keys move,
   `0`/`Backspace` clears.

Rules the server enforces:

- Only the **correct** value sticks. A wrong value is a mistake; **3 mistakes
  and you are eliminated** (your board blurs and your moves are rejected).
- Correct entries score 1 point and are tinted with your player colour. Given
  cells and already-solved cells cannot be changed.
- Every player's current cell is highlighted live for everyone, and the board
  refreshes by polling every 5 seconds.
- Only the **host** can restart the puzzle, and only once everyone is eliminated.
- **Leaving is final:** that browser cannot rejoin the same lobby. When the last
  player leaves, the lobby is deleted.

**Several players on one computer?** Use a different browser (or a separate
Chrome profile / private window) per player. Identity is a per-browser
`sudoku_client` cookie, so separate browsers are separate players — but two tabs
of the *same* browser share one identity.

## 7. Accounts, credits, and wallet (optional)

The Sudoku game is playable as a guest and never touches MongoDB. The account
layer is a separate REST API under `/api/v1`, used by `/login`:

```bash
# register (new users start with 100 credits)
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","email":"alice@example.com","password":"Test1234!","display_name":"Alice"}'

# log in — returns JWTs and sets the session cookie
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"Test1234!"}'

# authenticated calls
curl http://localhost:8000/api/v1/auth/me      -H "Authorization: Bearer <access_token>"
curl http://localhost:8000/api/v1/wallet/balance -H "Authorization: Bearer <access_token>"
```

Other routers: `/api/v1/wallet/*` (balance, transactions) and
`/api/v1/game/*` (buy-in games, scores, payouts) — see `/docs`.

## 8. Layout

```
app/
  main.py            FastAPI app factory, page routes, router wiring
  api/legacy.py      the endpoints the game UI actually uses (/api/session/...)
  api/v1/            auth, wallet, game REST API (MongoDB-backed)
  core/              settings, JWT/password helpers, login-session store
  db/mongo.py        Motor client + database accessor
  models/ schemas/   Pydantic models
  services/          auth, users, wallet, games business logic
  ws/                WebSocket manager and router (not used by the current UI)
session_manager.py   in-memory lobbies: players, scores, claims, chat
sudoku_core.py       board state, validation, completion checks
sudoku_generator.py  puzzle generation per difficulty
templates/           index.html (game), login.html
static/              app.js (game client), auth.js, styles.css
app.py               original standalone Flask version — superseded by app/, not run
```

## 9. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `RSGhost`, or `ServerSelectionTimeoutError: No servers match selector` | Replica set configured but never initiated — run step 2 of §4 |
| `Transaction numbers are only allowed on a replica set member or mongos` | Standalone `mongod` — do §4 |
| Registration 500s, `sudoku` DB never appears | Same as above |
| `Session not found.` right after a friend hosted | Server restarted, or you are running more than one worker — see §5 |
| `This browser has left the lobby and cannot rejoin.` | That browser clicked *Leave Game*. Use another browser/profile, or host a fresh lobby |
| `This player belongs to a different browser session.` | The player was created in a different browser; rejoin from this one |
| Board stays blank, nothing happens after joining | Stale cached `static/app.js` — hard-refresh (Ctrl+Shift+R) |
| Logged in, but the app acts like a guest | Cookie was dropped: you are on plain HTTP with `ENVIRONMENT` not set to `development` |
| `email-validator is not installed` | `venv/bin/pip install -r requirements.txt` again |
