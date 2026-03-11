# Prison Messaging App

A Dockerised Django app on PostgreSQL for managed messaging between prisoners and their families (customers). Officers can inspect messages.

## Roles

- **Super Admin** / **Admin** — full access
- **Officer** — can list and inspect messages (mark as inspected)
- **Prisoner** — can send/receive messages only with linked customers
- **Customer** — can send/receive messages only with linked prisoners (recipients)

Messaging is allowed only between customer–prisoner pairs defined in **Customer Recipients**.

## Quick start

1. Copy environment example and adjust if needed:
   ```bash
   cp .env.example .env
   ```

2. Run with Docker Compose:
   ```bash
   docker compose up --build
   ```

3. Open the admin: http://localhost:8000/admin/

4. Log in with any of the fixture users. **Default password for all fixture users: `password`**

### How users sign in

Sign-in is via **Django Admin** at **http://localhost:8000/admin/** (username + password). Only users with staff access can log in there: **superadmin**, **admin1**, **officer1**, **officer2**. Prisoners and customers (`prisoner1`, `customer1`, etc.) have no admin access in this setup; they exist in the database for messaging and could be given a separate login later (e.g. a custom app or API).

### Where test credentials are kept

- **Usernames and roles** are listed in the **Fixture users** table below (and in the admin once you’re logged in).
- **Password:** The shared password for all fixture users is **`password`**. It is not stored in code or config; it’s only documented here in the README. The fixture file stores only a **hashed** version so the DB never contains the plaintext.
- **Fixture data:** User records (with hashed passwords) are in **`core/fixtures/users.json`**; threads in **`threads.json`**; messages in **`messages.json`**. Load order: `users` → `recipients` → `threads` → `messages` (when you run `loaddata` or when the Docker `web` service starts via `entrypoint.sh`). To change or add test data, edit the fixtures and re-run `loaddata`, or use the admin and optionally `dumpdata` to refresh fixtures.

### Fixture users

| Username    | Role        | Notes                    |
|------------|-------------|--------------------------|
| superadmin | Super Admin | Full access              |
| admin1     | Admin       | Staff access              |
| officer1   | Officer     | Can inspect messages     |
| officer2   | Officer     | Can inspect messages     |
| prisoner1  | Prisoner    | James Smith              |
| prisoner2  | Prisoner    | David Jones              |
| prisoner3  | Prisoner    | Robert Brown             |
| customer1  | Customer    | Sarah Smith (family)     |
| customer2  | Customer    | Emma Jones               |
| customer3  | Customer    | Lisa Brown               |
| customer4  | Customer    | Maria Garcia             |

The app loads fixtures on startup (`users`, `recipients`, `messages`), so sample messages and customer–prisoner links are available after the first run.

## Local development (without Docker)

The app **requires PostgreSQL**. If you run it in a venv with no database (or wrong connection settings), it will crash when Django tries to connect—e.g. on `runserver`, `migrate`, or opening the admin.

**Option A — Database in Docker, Django in venv (recommended)**  
The `db` container exposes port 5432 so your venv can connect to `localhost:5432`. If you already have PostgreSQL running on your machine (e.g. Homebrew), stop it so Docker can use 5432, or you’ll get “password authentication failed” because Django would be talking to the wrong server.

1. **Reset the DB** so it’s created with the password in your `.env` (required if you ever had a different password or never used Docker for the DB before):

   ```bash
   docker compose down -v
   docker compose up -d db
   ```

2. In `.env`, set the same credentials the `db` container uses (e.g. from `.env.example`). The app builds the DB URL from these if `DATABASE_URL` is not set:

- `POSTGRES_USER=messaging`
- `POSTGRES_PASSWORD=...` ← **must match** the value used when you first ran `docker compose up -d db`
- `POSTGRES_DB=messaging`
- `POSTGRES_HOST=localhost` (optional; default is localhost for venv)

If you set `DATABASE_URL` yourself, use the **same password** as `POSTGRES_PASSWORD` (e.g. `postgres://messaging:your-password@localhost:5432/messaging`).

Run migrations and load fixtures once, then start the server:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py loaddata users recipients threads messages
python manage.py runserver
```

**Option B — PostgreSQL installed locally**  
Create a database (e.g. `messaging`) and a user with access, then set `DATABASE_URL` in `.env` to match (e.g. `postgres://user:password@localhost:5432/messaging`).

---

1. Create a PostgreSQL database (e.g. `messaging`) if not using Option A.
2. Create a virtualenv and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # or .venv\Scripts\activate on Windows
   pip install -r requirements.txt
   ```
3. Set environment variables (or use a `.env` file with `django-environ`):
   - `DATABASE_URL=postgres://user:password@localhost:5432/messaging`
   - `SECRET_KEY=...`
   - `DEBUG=True`
   - `ALLOWED_HOSTS=localhost,127.0.0.1`
4. Run migrations and load fixtures:
   ```bash
   python manage.py migrate
   python manage.py loaddata users recipients threads messages
   ```
5. Run the server:
   ```bash
   python manage.py runserver
   ```

## Using a virtual environment (venv)

When developing locally (without Docker), use a virtual environment so project dependencies stay isolated from your system Python.

**Create the venv** (once per machine):

```bash
python -m venv .venv
```

Or with Python 3 explicitly: `python3 -m venv .venv`. The `.venv` folder is in `.gitignore`.

**Activate it** (do this whenever you open a new terminal to work on the project):

- **macOS / Linux:**  
  `source .venv/bin/activate`
- **Windows (Command Prompt):**  
  `.venv\Scripts\activate.bat`
- **Windows (PowerShell):**  
  `.venv\Scripts\Activate.ps1`

When active, your prompt usually shows `(.venv)`. Then install dependencies and run Django:

```bash
pip install -r requirements.txt
python manage.py runserver
```

**Deactivate** when you’re done:

```bash
deactivate
```

## Troubleshooting

**`password authentication failed for user "messaging"`**  
Either the password in `.env` doesn’t match the DB, or Django is talking to the wrong PostgreSQL.

- **Using Docker for the DB:** The `db` service must expose port 5432 (it does in this project). If you have **PostgreSQL installed on your Mac** (e.g. Homebrew, Postgres.app), it may be listening on 5432, so Django in the venv connects to that one instead of the container—and that instance has different (or no) user `messaging`. **Stop local Postgres** (e.g. `brew services stop postgresql` or quit Postgres.app) so only the Docker container is on 5432. Then recreate the container so it’s initialized with your current `.env`: run `docker compose down -v` then `docker compose up -d db`, then `python manage.py migrate` and `loaddata` again.
- **Not using Docker:** Create the `messaging` user and database on your local Postgres and set `POSTGRES_PASSWORD` / `DATABASE_URL` in `.env` to match.

## Project structure

- `config/` — Django project settings and URLs
- `core/` — Main app: User (with role), CustomerRecipient, Message
- `core/fixtures/` — Initial users, recipients, and messages
- `entrypoint.sh` — Waits for PostgreSQL, runs migrations and loaddata (users, recipients, threads, messages), then starts the app

## Licence

Private / internal use.
