# Short It

[![Shortit](https://img.shields.io/badge/Shortit-URL%20shortener-F28B30?style=flat-square&logo=chainlink&logoColor=white)](http://winslinn.dpdns.org)
[![Powered by FastAPI](https://img.shields.io/badge/Powered%20by-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)

## Project Overview

Short It turns long URLs into short links that redirect to the original destination. Users create links from the web app after signing in and completing a security check.

## Features

- Create an account with email and password, or sign in with Google when configured.
- Shorten and copy links from the web app.
- Check submitted URLs with Google Safe Browsing and redirect visitors through `/s/{code}`.

## Tech Stack

React and Vite for the web app; Python 3.14+, FastAPI, and SQLAlchemy for the API. SQLite is the default database. Redis is used for API rate limiting.

## Getting Started

### Requirements

- Python 3.14 or newer and `uv`.
- Node.js: minimum 20.19+ or 22.12+; recommended 24, matching the frontend Docker image. See the [Vite requirements](https://v8.vite.dev/guide/).
- npm.
- A Redis server available at `redis://localhost:6379/0` (the default).
- Link creation requires both Google Safe Browsing and Cloudflare Turnstile checks to be configured and pass. Password sign-in also requires application secrets; see [Configuration](#configuration).

### Start the API

From the repository root:

```sh
pip install uv
uv sync --frozen
uv run --frozen uvicorn shortit.main:app --app-dir src --host 127.0.0.1 --port 8000 --reload --reload-dir src
```

### Start the web app

In a second terminal:

```sh
cd src/frontend
npm ci
npm run dev
```

Open the Vite URL shown in the terminal. By default, the frontend proxies API requests to `http://127.0.0.1:8000`.

Alternatively, `docker compose up --build` starts the API, web app, and Redis. Compose enables Turnstile test mode and supplies test keys. It also expects `/etc/shortit/shortit.env`, `/etc/shortit/google_cloud.env`, and `/etc/shortit/turnstile.env` to exist on the host; these files are not included in the repository.

## Configuration

Configure these variables on the API or frontend as appropriate:

| Variable | Purpose |
| --- | --- |
| `JWT_SECRET_KEY` | Signs access tokens; must be at least 32 bytes. |
| `PASSWORD_SECRET` | Required for email/password sign-in; must be at least 32 bytes. |
| `SAFE_BROWSING_API_KEY` | Required for URL safety checks on every new link. |
| `GOOGLE_CLIENT_ID` | Optional; enables Google sign-in. |
| `TURNSTILE_SECRET` | Required for production Turnstile verification. |
| `TURNSTILE_HOSTNAMES` | Required in normal mode; comma-separated hostnames allowed by Turnstile verification. |
| `VITE_TURNSTILE_SITE_KEY` | Required in production; the frontend's public Turnstile site key. |

The database defaults to `sqlite:///shortit.db`, and the API's Redis URL defaults to `redis://localhost:6379/0`. There is no `.env.example` in the repository.
