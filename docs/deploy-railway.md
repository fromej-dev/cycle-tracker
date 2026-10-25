# Deploying on Railway

The repository ships a `railway.json` (Dockerfile build, `/health` healthcheck,
restart on failure). The image builds the Vue frontend, serves it from Flask, runs
`flask db upgrade` on every start (the container exits if the migration fails) and
starts gunicorn on `0.0.0.0:$PORT`.

## Steps

1. **Create a project.** In Railway choose *New Project -> Deploy from GitHub repo*
   and pick your fork of this repository. Railway reads `railway.json` and builds
   the root `Dockerfile`. The first deploy will fail until steps 2 and 3 are done;
   that is expected.
2. **Add PostgreSQL.** *New -> Database -> Add PostgreSQL*. Then, on the app
   service, add a variable reference so the app can reach it:
   `DATABASE_URL` = `${{Postgres.DATABASE_URL}}` (replace `Postgres` with your
   database service's name). `postgres://` and `postgresql://` URLs are both
   accepted. `DATABASE_URL` overrides `DB_TYPE`, `POSTGRES_*` and `SQLITE_PATH`.
   Without a database the app falls back to SQLite on the container filesystem,
   which is wiped on every redeploy (a warning is logged).
3. **Set the secrets.** On the app service add two *different* random values:

   ```sh
   python -c "import secrets;print(secrets.token_hex(32))"   # run twice
   ```

   * `SECRET_KEY`
   * `JWT_SECRET_KEY`

   The app refuses to start in production if either is missing, shorter than 32
   characters, or a known default; the deploy log then names the variable.
4. **Generate a domain.** App service -> *Settings -> Networking -> Generate Domain*.
5. **(Optional) `PUBLIC_BASE_URL`.** Used to return absolute calendar-feed and
   Home Assistant URLs. If unset, the app uses `https://$RAILWAY_PUBLIC_DOMAIN`
   (set by Railway). Set it explicitly (e.g. `https://cycle.example.com`) when you
   attach a custom domain. It is never taken from the request `Host` header.
6. **(Optional) webhooks.**
   * `ALLOW_PRIVATE_WEBHOOKS=1` is only needed if webhook targets are private/LAN
     addresses. A Railway deployment cannot reach your home LAN, so leave it unset
     and use public HTTPS targets (e.g. Home Assistant via Nabu Casa or a tunnel).
   * Time-driven events (`period_expected_soon`, `fertile_window_starting`) need
     either `WEBHOOK_SCHEDULER_SECONDS=900` (a background loop in each gunicorn
     worker) or a Railway *Cron* service running `flask webhooks tick` every
     15-60 minutes. Use one of the two. Several workers are safe: each event is
     claimed with a database compare-and-swap, so it fires once per cycle.
7. **Deploy and register.** Open the generated domain and register the first user
   in the web UI. If you do not want strangers to sign up, do not share the URL;
   there is no admin approval step.

## Variables

| Variable | Required | Purpose |
|---|---|---|
| `SECRET_KEY`, `JWT_SECRET_KEY` | yes | >= 32 random chars each |
| `DATABASE_URL` | recommended | PostgreSQL connection (reference variable) |
| `PUBLIC_BASE_URL` | no | absolute URLs; defaults to `https://$RAILWAY_PUBLIC_DOMAIN` |
| `PORT` | set by Railway | gunicorn bind port |
| `WEB_CONCURRENCY` | no (2) | gunicorn worker processes |
| `GUNICORN_THREADS` | no (4) | threads per worker |
| `GUNICORN_TIMEOUT` | no (60) | worker timeout in seconds |
| `JWT_ACCESS_TOKEN_EXPIRES` | no (3600) | seconds |
| `JWT_REFRESH_TOKEN_EXPIRES` | no (30) | days |
| `ALLOW_PRIVATE_WEBHOOKS` | no | allow private/LAN webhook targets |
| `WEBHOOK_SCHEDULER_SECONDS` | no | in-process webhook scheduler interval |
| `RUN_MIGRATIONS` | no (1) | `0` skips `flask db upgrade` at start |

## Notes

* Migrations run from the container entrypoint rather than Railway's pre-deploy
  command, so the same image behaves the same on Docker and Kubernetes. A failed
  migration stops the container and the previous deployment keeps serving.
* `FLASK_ENV=production` is the image default.
* The healthcheck only confirms the process is serving; it does not touch the
  database.
