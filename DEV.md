# Development notes

`django-trusts-example` began as a small Django 1.8 example. The application
was rebuilt in 2026 as the Alice/Bob/Carol/Dave authorization demo, first
against the modernized pre-split core at `8916a76` and now against
`django-trusts-zero` plus the schema-neutral `django-trusts` engine.

The active development branch is `dev`. `master` remains the restored
pre-split baseline until a release decision is made.

## Local development

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py check
python manage.py test projects
```

The dependency SHAs in `requirements.txt` and `pyproject.toml` are a tested
core/Zero pair. Update them together and run both SQLite and MySQL CI before
merging.

## Demo data

```bash
python manage.py migrate --noinput
python manage.py seed_demo
```

`seed_demo` is idempotent. It is intentionally not a release-phase command;
run it once for a new demo database.

## Dokku

The repository includes a Gunicorn process, WhiteNoise static serving, and
`DATABASE_URL` support. Local development defaults to SQLite. A linked MySQL
deployment must use MySQL 8.4 or newer.

Set the public HTTPS origin before deployment:

```bash
dokku config:set your-app CSRF_TRUSTED_ORIGINS=https://your-app.example.com
git push dokku dev:master
dokku run your-app python manage.py seed_demo
```

Do not put a private deployment hostname in source. Do not run `seed_demo`
on every release.

## Project history

- Historical branch `DJANGO-TRUSTS-8-Edit-Perm-Pages` supplied the original
  Project/collaborator idea.
- Commit `2ee36f9` is the restored example baseline paired with core
  `8916a76`; the repository was not converted during the abandoned first
  split attempt.
- [Issue #10](https://github.com/django-trusts/django-trusts-example/issues/10)
  moves the runnable demo to Zero while retaining its authorization behavior.

Behavioral migration details are kept in [migrates.md](migrates.md).
