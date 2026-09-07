# Where Trusts fits in this example

This note is the issue #16 record of what Trusts does on its own and what
the example still has to do. It is not a claim that the declarative
authorization thesis is complete.

**No django-trusts API or method change was required for this example.**
There is no companion core PR and no `migrates.md` update.

Inspected before this rewrite:

| Tree | Commit | What it is |
| --- | --- | --- |
| `django-trusts-example` default `master` | `0b22f2e4768a3c4ed02dd048627d0d596c7b7eb0` | 2016 Django 1.9 starter. No Trusts app, no models, no workflows. |
| Historical `DJANGO-TRUSTS-8-Edit-Perm-Pages` / PR #1 | `54e83b76fee2e6e950cec94366adec038ebc1260` | Incomplete Project / collaborator UI on Django 1.8 / Python 2. |
| `django-trusts` master (post #19) | `5bd2a585d3806571f95bebf89c2852cac3649d25` | Installable 1.0.0.dev0 used here. |

The historical branch is the useful ancestor for *domain shape* (a `Project`
`Content` subclass, settlor trusts, collaborators, groups). It is not a
complete Trusts demo: tests are thin, `print` debug remains, and it calls
`Content.grant` and `QuerySet.permitted` / `Trust.objects.filter_by_user_content_perm`.
Those helpers were sketched on an unmerged trusts checkout (`Moved filter and
grant method into trusts`) and **are not in modernized master**. This example
does not pretend they exist.

## Trusts fits naturally

- `Project(Content)` plus `TrustModelBackend` so `user.has_perm('projects.read_project', project)` is object-level.
- Creating a dedicated `Trust` per project (settlor = creator) and writing `TrustUserPermission` rows for the owner.
- Grant / revoke as insert / delete of `TrustUserPermission` (trustee path).
- Organization membership as Django `Group` attached to a trust, with the
  `reader` role materialized by `update_roles_permissions` (role path).
- Public read as the `public-readers` group attached to that project's trust
  (group-permission path). Same tables `has_perm` reads. Existing accounts
  are synced into the group at seed; new accounts are enrolled by a
  `post_save` signal. That is still a group row, not a Python allow-list.
- View guards via `trusts.decorators.permission_required` and `K()`.
- Cross-organization isolation: Dave's notes are on Dave's trust; Alice's
  grants do not leak.

## Application code that remains

- **List filter.** Trusts can answer `has_perm(user, perm, obj)` and
  `has_perm(user, perm, queryset)` (the queryset form is all-must-match, not
  a filter). There is no supported "objects this user may see" manager.
  `projects.query.readable_projects` is application SQL against Trusts
  tables. Pagination wraps that QuerySet. The helper also returns empty for
  inactive users so it matches `User.has_perm` (which denies `is_active=False`).
- **Grant / revoke / visibility helpers.** Thin writes to Trusts rows. Not
  core API.
- **Create flow.** Allocate a unique slug, then create trust + project +
  owner grants in one transaction. Trusts does not auto-grant the settlor.
- **Public-readers enrollment.** Application signal / seed sync writes the
  group membership Trusts already evaluates. Not a per-request predicate.
- **UI and seed.** Forms, templates, `seed_demo`, demo passwords.

## Model limitations (not papered over)

- `Trust.trust` and `Trust.settlor` are readonly after create. A project
  cannot be moved to another organization trust. Visibility change attaches
  or detaches a group on the *existing* trust.
- Grants are **trust-scoped**. Two projects on one trust share trustees and
  groups. This demo gives most projects their own trust so visibility and
  collaborator lists stay per-object. The Acme Handbook shares the Acme
  trust with any future Acme content — that is the intended organization
  pattern and also the limitation.
- Django `User.has_perm` short-circuits for `is_superuser`. Superusers are
  not a Trusts proof. Seed users are ordinary users. The list helper does
  **not** special-case superusers; a superuser may see a narrower list than
  `has_perm` would allow. That mismatch is documented, not treated as
  Trusts validation.
- `:own` on `Trust` is a registered **Python predicate**
  (`lambda u, p, o: u == o.settlor`). This example does not use `:own` for
  list membership or as evidence that permission declarations evaluate in a
  single query. Public / private is a group grant, not a condition code.

Windows ACL work stays on django-trusts#17.
