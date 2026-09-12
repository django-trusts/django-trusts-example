# django-trusts-example

A runnable Django application showing how persisted relationships become
object permissions with
[django-trusts-zero](https://github.com/django-trusts/django-trusts-zero).

The example keeps authorization in ordinary database rows. Direct grants,
team membership, role ceilings, and Trust-scoped permissions feed the same
decision used by object checks and filtered querysets. Lists are filtered in
SQL before pagination, and unauthorized object URLs fail closed.

## Run it

Requires Python 3.12 or newer and Django 6.1.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Open <http://127.0.0.1:8000/>. Every seeded account uses the password
`demo`.

| User | What the account demonstrates |
| --- | --- |
| `alice` | Ownership, private projects, direct grants, shared Trusts, and public visibility |
| `bob` | A direct read-only grant on Shared Roadmap |
| `carol` | Team-derived access: read on the shared Acme Trust and change on a separate Trust |
| `dave` | Isolation from Alice's private work, public access, and his own project |

Try the same object from different accounts. The project list and direct URL
use the same persisted authorization facts.

## What it demonstrates

### Direct object permissions

`Project` subclasses Zero's abstract `Content` model. A direct grant is an
ordinary `TrustUserPermission` row attached to the project's Trust:

```python
TrustUserPermission.objects.get_or_create(
    trust=project.trust,
    entity=user,
    permission=project_permission("read_project"),
)
```

Django's familiar object-permission API asks the question:

```python
user.has_perm("projects.read_project", project)
```

### Database-filtered listings

The list form of the same question stays a QuerySet:

```python
Project.objects.permitted("read_project", user)
```

The list view passes that QuerySet to `Paginator`; it never loads an
unfiltered page and checks each row in Python.

### Trust-scoped teams

`acme-staff` has an editor role as its global ceiling. Each Trust selects the
local subset that is active there. Acme Handbook and Acme Appendix share one
Trust and are readable by Carol. Acme Playbook uses another Trust where Carol
can also change the project. Merely associating a team grants nothing.

### View protection

Direct URLs use the core decorator and Django's object-permission backend:

```python
from trusts.decorators import K, permission_required

@permission_required("projects.change_project", pk=K("pk"))
def project_edit(request, pk):
    ...
```

## Configuration

The concrete Django app belongs to Zero. `django-trusts` is installed as its
schema-neutral engine and is not listed separately in `INSTALLED_APPS`.

```python
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "trusts.zero.apps.ZeroConfig",
    "projects.apps.ProjectsConfig",
]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "trusts.zero.backends.TrustModelBackend",
]
```

The host app contributes its protected model to Zero's configured registry:

```python
from trusts.zero.apps import CANONICAL_BACKEND_PATH, zero_config
from trusts.zero.registration import register_zero_content

handle = zero_config().configured_backend(CANONICAL_BACKEND_PATH)
register_zero_content(handle.registry, Project)
```

Development dependencies are pinned to a mutually tested core/Zero pair
until the corresponding releases are published.

## Verify it

```bash
python manage.py check
python manage.py test projects
python manage.py migrate --noinput
python manage.py seed_demo
```

CI covers Python 3.12–3.14 on SQLite and a MySQL 8.4 smoke run. It also
checks static-file collection and the seeded permission query.

Contributor history and deployment notes live in [DEV.md](DEV.md). Detailed
authorization boundaries are recorded in
[docs/TRUSTS_FIT.md](docs/TRUSTS_FIT.md), and behavior changes in
[migrates.md](migrates.md).

Licensed under the BSD 2-Clause License. Copyright BeeDesk, Inc.
