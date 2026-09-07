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
| Previous | `example/settings.py` defaulted `CSRF_TRUSTED_ORIGINS` to a private Dokku hostname when the env var was unset. HTTPS login and other unsafe POSTs on that host worked without operator config. |
| New | Parse `CSRF_TRUSTED_ORIGINS` from the environment when set; otherwise `[]`. Private hostnames are not a source default. |
| Replacement | Set the env var on each HTTPS deploy (`dokku config:set your-app CSRF_TRUSTED_ORIGINS=https://your-app.example.com`). Local HTTP `runserver` needs no origin list. |
| Affected | `example/settings.py`; Dokku/HTTPS deploys; Django login and other unsafe-method POSTs. |
| Authorization | Unchanged. Trusts `has_perm` / backends are not involved. This is CSRF origin checking only. |

Existing HTTPS deployments that relied on the old default must set `CSRF_TRUSTED_ORIGINS` to their public origin **before** deploying this revision. Do **not** put private hostnames in source defaults.

Migration-bot checklist:

- [ ] Confirm `example/settings.py` has no hard-coded CSRF hostname default.
- [ ] Set and verify `CSRF_TRUSTED_ORIGINS` via `dokku config` (or equivalent) **before** deploying this revision.
- [ ] After deploy, confirm an HTTPS login POST succeeds.
- [ ] Do not put private hostnames in source defaults.

## Migration-bot summary

- [ ] Keep `AUTHENTICATION_BACKENDS` as `trusts.backends.TrustModelBackend`.
- [ ] Apply the four example checklists above.
- [ ] Set and verify `CSRF_TRUSTED_ORIGINS` via `dokku config` (or equivalent) before deploying this revision; then confirm an HTTPS login POST succeeds. Do not put private hostnames in source defaults.
- [ ] `python manage.py test projects`
- [ ] `python manage.py migrate --noinput && python manage.py seed_demo`
- [ ] Do not edit django-trusts `migrates.md` for these example-only changes.

# Per-Trust group rights in project settings (issue #5)

This record covers the example app after django-trusts **#23 / PR #24**
(`b5d5ae18e1fbe4901d0350a82a2aab1dcac92a20`). Core `migrates.md` on that
revision is the library contract. This file records **example** old/new
behavior only.

Authorization still goes through `TrustModelBackend` / Trusts tables. Group
access is now the fail-closed intersection:

```
effective = member ∧ TrustGroup(trust, group) ∧ local TrustGroup.permissions
            ∧ global Group.permissions (roles are ceiling only)
```

## Pin

