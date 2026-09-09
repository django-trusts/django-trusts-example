# django-trusts-example

Runnable Django 6.1 application that exercises
[django-trusts](https://github.com/django-trusts/django-trusts) **1.0.0.dev0**
at revision
[`a2ab5a13752751ee761990bea778c9f868b2ad6e`](https://github.com/django-trusts/django-trusts/commit/a2ab5a13752751ee761990bea778c9f868b2ad6e)
(`trusts.context` / `trusts.trustee` after PRs [#41](https://github.com/django-trusts/django-trusts/pull/41)
and [#42](https://github.com/django-trusts/django-trusts/pull/42); includes
Expr conditions and TrustGroup intersection).

This is the implementation repository for [django-trusts#16](https://github.com/django-trusts/django-trusts/issues/16)
and the Windows ACL validation for [django-trusts#17](https://github.com/django-trusts/django-trusts/issues/17).
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
| `alice` | Owner of private notes, a shared roadmap, a public changelog, the Acme handbook and appendix (one Trust), and the Acme playbook |
| `bob` | Trustee with **read** on Shared Roadmap |
| `carol` | `acme-staff` member; **read** on Acme Handbook and Acme Appendix (shared `org:acme` Trust) and **change** on Acme Playbook (separate Trust) |
| `dave` | Outsider plus his own notes; reads Alice's work only when it is public |

`acme-staff` has the **editor** role as its global ceiling (read + change).
Local TrustGroup grants choose the subset **per Trust**. Associating the team
without local rights grants nothing. Handbook and Appendix share `org:acme`,
so a local change there applies to both. Playbook has its own Trust so the
same team can have different local rights.

## Demo workflows

1. **Create an object** — as alice (or bob), *New project*. The creator gets
   read and change trustee rows on a new trust.
2. **Change visibility** — on a project you can change, toggle public. Public
   associates `public-readers` and enables **local read** on that Trust
   (every project on the Trust). Association alone does not grant access;
   the page only shows **public** when that intersection is effective.
   Every signed-in account is enrolled in that group (seeded users and
   accounts created later). Log in as dave — or create another user — to
   see the list change.
3. **Grant / revoke trustees** — grant bob or dave read (or read+change), then revoke.
4. **Teams** — on a project you can change, associate `acme-staff` without
   granting access (the row shows “grants nothing”). Enable local **Read**
   and/or **Change** only if those codes are in the team's global ceiling.
   Those rights apply to **every project on this Trust**. Saving a
   permission outside the ceiling is rejected and does not mutate.
   Log in as carol: Handbook and Appendix share read; Playbook has change.
5. **Another user's view** — log out and in as bob, carol, or dave. The home
   list is already filtered.
6. **Unauthorized edits** — as bob, open Alice Private Notes (403) or edit
   Shared Roadmap (403: bob has read only). As carol, edit Acme Handbook
   or Acme Appendix (403: local read only) but edit Acme Playbook (allowed).

List pages paginate *after* the Trusts SQL filter (`PROJECT_PAGE_SIZE`,
default 3) from `Project.objects.permitted`. Direct URLs use the same
`has_perm` decision as list membership.

## Windows ACL example (`winfs`)

The `winfs` app is the bounded NTFS AccessCheck validation for
django-trusts#17 (`bounded-winfs-acl-r3`). It uses example-local SID /
descriptor / `WinNode.parent` tables and
`Context.register_direct(WinNode, scope_field='security_descriptor')`.
It does **not** use Trust, Trustee, Content, or Django Group.

The matrix and evaluator semantics are database-neutral. **PostgreSQL
14+** is the first reference implementation (recursive CTE, integer bit
ops, fail-closed cycle/depth). See [docs/WINFS_ACL.md](docs/WINFS_ACL.md).
Vectors remain documentation-derived until verified on a Windows host.

```bash
python -m pip install "psycopg[binary]>=3.2"
DATABASE_URL=postgres://USER:PASS@127.0.0.1:5432/DB \
  python manage.py migrate --settings=example.settings_winfs
DATABASE_URL=postgres://USER:PASS@127.0.0.1:5432/DB \
  python manage.py seed_winfs --settings=example.settings_winfs
DATABASE_URL=postgres://USER:PASS@127.0.0.1:5432/DB \
  python manage.py test winfs --settings=example.settings_winfs
```

After `seed_winfs`, open `/winfs/` while signed in (password `demo`).
SQLite `runserver` can still show the volume list; AccessCheck itself
returns unavailable unless the database is PostgreSQL.

## Checks

```bash
python manage.py check
python manage.py test projects
python manage.py test winfs.tests.test_schema
```

`manage.py check` must stay clean of `trusts.E001` / `trusts.E002`
(invalid `Expr` registrations or leftover callable conditions). This
example does not set `TRUSTS_ALLOW_LEGACY_PERMISSION_CALLBACKS`.

CI runs that suite on Python 3.12–3.14 with Django 6.1 (SQLite), plus
`check`, `migrate` / `seed_demo`, collectstatic + a WhiteNoise fetch of
`/static/admin/css/base.css`. A separate job runs `check`, `migrate`,
`seed_demo`, and a Trusts list-filter query against **MySQL 8**. The
`winfs` AccessCheck matrix and inspected plans run against **PostgreSQL
16**.

## Dokku

Deploy glue for Dokku with linked MySQL 8 (`DATABASE_URL` from dokku-mysql).
Django 6.1 requires **MySQL 8.4+**. Local `runserver` still uses SQLite when
`DATABASE_URL` is unset.

**Do not push this Trusts pin bump to Dokku until the example PR is
reviewed.** After merge, redeploy, migrate (no new Trusts schema beyond
the already-applied TrustGroup migration), then re-run `seed_demo` only
if the database is new or local TrustGroup rows are missing (`seed_demo`
is idempotent). Do not run `grandfather_trust_group_permissions` for
this demo.

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
`1.0.0.dev0`. Example package version is `0.3.0.dev0`.

## What was reused

The default branch was a starter only. The historical
`DJANGO-TRUSTS-8-Edit-Perm-Pages` branch (PR #1) supplied the Project /
collaborator idea. The app was rewritten for Django 6.1 and the modern
Trusts API. See [docs/TRUSTS_FIT.md](docs/TRUSTS_FIT.md).

Example behavior changes (including the Trusts pin bump through #28+#30)
are recorded in [migrates.md](migrates.md). Core library behavior for
#23 / #28 / #29 is in django-trusts `migrates.md` on the pinned revision.
