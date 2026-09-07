# Where Trusts fits in this example

This note is the issue #16 record of what Trusts does on its own and what
the example still has to do. It is not a claim that the declarative
authorization thesis is complete.

Example behavior changes are recorded in [migrates.md](../migrates.md).
django-trusts **#23 / PR #24** is the TrustGroup local/global
intersection. **#28** registers queryable V1 `Expr` conditions via
`condition_refs()`. **#29 / PR #30** validates those registrations
with Django system checks (`trusts.E001` / `trusts.E002`). This
example pins that master tip and exposes TrustGroup in project
settings. It does not register a Project permission condition.

Inspected for this revision:

| Tree | Commit | What it is |
| --- | --- | --- |
| `django-trusts-example` default `master` | pre-#5 | Demo against Trusts post-#19; group attach implied access. |
| Historical `DJANGO-TRUSTS-8-Edit-Perm-Pages` / PR #1 | `54e83b76fee2e6e950cec94366adec038ebc1260` | Incomplete Project / collaborator UI on Django 1.8 / Python 2. |
| `django-trusts` master (PR #30 merge) | `8916a760fbe849170e88e3969723b317d0360cd1` | Installable 1.0.0.dev0 used here (Expr + system checks). |

The historical branch is the useful ancestor for *domain shape* (a `Project`
`Content` subclass, settlor trusts, collaborators, groups). Core now ships
`Content.grant` / `Content.revoke`, `ContentQuerySet.permitted`, and
`Trust.objects.filter_by_user_content_perm`. Group-derived access requires
the TrustGroup intersection from #23.

## Trusts fits naturally

- `Project(Content)` plus `TrustModelBackend` so `user.has_perm('projects.read_project', project)` is object-level.
- Creating a dedicated `Trust` per project (settlor = creator) and writing `TrustUserPermission` rows for the owner (`Content.grant`).
- Grant / revoke trustees as insert / delete of `TrustUserPermission`.
- Organization membership as Django `Group` **associated** with a trust
  (`TrustGroup`), with the `editor` role as the **global ceiling** and
  per-project `TrustGroup.permissions` as the local subset. Role-derived
  capabilities are ceiling only; they are not a local assignment.
- Public read as `public-readers` associated with that project's trust
  **and** a local `read_project` grant. Same tables `has_perm` reads.
  Existing accounts are synced into the group at seed; create/edit forms
  and admin keep every user in that group (`post_save` + `m2m_changed` +
  `UserAdmin.save_related`). Association without the local grant grants
  nothing. `public-readers` is a system-maintained audience for every
  signed-in account.
- Team mutations via `trusts.authorization` (`associate_group_with_trust`,
  `set_trust_group_permissions`, `disassociate_group_from_trust`). Writes
  outside the ceiling raise `AuthorizationDenied` and do not mutate.
- View guards via `trusts.decorators.permission_required` and `K()`.
- Cross-organization isolation: Dave's notes are on Dave's trust; Alice's
  grants do not leak.
- Same team, different projects: `acme-staff` has `change` on Acme Playbook
  and `read` only on Acme Handbook.

## Application code that remains

- **List filter.** `projects.query.readable_projects` wraps
  `Project.objects.permitted` (core SQL: trustee **or** TrustGroup
  local/global intersection). Pagination wraps that QuerySet. Inactive and
  anonymous principals are empty, matching `User.has_perm`.
- **Grant / revoke / visibility / team helpers.** Thin writes to Trusts
  APIs. Visibility calls `grant_group_permission` for local public read.
- **Create flow.** Allocate a unique slug, then create trust + project +
  owner grants in one transaction. Trusts does not auto-grant the settlor.
- **Public-readers enrollment.** Application signals, admin `save_related`,
  and seed sync write the group membership Trusts already evaluates. Not a
  per-request predicate. See [migrates.md](../migrates.md).
- **UI and seed.** Forms, templates, `seed_demo`, demo passwords. Project
  settings distinguish association, local rights, and the global ceiling.

## Model limitations (not papered over)

- `Trust.trust` and `Trust.settlor` are readonly after create. A project
  cannot be moved to another organization trust. Visibility change attaches
  or detaches a group on the *existing* trust (and enables or drops local
  read).
- Grants are **trust-scoped**. Two projects on one trust share trustees and
  TrustGroup local rights. This demo gives most projects their own trust so
  visibility and collaborator lists stay per-object. The Acme Handbook
  shares the Acme trust with any future Acme content — that is the intended
  organization pattern and also the limitation. **Acme Appendix** is seeded on
  that same Trust so the UI can show Trust-scoped local rights. Acme Playbook
  has its own Trust so the same team can have different local rights.
- Django `User.has_perm` short-circuits for `is_superuser`. Superusers are
  not a Trusts proof. Seed users are ordinary users. The list helper does
  **not** special-case superusers; a superuser may see a narrower list than
  `has_perm` would allow. That mismatch is documented, not treated as
  Trusts validation.
- `:own` on `Trust` is a registered **V1 `Expr`** (`u == o.settlor` from
  `condition_refs()`), queryable on `Trust.objects.permitted`. This
  example does not register a Project condition and does not use `:own`
  for project list membership. Public / private is a group grant, not a
  condition code. Callable conditions stay off (`TRUSTS_ALLOW_LEGACY_PERMISSION_CALLBACKS`
  is unset; default False). `manage.py check` must stay clean of
  `trusts.E001` / `trusts.E002`.

Windows ACL work stays on django-trusts#17. Parent Trust inheritance
and explicit deny stay out of scope. Core V1 `Expr` SQL compilation is
available; this demo does not register a Project condition.
