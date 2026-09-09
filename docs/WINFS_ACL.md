# Bounded Windows filesystem ACL (django-trusts#17)

Revision **`bounded-winfs-acl-r3`** plus the approved depth erratum.
Implementation lives in this example repository. django-trusts core is
unchanged.

Vectors in `winfs.tests.test_matrix` are **documentation-derived** from
Microsoft AccessCheck / ACE inheritance / MS-DTYP sources cited on
[issue #17](https://github.com/django-trusts/django-trusts/issues/17).
They are not bit-identical NTFS dumps and are not verified against a
Windows host until a later comparison pass.

## What this proves

Trusts’ reusable **Context** contract can register a filesystem node to
an example-local security descriptor (`Context.register_direct(WinNode,
scope_field='security_descriptor')`). Authorization itself is a fixed
remaining-bits AccessCheck evaluator over ordinary tables. Trustee is
**not** used: at the cited core revision it is a grant-path `Exists`
compiler and cannot express stored-order allow/deny.

Owner authority is an independent relational contribution:

```text
owner_sid ∈ requester token  →  pre-grant READ_CONTROL | WRITE_DAC
```

It does not traverse `Trust` and is not an all-permissions shortcut.

## Schema (example-local)

`WinSid` is the relational identity. `WinPrincipal` and `WinLocalGroup`
are typed profiles. `WinSidMember.group` is a real FK to
`win_local_group` (a principal or well-known SID cannot appear on the
left). `WinSecurityDescriptor` holds `owner_sid` and
`SE_DACL_PROTECTED`. Ordered `WinAce` rows are the DACL.
`WinVolume` plus recursive `WinNode.parent` is the resource tree (one
root per volume). Optional `WinStream` shares the node’s descriptor via
`Context.register_related(WinStream, through='node')` — not the parent
folder.

No `Trust`, Trustee adapter, `Content`, `Junction`, `TrustGroup`,
`Role`, or Django `Group` is consulted by the evaluator.

## Depth (approved erratum)

```text
MAX_PARENT_DEPTH = 64 parent links
target dist = 0
valid root may appear at dist = 64
expand while current dist < 64
overflow iff dist = 64 AND parent_id IS NOT NULL
```

`anc` may emit distances `0..64` (65 nodes including the target). Tests
cover valid depths 63 and 64 and fail-closed depth 65.

ACE count is **not** capped at 64. The reference statement names
`MAX_ACE_SCAN = 4096` as a separate operational incoming-ACE limit and
tests it independently (65 ACEs still evaluate; an override of 2 fails
closed).

## Evaluation

One PostgreSQL statement implements both a single-object decision and
pre-pagination authorized listing (filter, then `ORDER BY` / `LIMIT`).
Algorithm: remaining-bits AccessCheck (MS-DTYP), **not** deny-wins.
Inheritance is computed at read time (OI / CI / NP / IO). `OWNER_RIGHTS`
(`S-1-3-4`) on the inheritance-transformed incoming ACE bag is
**DENY+error** and suppresses the owner pre-grant, including inherited
hits (V40 / V43). Token construction starts from `win_principal` for
the authenticated user (V38′). Cycles and depth overflow fail closed.

## Portability

Schema, matrix, and semantics are database-neutral. PostgreSQL 14+ is
the first reference implementation and the inspected-plan backend.

Required capabilities:

- recursive CTE
- deterministic ACE sequencing
- integer bit operations
- fail-closed cycle / depth handling

PostgreSQL arrays / `CYCLE` and `EXPLAIN` tooling are implementation
choices, not part of the durable model. This slice does not ship a
second SQL dialect.

## Setup

Existing project demo (SQLite or `DATABASE_URL`):

```bash
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
```

Windows ACL evaluator (PostgreSQL 14+):

```bash
python -m pip install -r requirements.txt "psycopg[binary]>=3.2"
DATABASE_URL=postgres://USER:PASS@127.0.0.1:5432/DB \
  python manage.py migrate --settings=example.settings_winfs
DATABASE_URL=postgres://USER:PASS@127.0.0.1:5432/DB \
  python manage.py seed_winfs --settings=example.settings_winfs
DATABASE_URL=postgres://USER:PASS@127.0.0.1:5432/DB \
  python manage.py test winfs --settings=example.settings_winfs
```

Browse `/winfs/` after logging in as a seeded user (password `demo`).
The browser uses authorized-object listing, not “LIST on the folder ⇒
show every child name”.

Inspected plans for shallow, depth-8, 1 000-sibling / two-group, and
protected-midtree cases are written under
[winfs-plans/](winfs-plans/) by the plan tests.
