# django-trusts-example

Runnable Django 6.1 application that exercises
[django-trusts](https://github.com/django-trusts/django-trusts) **1.0.0.dev0**
at revision
[`b5d5ae18e1fbe4901d0350a82a2aab1dcac92a20`](https://github.com/django-trusts/django-trusts/commit/b5d5ae18e1fbe4901d0350a82a2aab1dcac92a20)
(PR [#24](https://github.com/django-trusts/django-trusts/pull/24) merge:
fail-closed per-Trust group permission intersection).

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
| `alice` | Owner of private notes, a shared roadmap, a public changelog, the Acme handbook, and the Acme playbook |
| `bob` | Trustee with **read** on Shared Roadmap |
| `carol` | `acme-staff` member; **read** on Acme Handbook and **change** on Acme Playbook (same team, different local rights) |
| `dave` | Outsider plus his own notes; reads Alice's work only when it is public |

`acme-staff` has the **editor** role as its global ceiling (read + change).
Local TrustGroup grants choose the subset per project. Associating the team
without local rights grants nothing.

## Demo workflows

1. **Create an object** — as alice (or bob), *New project*. The creator gets
   read and change trustee rows on a new trust.
2. **Change visibility** — on a project you can change, toggle public. Public
   associates `public-readers` and enables **local read**. Association alone
   does not grant access. Every signed-in account is enrolled in that group
   (seeded users and accounts created later). Log in as dave — or create
   another user — to see the list change.
3. **Grant / revoke trustees** — grant bob or dave read (or read+change), then revoke.
4. **Teams** — on a project you can change, associate `acme-staff` without
   granting access (the row shows “grants nothing”). Enable local **Read**
   and/or **Change** only if those codes are in the team's global ceiling.
   Saving a permission outside the ceiling is rejected and does not mutate.
   Log in as carol to confirm Handbook vs Playbook.
5. **Another user's view** — log out and in as bob, carol, or dave. The home
   list is already filtered.
6. **Unauthorized edits** — as bob, open Alice Private Notes (403) or edit
   Shared Roadmap (403: bob has read only). As carol, edit Acme Handbook
   (403: local read only) but edit Acme Playbook (allowed).

List pages paginate *after* the Trusts SQL filter (`PROJECT_PAGE_SIZE`,
default 3) from `Project.objects.permitted`. Direct URLs use the same
`has_perm` decision as list membership.

## Checks

```bash
python manage.py test projects
```

CI runs that suite on Python 3.12–3.14 with Django 6.1 (SQLite), plus
`migrate` / `seed_demo`, collectstatic + a WhiteNoise fetch of
`/static/admin/css/base.css`. A separate job runs `migrate`, `seed_demo`,
and a Trusts list-filter query against **MySQL 8**.

## Dokku

Deploy glue for Dokku with linked MySQL 8 (`DATABASE_URL` from dokku-mysql).
Django 6.1 requires **MySQL 8.4+**. Local `runserver` still uses SQLite when
`DATABASE_URL` is unset.

**Do not push this TrustGroup revision to Dokku until the example PR is
reviewed.** After review, migrate then re-run `seed_demo` once so local
TrustGroup rows exist (`seed_demo` is idempotent). Do not run
`grandfather_trust_group_permissions` for this demo.

```bash
git remote add dokku dokku@your-host:your-app
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
dokku run your-app python manage.py seed_demo
```

Dokku HTTPS login POSTs need `CSRF_TRUSTED_ORIGINS` (Django 4+). Set it to
your public origin after TLS is enabled:

```bash
dokku config:set your-app CSRF_TRUSTED_ORIGINS=https://your-app.example.com
```

Comma-separated extra origins are allowed. Unset, the list is empty (fine
for local HTTP `runserver`).

Optional config:

| Var | Default |
| --- | --- |
| `SECRET_KEY` | Hard-coded demo key |
| `CSRF_TRUSTED_ORIGINS` | empty; set via `dokku config:set` for HTTPS |

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

Example behavior changes (including the TrustGroup pin bump) are recorded
in [migrates.md](migrates.md). Core library behavior for #23 is in
django-trusts `migrates.md` on the pinned revision.
