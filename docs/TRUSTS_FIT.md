# Where Trusts fits in this example

This application uses two packages with distinct responsibilities:

- `django-trusts` supplies the schema-neutral registry, query compiler,
  backend mixin, decorators, and authorization QuerySet surface.
- `django-trusts-zero` supplies the concrete historical Trust, Content,
  trustee, team, role, and migration schema used by this demo.

The application owns its project model, persisted writes, workflows, and UI.
`ProjectsConfig.ready()` explicitly contributes `Project` to Zero's configured
registry; importing the abstract `Content` mixin does not perform registration.

## Authorization path

`Project` subclasses Zero's abstract `Content`, which gives each project a
foreign key to `Trust`. Zero registers the ordinary relations connecting:

- a user to `TrustUserPermission` and the Trust protecting the project;
- a user through team membership to a local `TrustGroupPermission`;
- that local team permission to the team's direct or role-derived global
  ceiling.

Core compiles those registered paths into SQL. Complete alternatives combine
with OR; the facts within one path combine with AND. A team association by
itself is not a grant.

## One decision, several call sites

The demo checks one object with Django's public API:

```python
user.has_perm("projects.read_project", project)
```

It asks the list form through Zero's Django-permission codec:

```python
Project.objects.permitted("read_project", user)
```

Views use `trusts.decorators.permission_required`. All three routes reach the
same registered relation plan and persisted policy facts. Pagination is
applied after the authorized QuerySet is constructed.

## Application-owned writes

The example intentionally writes normal model relationships rather than
depending on `Content.grant()` or `Trust.grant_group_permission()` convenience
methods:

- direct grants create or delete `TrustUserPermission` rows;
- local team grants create or delete `TrustGroupPermission` rows;
- team association uses the `TrustGroup` through row;
- global ceilings remain Django Group permissions and Zero Role permissions.

Zero's authorization helpers protect user-driven team mutations. Seed and
system-maintained public visibility write the same persisted rows directly.

## Scope demonstrated

- private and public projects;
- direct read/change grants and revocation;
- one Trust protecting several projects;
- the same team receiving different local rights on different Trusts;
- global role ceilings constraining local team grants;
- list/direct agreement, inactive-user denial, and authorization before
  pagination;
- failed unauthorized edits without mutation.

This is a focused Zero example, not a complete ACL implementation. Ordered
ACE evaluation and recursive inheritance are demonstrated separately by
`django-trusts-windows-acl`; organization-derived permissions are demonstrated
by `django-trusts-gh-permissions`.