| | |
| --- | --- |
| Previous | `django-trusts` at `5bd2a585d3806571f95bebf89c2852cac3649d25` (post-#19). |
| New | `django-trusts` at `b5d5ae18e1fbe4901d0350a82a2aab1dcac92a20` (PR #24 merge on master). |
| Replacement | Same git URL, new SHA in `requirements.txt` / `pyproject.toml`. |
| Affected | `migrate` applies `trusts.0002_trustgroup`. Existing `Trust.groups` rows become `TrustGroup` associations with **empty** local grants. |
| Authorization | Association without local tuples grants nothing until `seed_demo` (or an operator) writes `TrustGroupPermission` rows. Do **not** run `grandfather_trust_group_permissions` unless you deliberately want former implicit group access. |

## Changes (example)

### 5. List filter uses core `permitted()` (TrustGroup intersection)

| | |
| --- | --- |
| Previous | `projects.query.projects_with_perm` JOINed `trust__groups__permissions` and `trust__groups__roles__permissions`. That treated the global ceiling (and role) as a Trust grant. |
| New | `Project.objects.permitted(codename, user)` via `trusts.query.trust_grant_q`. Group-derived rows require the local/global intersection on the same TrustGroup. Inactive/anonymous still yield an empty QuerySet. Pagination still wraps that QuerySet. |
| Replacement | Same helper names: `readable_projects` / `editable_projects`. |
| Affected | Project list, `can_edit_ids`, MySQL smoke titles. |
| Authorization | List membership and `has_perm` / direct 403 agree on the supported relational paths, including fail-closed partial group setup. |

Migration-bot checklist:

- [ ] Do not restore a Python `has_perm` loop or a JOIN that omits `TrustGroup.permissions`.
- [ ] Paginate `readable_projects(user)`, never `Project.objects.all()`.
- [ ] Re-run list-vs-direct tests after the Trusts pin bump.

### 6. Public visibility associates **and** enables local read

| | |
| --- | --- |
| Previous | `set_public` called `trust.groups.add(public-readers)`. With implicit group grants that was enough. |
| New | `trust.grant_group_permission(public-readers, read_project)` (associates + local read). Detach still `groups.remove`. `Group.permissions` on public-readers remains the global ceiling (`read_project` only). |
| Replacement | Same `set_public` / visibility form. Help text states association alone does not grant access. `is_public()` is the effective intersection (association + local read + ceiling), not association-only. |
| Affected | Public Changelog seed, visibility POST, users created after seed. |
| Authorization | A public-readers association with an empty local set grants nothing **and** `is_public()` is false (the page shows private, not public + “grants nothing”). Seed and the visibility form always write the local read tuple when making public. |

Migration-bot checklist:

- [ ] After migrate, confirm public projects have a `TrustGroupPermission` for `read_project`.
- [ ] Do not treat `trust.groups.add(public-readers)` as a grant.
- [ ] Do not treat association-only as `is_public()` / a public badge.

### 7. Project settings distinguish association, local rights, and ceiling

| | |
| --- | --- |
| Previous | No team UI. Organization access was `Trust.groups.add(acme-staff)` plus the `reader` role (implicit grant). |
| New | Settings show (1) associated teams, (2) local TrustGroup checkboxes limited to grantable permissions **inside the group's global ceiling**, (3) the ceiling (and contributing roles) as read-only. Copy states that local rights belong to **this project's Trust** and apply to every project on it. Associate POSTs `associate_group_with_trust` with no permissions. Local POSTs `set_trust_group_permissions`. Unknown / cross-project IDs and permissions outside the ceiling raise `AuthorizationDenied` and **do not mutate**. Public-readers stays on the visibility form. |
| Replacement | New routes: `project-associate-team`, `project-disassociate-team`, `project-team-permissions`. |
| Affected | Project detail template; change-gated POSTs. Read-only users see the table and get 403 on mutate URLs. |
| Authorization | Partial setup (associated, no local rights) displays “grants nothing” and `has_perm` is false. Removing a ceiling permission revokes it on every Trust that still has a local tuple, even if it remains selected locally. Removing a local permission affects that **Trust** (every project using it), not other Trusts. |

Migration-bot checklist:

- [ ] Gate team POSTs on `projects.change_project` (decorator **and** the authorization helpers).
- [ ] Catch `AuthorizationDenied`; do not write TrustGroup rows after a rejected submit.
- [ ] Only render ceiling-subset checkboxes; still reject extra submitted codes/PKs server-side.
- [ ] Do not call `refuse_group_permission_write` / write `Group.permissions` from project forms.

### 8. Seed: explicit local grants; same team, different projects

| | |
| --- | --- |
| Previous | `acme-staff` + `reader` role on `org:acme`. Carol read Acme Handbook implicitly. Four Alice-owned demo projects. |
| New | `acme-staff` uses the **editor** role as the global ceiling (read + change). Acme Handbook and **Acme Appendix** share `org:acme` with local **read** only (Trust-scoped). New **Acme Playbook** (own Trust) gets local **read and change**. `seed_demo` writes those `TrustGroupPermission` rows; it does not run `grandfather_trust_group_permissions`. |
| Replacement | Same command: `python manage.py seed_demo`. Idempotent. |
| Affected | Carol's list (Appendix + Handbook + Playbook + public Changelog). Alice's list includes Appendix and Playbook. README demo table. |
| Authorization | Existing seeded users keep their intended access after the pin bump **because seed writes local tuples**. A migrate without re-seed would leave public-readers / acme-staff associated and grant nothing. Local rights on `org:acme` apply to Handbook and Appendix together. |

Migration-bot checklist:

- [ ] `migrate` then `seed_demo` (not grandfather) for this demo.
- [ ] Confirm carol: `change` on Playbook, `read` only on Handbook **and** Appendix (shared Trust).
- [ ] Confirm dave still reads Public Changelog and not private notes.

## Deployment / migration checklist (example)

Do **not** Dokku-deploy this revision until the example PR is reviewed.

- [ ] Install Trusts at `b5d5ae18e1fbe4901d0350a82a2aab1dcac92a20`.
- [ ] `python manage.py migrate --noinput` (applies `trusts.0002_trustgroup`).
- [ ] Expect existing group associations to grant **nothing** until local tuples exist.
- [ ] Do **not** run `grandfather_trust_group_permissions` for this demo.
- [ ] `python manage.py seed_demo` so public-readers and acme-staff get explicit local grants.
- [ ] `python manage.py test projects`
- [ ] Keep `AUTHENTICATION_BACKENDS` as `trusts.backends.TrustModelBackend`.
- [ ] Set `CSRF_TRUSTED_ORIGINS` on HTTPS deploys (unchanged; still no private hostname defaults).
- [ ] When an operator later deploys: migrate, seed once if the database is new; on an already-seeded Dokku app, re-run `seed_demo` so local TrustGroup rows exist (the command is idempotent). Do not put `seed_demo` on every release.

# Pin django-trusts through #28 Expr + #29 system checks

This record covers the example app after django-trusts **#28 / PR #28**
(queryable V1 `Expr` conditions) and **#29 / PR #30** (Django system
checks). The pin is master HEAD
`8916a760fbe849170e88e3969723b317d0360cd1`. Core `migrates.md` on that
revision is the library contract. This file records **example** old/new
behavior only.

Authorization still goes through `TrustModelBackend` / Trusts tables.
Group access remains the fail-closed TrustGroup intersection from #23.
No new Trusts schema migration is required beyond `trusts.0002_trustgroup`
(already applied on the previous pin).

## Pin

| | |
| --- | --- |
| Previous | `django-trusts` at `b5d5ae18e1fbe4901d0350a82a2aab1dcac92a20` (PR #24 merge; TrustGroup only). |
| New | `django-trusts` at `8916a760fbe849170e88e3969723b317d0360cd1` (PR #30 merge on master: #29 system checks, includes #28 `Expr` registration). |
| Replacement | Same git URL, new SHA in `requirements.txt` / `pyproject.toml`. |
| Affected | `manage.py check` now reports `trusts.E001` (invalid `Expr`) and `trusts.E002` (callable conditions unless the legacy flag is on). Trust `:own` is an `Expr` (`u == o.settlor`), not a lambda. |
| Authorization | Unchanged for this demo. Project list / visibility / teams stay trustee and TrustGroup rows. The example does not register a Project condition and does not set `TRUSTS_ALLOW_LEGACY_PERMISSION_CALLBACKS`. |

## Changes (example)

### 9. No Project condition registration; do not enable the callable escape hatch

| | |
| --- | --- |
| Previous | Trust `:own` was documented as a Python lambda. The example never registered a Project condition. Public read was (and is) a group grant. |
| New | Trust `:own` is a queryable `Expr` in core. Project still has no `permission_conditions`. Settings do **not** set `TRUSTS_ALLOW_LEGACY_PERMISSION_CALLBACKS` (default False). CI runs `python manage.py check` and fails on `trusts.E001` / `trusts.E002`. |
| Replacement | If a future Project condition is V1-shaped, register `u, p, o = condition_refs()` plus an `Expr` via `Meta.permission_conditions` or `Content.register_permission_condition`. Do not keep a lambda and flip the escape hatch. |
| Affected | Docs, CI `check` step, pin comments. Seed, TrustGroup UI, and list SQL are unchanged. |
| Authorization | Same grants as the TrustGroup pin. Callable leftover registrations would fail closed (`trusts.E002`) rather than run. |

Migration-bot checklist:

- [ ] Confirm `requirements.txt` / `pyproject.toml` pin the SHA, not `master`.
- [ ] Confirm `example/settings.py` does not set `TRUSTS_ALLOW_LEGACY_PERMISSION_CALLBACKS`.
- [ ] Confirm `Project` has no callable `permission_conditions`.
- [ ] `python manage.py check` with no `SILENCED_SYSTEM_CHECKS` for `trusts.E001` / `trusts.E002`.
- [ ] `python manage.py test projects`
- [ ] Re-run `seed_demo` only if the database is new or TrustGroup local rows are missing.

## Deployment / migration checklist (example)

Do **not** Dokku-deploy this revision until the example PR is reviewed.
After merge, a redeploy can follow (no new Trusts schema).

- [ ] Install Trusts at `8916a760fbe849170e88e3969723b317d0360cd1`.
- [ ] `python manage.py check` (must be clean of `trusts.E001` / `trusts.E002`).
- [ ] `python manage.py migrate --noinput` (no new Trusts migration expected).
- [ ] `python manage.py seed_demo` only if the database is new or local TrustGroup rows are missing.
- [ ] `python manage.py test projects`
- [ ] Keep `AUTHENTICATION_BACKENDS` as `trusts.backends.TrustModelBackend`.
- [ ] Do not set `TRUSTS_ALLOW_LEGACY_PERMISSION_CALLBACKS` for this demo.
- [ ] Set `CSRF_TRUSTED_ORIGINS` on HTTPS deploys (unchanged; still no private hostname defaults).

