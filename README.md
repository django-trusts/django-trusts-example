# django-trusts-example

Runnable Django 6.1 application that exercises
[django-trusts](https://github.com/django-trusts/django-trusts) **1.0.0.dev0**
at revision
[`5bd2a585d3806571f95bebf89c2852cac3649d25`](https://github.com/django-trusts/django-trusts/commit/5bd2a585d3806571f95bebf89c2852cac3649d25)
(post-merge CI green on
[actions/runs/34069646754](https://github.com/django-trusts/django-trusts/actions/runs/34069646754)).

This is the implementation repository for [django-trusts#16](https://github.com/django-trusts/django-trusts/issues/16).
It does not close the parent [django-trusts#11](https://github.com/django-trusts/django-trusts/issues/11) tracker.

Requires **Python ≥ 3.12**.

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Open http://127.0.0.1:8000/ and log in. Every seeded password is `demo`.

| User | What the seed is for |
| --- | --- |
| `alice` | Owner of private notes, a shared roadmap, a public changelog, and the Acme handbook |
| `bob` | Trustee with **read** on Shared Roadmap |
| `carol` | `acme-staff` member; reads Acme Handbook through the `reader` role |
| `dave` | Outsider plus his own notes; reads Alice's work only when it is public |

## Demo workflows

1. **Create an object** — as alice (or bob), *New project*. The creator gets
   read and change trustee rows on a new trust.
2. **Change visibility** — on a project you can change, toggle public. Public
   attaches the `public-readers` group to that trust. Every signed-in account
   is enrolled in that group (seeded users and accounts created later). Log
   in as dave — or create another user — to see the list change.
3. **Grant / revoke** — grant bob or dave read (or read+change), then revoke.
4. **Another user's view** — log out and in as bob, carol, or dave. The home
   list is already filtered.
5. **Unauthorized edits** — as bob, open Alice Private Notes (403) or edit
   Shared Roadmap (403: bob has read only).

List pages paginate *after* the Trusts-table filter (`PROJECT_PAGE_SIZE`,
default 3). Direct URLs use the same `has_perm` decision as list membership.

## Checks

```bash
python manage.py test projects
```

CI runs that suite on Python 3.12–3.14 with Django 6.1 (SQLite), plus
`migrate` / `seed_demo`, collectstatic + a WhiteNoise fetch of
`/static/admin/css/base.css`. A separate job runs `migrate`, `seed_demo`,
and a Trusts list-filter query against **MySQL 8**.

## Dokku

Deploy glue for **trustsexample1.cacheca.com** on Dokku with linked MySQL 8
(`DATABASE_URL` from dokku-mysql). Local `runserver` still uses SQLite when
`DATABASE_URL` is unset.

```bash
git remote add dokku dokku@your-host:trustsexample1
git push dokku master
```

The Procfile `release` phase runs `migrate --noinput` only. Dokku does
**not** persist release-phase filesystem writes into web containers
([deployment tasks](https://dokku.com/docs/advanced-usage/deployment-tasks/)).

Static files are collected in a step whose output **is** in the web image:

- The Herokuish **Python buildpack** runs `collectstatic --noinput` at
  compile time when Django is installed. Leave `DISABLE_COLLECTSTATIC`
  unset.
- `app.json` `scripts.dokku.predeploy` also runs
  `collectstatic --noinput --skip-checks` (Dokku commits predeploy
  changes to the image). `--skip-checks` avoids needing MySQL during
  that step.

Do **not** put `seed_demo` on every deploy. After the first successful
release, seed once:

```bash
dokku run trustsexample1 python manage.py seed_demo
```

Optional config (demo defaults work without these):

| Var | Default |
| --- | --- |
| `SECRET_KEY` | Hard-coded demo key |
| `CSRF_TRUSTED_ORIGINS` | `https://trustsexample1.cacheca.com,https://*.cacheca.com` |

`ALLOWED_HOSTS` is `*` for this demo. WhiteNoise serves collected static
files (admin CSS). Gunicorn binds `example.wsgi` on `$PORT`. The MySQL
driver is **PyMySQL** (plus `cryptography` for MySQL 8
`caching_sha2_password`) so the stock Python buildpack does not need
`libmysqlclient` headers.

## Trusts dependency

`requirements.txt` / `pyproject.toml` install Trusts from the git SHA above,
not from a published PyPI 1.0. Package metadata on that revision is
`1.0.0.dev0`.

## What was reused

The default branch was a starter only. The historical
`DJANGO-TRUSTS-8-Edit-Perm-Pages` branch (PR #1) supplied the Project /
collaborator idea. The app was rewritten for Django 6.1 and the modern
Trusts API. See [docs/TRUSTS_FIT.md](docs/TRUSTS_FIT.md).

**The django-trusts library API is unchanged.** Example behavior changes
are recorded in [migrates.md](migrates.md).
