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

CI runs that suite on Python 3.12–3.14 with Django 6.1, plus `migrate` and
`seed_demo`.

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
