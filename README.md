# cycle-tracker

A self-hosted menstrual cycle tracker: Flask/APIFlask backend, Vue frontend,
Alembic migrations, gunicorn.

## Running

```sh
export SECRET_KEY=$(python -c "import secrets;print(secrets.token_hex(32))")
export JWT_SECRET_KEY=$(python -c "import secrets;print(secrets.token_hex(32))")
docker compose up --build
```

In production (the image default, `FLASK_ENV=production`) the app refuses to start
unless `SECRET_KEY` and `JWT_SECRET_KEY` are set to different random values of at
least 32 characters. Local development (`FLASK_ENV=development`) falls back to an
insecure default and logs a warning.

## Deployment

* Railway: [docs/deploy-railway.md](docs/deploy-railway.md)
* Kubernetes: Helm chart in `cycle-tracker/` (set `secrets.existingSecret`)
* Home Assistant integration: [docs/home-assistant.md](docs/home-assistant.md)

## Admin statistics

`/admin` shows app-wide totals: accounts, active and new people, sign-ups per
month, which features are used, median cycle and period length, the most logged
built-in symptoms and how much data is stored. It never shows names, e-mail
addresses, individual records or free-text symptoms, and health figures stay
hidden until at least 5 people contribute to them.

Nobody is an admin by default. Grant or revoke access from a shell where the app
runs (on Railway: `railway ssh`, then `cd /app`):

```sh
flask admin grant <username>
flask admin revoke <username>
```

An admin sees an "Admin" card on the Account page.

## Forecast: known limits

* All evaluation of the forecast is on synthetic data; no real-world accuracy
  claim is made.
* Only the confidence label that is shown is calibrated; the underlying numbers are not.
* 50% ranges are about 0.05 too wide on the native synthetic data.
* Late habitual skippers and users on day 32 of learning are under-covered
  (about 0.73 coverage for 80% ranges).
* Users whose pattern changes (regime change) are covered least.
* Late periods are bimodal: the headline follows the heavier possibility and the
  other is shown as a secondary window.
* The fertile window is a calendar estimate. It is not contraception or
  conception advice.
