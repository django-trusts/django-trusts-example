# Migration record (django-trusts-example)

This record covers **example application** API and method behavior changes
while modernizing the demo for django-trusts `1.0.0.dev0`
(`5bd2a585d3806571f95bebf89c2852cac3649d25`).

**The django-trusts library API and method signatures are unchanged.** There
is no companion core PR and no update to django-trusts `migrates.md`.
Authorization decisions still go through `TrustModelBackend` / Trusts tables.

## No change to these Trusts call sites

- `User.has_perm` / `User.has_perms` via `trusts.backends.TrustModelBackend`
- `trusts.decorators.permission_required`, `P`, `K`
- `Trust.objects.get_or_create_settlor_default`, `get_root`, `filter_by_content`,
  `filter_by_user_perm`
- `Content` subclassing, `Meta.roles`, `create_trust_root`,
  `update_roles_permissions`
- `TrustUserPermission` and `Trust.groups` as the grant store

## Changes (example only)

### 1. `readable_projects` / `editable_projects` deny inactive users

| | |
| --- | --- |
| Previous | Helpers skipped anonymous users only. An inactive user with trustee or group rows still appeared in the list QuerySet while `User.has_perm` returned `False`. |
| New | `projects.query.projects_with_perm` returns `Project.objects.none()` when the principal is missing, anonymous, unauthenticated, or `is_active` is false. |
| Replacement | Same function names. Callers do not change. |
| Affected | `project_list` (`can_edit_ids` and the page QuerySet). Tests that compare list membership to `has_perm`. |
| Authorization | List and direct-object deny now agree for inactive users. Superuser short-circuit on `has_perm` is unchanged Django behavior and is not treated as Trusts validation. |

Migration-bot checklist:

- [ ] Find `readable_projects` / `editable_projects` / `projects_with_perm` uses.
- [ ] Do not add a Python `has_perm` loop to “fix” inactive users; keep the empty QuerySet.
- [ ] Re-run list-vs-direct agreement tests with an inactive seeded user.

### 2. Project create is atomic and slug collisions are resolved

| | |
| --- | --- |
| Previous | `project_create` saved a `Trust`, then a `Project` with `slugify(title)`. Duplicate or normalizing titles raised `IntegrityError` (HTTP 500) and left an orphan trust. |
| New | `projects.create.create_owned_project` allocates a free slug (`title-2`, …), then creates trust + project + owner `TrustUserPermission` rows in `transaction.atomic`. Empty slugs (`slugify(title) == ""`) are rejected on `ProjectForm.clean_title`. Residual `IntegrityError` becomes a form error and rolls back. |
| Replacement | Views call `create_owned_project` instead of inline `Trust.save` / `Project.save` / `grant_user`. |
| Affected | `project_create`, any script that copied the old create sequence. Trust titles stay `project:{slug}` (fits `Trust.title` max_length=40). |
| Authorization | Owner still receives `read_project` and `change_project` trustee rows. Failed creates grant nothing. |

Migration-bot checklist:

- [ ] Replace ad-hoc trust-then-project saves with `create_owned_project` (or equivalent atomic block).
- [ ] Stop assuming `slugify(title)` is unique.
- [ ] Verify a colliding POST does not increase `Trust` count without a `Project`.

### 3. `public-readers` is a system-maintained audience

| | |
| --- | --- |
| Previous | Seed enrolled only the four demo users. `create_user` after seed had no group row, so public projects were invisible. A later `post_save` hook enrolled new users, but ModelForm / admin `save_m2m()` runs after `post_save` and a `groups=[]` (or groups widget that omits the group) cleared the membership. |
| New | Every `auth.User` is kept in `public-readers` (which holds `read_project`). Enrollment: `post_save` on create; `m2m_changed` on `User.groups.through` after `post_remove` / `post_clear` (both directions); `UserAdmin.save_related`; `sync_public_readers()` at seed / backfill. The admin groups picker hides `public-readers`. Permission to see a public project is still `has_perm('projects.read_project', obj)` via that group attached to the project's trust. |
| Replacement | Do not test public read by checking a hard-coded demo-user list. Do not drop `public-readers` in application code expecting it to stay gone. |
| Affected | `seed_demo`, user create/edit forms, Django admin user and group M2M, `readable_projects` JOIN on `trust__groups`. |
| Authorization | Public visibility remains a Trusts group grant, not a Python predicate. Users created or edited without selecting the group still receive it. Removing a user from `public-readers` is restored. `seed_demo` is not required to repair routine user create/edit. |

Migration-bot checklist:

- [ ] Confirm `projects.signals` is imported from `ProjectsConfig.ready`.
- [ ] Confirm custom `UserAdmin` is registered (default `UserAdmin` unregistered).
- [ ] Create a user with `modelform_factory(..., fields=('username','groups'))` and `groups=[]`; assert `has_perm` on a public project.
- [ ] Repeat as a subsequent edit of that user with `groups=[]`.
- [ ] Create/edit via `UserAdmin.save_related` without selecting `public-readers`.
- [ ] Do not add an in-Python public-read bypass to list or detail views.

### 4. `CSRF_TRUSTED_ORIGINS` is env-only (no private hostname default)

| | |
| --- | --- |
| Previous | `example/settings.py` defaulted `CSRF_TRUSTED_ORIGINS` to `https://trustsexample1.cacheca.com,https://*.cacheca.com` when the env var was unset. HTTPS login and other unsafe POSTs on that host worked without operator config. |
| New | Parse `CSRF_TRUSTED_ORIGINS` from the environment when set; otherwise `[]`. The hostname is not a source default. |
| Replacement | Set the env var on each HTTPS deploy (`dokku config:set your-app CSRF_TRUSTED_ORIGINS=https://your-app.example.com`). Local HTTP `runserver` needs no origin list. |
| Affected | `example/settings.py`; Dokku/HTTPS deploys; Django login and other unsafe-method POSTs. |
| Authorization | Unchanged. Trusts `has_perm` / backends are not involved. This is CSRF origin checking only. |

The live demo must have `CSRF_TRUSTED_ORIGINS=https://trustsexample1.cacheca.com` configured **before** its next deployment of this revision. Do **not** restore that hostname as a source default.

Migration-bot checklist:

- [ ] Confirm `example/settings.py` has no hard-coded CSRF hostname default.
- [ ] Set and verify `CSRF_TRUSTED_ORIGINS` on the target HTTPS app (`dokku config:show` / equivalent) **before** deploying this revision.
- [ ] Live demo: `CSRF_TRUSTED_ORIGINS=https://trustsexample1.cacheca.com` must be set before the next deploy.
- [ ] After deploy, confirm an HTTPS login POST succeeds.
- [ ] Do not put the private hostname back into source defaults.

## Migration-bot summary

- [ ] Keep `AUTHENTICATION_BACKENDS` as `trusts.backends.TrustModelBackend`.
- [ ] Apply the four example checklists above.
- [ ] Set and verify `CSRF_TRUSTED_ORIGINS` before deploying this revision (live demo: `https://trustsexample1.cacheca.com`); then confirm an HTTPS login POST succeeds.
- [ ] `python manage.py test projects`
- [ ] `python manage.py migrate --noinput && python manage.py seed_demo`
- [ ] Do not edit django-trusts `migrates.md` for these example-only changes.
