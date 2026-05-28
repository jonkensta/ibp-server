# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Inside Books Project (IBP) database web interface — a Flask + SQLAlchemy app for processing book-request mail to incarcerated people. Features include label printing via DYMO JS, querying inmate data from TDCJ/FBOP, warnings/alerts on inmates, and shipment/request metrics. This is the `legacy` branch.

## Commands

Install:
```bash
pip install -r requirements.txt        # Python deps (incl. pymates from GitHub)
cd ibp/static && npm install           # JS deps (bootstrap, jquery, chart.js, DYMO)
```

Run dev server (defaults to 127.0.0.1:8000):
```bash
FLASK_ENV=development python -m ibp
# or: python -m ibp --host 0.0.0.0 --port 8000
```

Database migrations (Alembic, SQLite at `data.db`):
```bash
alembic upgrade head
alembic revision --autogenerate -m "msg"
```

Initialize a fresh DB (per README):
```python
import ibp
ibp.db.create_all()
```

There is no test suite, linter config, or CI in the repo.

## Configuration

App reads `conf/server.conf` at import time (see `ibp/base.py:read_server_config`). Sections: `server` (secret_key, apikey), `database`, `logging`, `address`, `providers` (timeout for pymates), `warnings` (cache TTL, release/postmark thresholds), `shipping`. The committed `conf/server.conf` has placeholder secrets — real deploys override `secret_key` and `apikey`. `conf/` also contains `gunicorn.service`, `gunicorn.socket`, `nginx.conf` for production.

## Architecture

Single Flask app package `ibp/`, ~1.2k LOC of Python, organized as:

- **`base.py`** — module-level singletons. Imports build `app`, `db` (Flask-SQLAlchemy with custom `DeclarativeBase` + naming convention), `csrf`, `config`, and configure logging (rotating file + in-memory `RotatingStream` exposed via `/view_log`). Importing `ibp` triggers all of this and then imports `models` and `views` for side-effects (route registration). Order matters: `base` must finish before `models`/`views` import it.
- **`models.py`** — SQLAlchemy models: `Inmate`, `Lookup`, `Request`, `Shipment`, `Comment`, `Unit`. `Inmate` is uniqued on `(jurisdiction, id)` where jurisdiction ∈ {Texas, Federal}; `Unit` is uniqued on `(jurisdiction, name)`. `Inmate.entry_is_fresh()` drives whether to re-query upstream providers (TTL from config).
- **`query.py`** — the bridge to `pymates` (external provider package, installed from `jonkensta/inmate-providers@main`). `inmates_by_autoid`, `inmates_by_inmate_id`, `inmates_by_name` each call pymates, then upsert returned records into the DB via `_build_or_update_inmate_from_response`. Provider `id` strings have dashes stripped and are stored as `int`.
- **`views.py`** — all Flask routes. Some POST endpoints are guarded by `@appkey_required`, which compares `request.form["key"]` against `config[server][apikey]` (NOT a session/login system — this is a shared-secret header for tooling). Views render Jinja templates in `ibp/templates/` and return JSON for AJAX endpoints.
- **`flask_forms.py`** — WTForms definitions for the HTML forms.
- **`warnings.py`** — pure functions computing human-readable warning strings about inmates/requests (stale data, release date proximity, postmark age). Driven by thresholds in the `[warnings]` config section.
- **`providers/`** — currently empty (only `__pycache__`); provider logic lives in the external `pymates` package.

Frontend is server-rendered Jinja + Bootstrap 3 + jQuery. The DYMO label printing uses `DYMO.Label.Framework.3.0.js` (vendored, not via npm) plus an XML template `templates/request_label.xml` rendered server-side and posted to the local DYMO service.

Auxiliary scripts live in `tools/` (`label.py`, `ship.py`, `migrate.py`) — standalone CLIs, not imported by the app.

## Gotchas

- Importing `ibp` (or anything under it) reads `conf/server.conf` and opens log files immediately — there's no app factory.
- `pymates` is a git dependency on branch `main` (see commit `ed0bcff`); a fresh `pip install` needs network access to GitHub.
- The DB file (`data.db`) is gitignored but a copy exists in the working tree; `data.new.db` appears to be a scratch/migration artifact.
- `Inmate.id` is an integer (digits only, dashes stripped). Recent fix (`156dd50`) enforces that queries against `inmates.id` use an integer.
