"""One PostgreSQL statement: remaining-bits AccessCheck and authorized listing.

This module does not import Trusts grant models or call a Trustee
grant-path compiler. Token expansion is example-local SQL over
win_principal / win_sid_member.
"""

from dataclasses import dataclass

from django.db import connection

from trusts.context import Context, ContextNotRegistered

from .constants import (
    MAX_ACE_SCAN,
    MAX_PARENT_DEPTH,
    READ_CONTROL,
    WRITE_DAC,
    map_generic_mask,
)
from .models import WinNode, WinStream

# Required database capabilities (semantics are DB-neutral):
# recursive CTE, deterministic ACE sequencing, integer bit ops,
# fail-closed cycle/depth. PostgreSQL 14+ is the first reference
# implementation and the only dialect in this slice.


class WinfsBackendError(RuntimeError):
    """The reference evaluator is not available on this database."""


ERR_CYCLE = "cycle"
ERR_OVERFLOW = "overflow"
ERR_DANGLING = "dangling_parent"
ERR_OWNER_RIGHTS = "owner_rights"
ERR_MISSING_SD = "missing_descriptor"
ERR_MISSING_PRINCIPAL = "missing_principal"
ERR_CONTEXT = "context_not_registered"
ERR_ACE_OVERFLOW = "ace_overflow"
ERR_MISSING_NODE = "missing_node"
ERR_INACTIVE = "inactive_or_anonymous"


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    error: str | None = None
    remaining: int = 0
    node_id: int | None = None

    @property
    def denied_with_error(self):
        return (not self.allowed) and self.error is not None


def _require_postgres():
    if connection.vendor != "postgresql":
        raise WinfsBackendError(
            "The AccessCheck evaluator requires PostgreSQL 14+ "
            "(recursive CTE, deterministic ACE sequencing, integer bit "
            "operations, fail-closed cycle/depth). Other dialects are "
            "out of this slice."
        )


def _usable_user(user):
    if user is None:
        return False
    if getattr(user, "is_anonymous", False):
        return False
    if not getattr(user, "is_authenticated", True):
        return False
    if getattr(user, "is_active", True) is False:
        return False
    if getattr(user, "pk", None) is None:
        return False
    return True


def _context_error(resource):
    model = resource.__class__
    try:
        Context.ensure_frozen()
        Context.get(model)
    except ContextNotRegistered:
        return ERR_CONTEXT
    if model is WinNode or model is WinStream:
        return None
    return ERR_CONTEXT


def _resolve_node(resource):
    if isinstance(resource, WinStream):
        return resource.node
    return resource


_CTE = """
WITH RECURSIVE
requester AS (
  SELECT p.sid_id
  FROM win_principal p
  WHERE p.user_id = %(auth_user_id)s
),
token(sid_id) AS (
  SELECT sid_id FROM requester
  UNION
  SELECT m.group_sid_id
  FROM requester r
  JOIN win_sid_member m ON m.member_sid_id = r.sid_id
),
candidates AS (
  SELECT n.id, n.parent_id, n.kind, n.name, n.volume_id,
         n.security_descriptor_id
  FROM win_node n
  WHERE %(use_ids)s = 0 OR n.id = ANY(%(candidate_ids)s)
    AND (%(parent_id)s IS NULL OR n.parent_id = %(parent_id)s)
),
anc AS (
  SELECT c.id AS target_id, c.id AS at_id, c.parent_id, c.kind,
         c.security_descriptor_id AS sd_id,
         0 AS dist, ARRAY[c.id] AS path, false AS saw_cycle
  FROM candidates c
  UNION ALL
  SELECT a.target_id, p.id, p.parent_id, p.kind, p.security_descriptor_id,
         a.dist + 1, a.path || p.id,
         a.saw_cycle OR p.id = ANY (a.path)
  FROM anc a
  JOIN win_node p ON p.id = a.parent_id
  LEFT JOIN win_security_descriptor cur ON cur.id = a.sd_id
  WHERE a.dist < %(max_parent_depth)s
    AND NOT a.saw_cycle
    AND COALESCE(cur.se_dacl_protected, false) = false
),
incoming AS (
  SELECT a.target_id, a.dist, a.sd_id, ace.id AS ace_id, ace.ace_order,
         ace.ace_type, ace.trustee_sid_id, ace.access_mask,
         ace.flag_oi, ace.flag_ci, ace.flag_np, ace.flag_io,
         s.sid_string
  FROM anc a
  JOIN win_ace ace ON ace.descriptor_id = a.sd_id
  JOIN win_sid s ON s.id = ace.trustee_sid_id
  JOIN win_node t ON t.id = a.target_id
  WHERE
    a.dist = 0
    OR (
      a.dist >= 1
      AND (NOT ace.flag_np OR a.dist = 1)
      AND (
        (t.kind = 'file' AND ace.flag_oi)
        OR (t.kind = 'folder' AND (ace.flag_oi OR ace.flag_ci))
      )
    )
),
gates AS (
  SELECT c.id AS target_id,
         COALESCE((
           SELECT BOOL_OR(a.saw_cycle) FROM anc a WHERE a.target_id = c.id
         ), false) AS saw_cycle,
         COALESCE((
           SELECT BOOL_OR(a.dist = %(max_parent_depth)s
                          AND a.parent_id IS NOT NULL)
           FROM anc a WHERE a.target_id = c.id
         ), false) AS overflow,
         COALESCE((
           SELECT BOOL_OR(
             a.parent_id IS NOT NULL
             AND a.dist < %(max_parent_depth)s
             AND NOT a.saw_cycle
             AND NOT EXISTS (
               SELECT 1 FROM win_security_descriptor sd
               WHERE sd.id = a.sd_id AND sd.se_dacl_protected
             )
             AND NOT EXISTS (
               SELECT 1 FROM win_node p WHERE p.id = a.parent_id
             )
           )
           FROM anc a WHERE a.target_id = c.id
         ), false) AS dangling,
         COALESCE((
           SELECT BOOL_OR(i.sid_string = 'S-1-3-4')
           FROM incoming i WHERE i.target_id = c.id
         ), false) AS owner_rights,
         COALESCE((
           SELECT COUNT(*) FROM incoming i WHERE i.target_id = c.id
         ), 0) AS incoming_ace_count
  FROM candidates c
),
effective AS (
  SELECT i.target_id,
         ROW_NUMBER() OVER (
           PARTITION BY i.target_id ORDER BY i.dist, i.ace_order
         ) AS seq,
         i.ace_type,
         CASE
           WHEN i.sid_string = 'S-1-3-0' THEN tsd.owner_sid_id
           ELSE i.trustee_sid_id
         END AS match_sid,
         i.access_mask
  FROM incoming i
  JOIN win_node t ON t.id = i.target_id
  LEFT JOIN win_security_descriptor tsd ON tsd.id = t.security_descriptor_id
  WHERE
    (i.dist = 0 AND i.flag_io = false)
    OR (
      i.dist >= 1
      AND NOT (
        t.kind = 'folder'
        AND i.flag_oi
        AND NOT i.flag_ci
        AND NOT (i.flag_np AND i.dist = 1)
      )
    )
),
seed AS (
  SELECT c.id AS target_id,
         EXISTS (SELECT 1 FROM requester) AS has_requester,
         (c.security_descriptor_id IS NOT NULL
          AND EXISTS (
            SELECT 1 FROM win_security_descriptor sd
            WHERE sd.id = c.security_descriptor_id
          )) AS sd_present,
         CASE
           WHEN NOT EXISTS (SELECT 1 FROM requester) THEN %(desired_mask)s::bigint
           WHEN g.owner_rights THEN %(desired_mask)s::bigint
           WHEN EXISTS (
             SELECT 1 FROM win_security_descriptor sd
             WHERE sd.id = c.security_descriptor_id
               AND sd.owner_sid_id IN (SELECT sid_id FROM token)
           )
             THEN %(desired_mask)s::bigint & ~(%(rc)s | %(wd)s)::bigint
           ELSE %(desired_mask)s::bigint
         END AS remaining
  FROM candidates c
  JOIN gates g ON g.target_id = c.id
),
scan AS (
  SELECT s.target_id, 0::bigint AS seq, s.remaining::bigint, false AS denied
  FROM seed s
  UNION ALL
  SELECT sc.target_id, e.seq,
         CASE
           WHEN e.match_sid IN (SELECT sid_id FROM token)
                AND e.ace_type = 'allow'
             THEN sc.remaining & ~e.access_mask
           ELSE sc.remaining
         END,
         sc.denied OR (
           e.match_sid IN (SELECT sid_id FROM token)
           AND e.ace_type = 'deny'
           AND (sc.remaining & e.access_mask) <> 0
         )
  FROM scan sc
  JOIN effective e ON e.target_id = sc.target_id AND e.seq = sc.seq + 1
  WHERE NOT sc.denied AND sc.remaining <> 0
)
"""

_SELECT_DECISIONS = """
SELECT c.id,
       c.name,
       s.has_requester,
       s.sd_present,
       g.saw_cycle,
       g.overflow,
       g.dangling,
       g.owner_rights,
       g.incoming_ace_count,
       last.remaining,
       last.denied,
       (
         s.has_requester
         AND s.sd_present
         AND NOT g.saw_cycle
         AND NOT g.overflow
         AND NOT g.dangling
         AND NOT g.owner_rights
         AND g.incoming_ace_count <= %(max_ace_scan)s
         AND NOT last.denied
         AND last.remaining = 0
       ) AS allowed
FROM candidates c
JOIN seed s ON s.target_id = c.id
JOIN gates g ON g.target_id = c.id
JOIN LATERAL (
  SELECT sc.remaining, sc.denied
  FROM scan sc
  WHERE sc.target_id = c.id
  ORDER BY sc.seq DESC
  LIMIT 1
) last ON true
"""

_ALLOWED_PREDICATE = """
  s.has_requester
  AND s.sd_present
  AND NOT g.saw_cycle
  AND NOT g.overflow
  AND NOT g.dangling
  AND NOT g.owner_rights
  AND g.incoming_ace_count <= %(max_ace_scan)s
  AND NOT last.denied
  AND last.remaining = 0
"""

_ORDER_LIMIT = (
    "WHERE (\n"
    + _ALLOWED_PREDICATE
    + "\n)\nORDER BY c.name, c.id\nLIMIT %(lim)s OFFSET %(off)s\n"
)

_SELECT_NODES = f"""
SELECT c.id, c.parent_id, c.kind, c.name, c.volume_id, c.security_descriptor_id
FROM candidates c
JOIN seed s ON s.target_id = c.id
JOIN gates g ON g.target_id = c.id
JOIN LATERAL (
  SELECT sc.remaining, sc.denied
  FROM scan sc
  WHERE sc.target_id = c.id
  ORDER BY sc.seq DESC
  LIMIT 1
) last ON true
WHERE (
{_ALLOWED_PREDICATE}
)
ORDER BY c.name, c.id
LIMIT %(lim)s OFFSET %(off)s
"""


def _params(auth_user_id, desired_mask, candidate_ids, parent_id, max_ace_scan):
    ids = list(candidate_ids) if candidate_ids is not None else [0]
    return {
        "auth_user_id": auth_user_id,
        "desired_mask": int(desired_mask),
        "candidate_ids": ids,
        "use_ids": 0 if candidate_ids is None else 1,
        "parent_id": parent_id,
        "max_parent_depth": MAX_PARENT_DEPTH,
        "max_ace_scan": int(max_ace_scan),
        "rc": READ_CONTROL,
        "wd": WRITE_DAC,
    }


def _error_from_row(row):
    if not row["has_requester"]:
        return ERR_MISSING_PRINCIPAL
    if row["saw_cycle"]:
        return ERR_CYCLE
    if row["overflow"]:
        return ERR_OVERFLOW
    if row["dangling"]:
        return ERR_DANGLING
    if row["owner_rights"]:
        return ERR_OWNER_RIGHTS
    if not row["sd_present"]:
        return ERR_MISSING_SD
    if row["incoming_ace_count"] > row.get("max_ace_scan_cmp", MAX_ACE_SCAN):
        return ERR_ACE_OVERFLOW
    return None


def _fetch(sql, params):
    _require_postgres()
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, values)) for values in cursor.fetchall()]


def access_check(user, resource, desired_mask, *, max_ace_scan=MAX_ACE_SCAN):
    """One-object remaining-bits AccessCheck. One SQL statement."""
    ctx_err = _context_error(resource)
    if ctx_err:
        return AccessDecision(False, error=ctx_err)
    if not _usable_user(user):
        return AccessDecision(False, error=ERR_INACTIVE)
    node = _resolve_node(resource)
    if not isinstance(node, WinNode):
        return AccessDecision(False, error=ERR_CONTEXT)
    mapped = map_generic_mask(desired_mask)
    params = _params(user.pk, mapped, [node.pk], None, max_ace_scan)
    rows = _fetch(_CTE + _SELECT_DECISIONS, params)
    if not rows:
        return AccessDecision(False, error=ERR_MISSING_NODE, node_id=node.pk)
    row = rows[0]
    row["max_ace_scan_cmp"] = max_ace_scan
    allowed = bool(row["allowed"])
    error = None if allowed else _error_from_row(row)
    return AccessDecision(
        allowed=allowed,
        error=error,
        remaining=int(row["remaining"]),
        node_id=row["id"],
    )


def authorized_pks(
    user,
    desired_mask,
    *,
    candidate_ids=None,
    parent_id=None,
    limit=None,
    offset=0,
    max_ace_scan=MAX_ACE_SCAN,
):
    """Authorized-object listing. Filter before ORDER BY / LIMIT. One statement."""
    if not _usable_user(user):
        return []
    try:
        Context.ensure_frozen()
        Context.get(WinNode)
    except ContextNotRegistered:
        return []
    mapped = map_generic_mask(desired_mask)
    params = _params(user.pk, mapped, candidate_ids, parent_id, max_ace_scan)
    params["lim"] = 2147483647 if limit is None else int(limit)
    params["off"] = int(offset)
    sql = _CTE + _SELECT_DECISIONS + _ORDER_LIMIT
    return [row["id"] for row in _fetch(sql, params)]


def authorized_nodes(
    user,
    desired_mask,
    *,
    candidate_ids=None,
    parent_id=None,
    limit=None,
    offset=0,
    max_ace_scan=MAX_ACE_SCAN,
):
    """Same one-statement filter as authorized_pks, returning WinNode rows."""
    if not _usable_user(user):
        return []
    try:
        Context.ensure_frozen()
        Context.get(WinNode)
    except ContextNotRegistered:
        return []
    mapped = map_generic_mask(desired_mask)
    params = _params(user.pk, mapped, candidate_ids, parent_id, max_ace_scan)
    params["lim"] = 2147483647 if limit is None else int(limit)
    params["off"] = int(offset)
    return list(WinNode.objects.raw(_CTE + _SELECT_NODES, params))


def explain_access_sql(
    user,
    desired_mask,
    *,
    candidate_ids=None,
    parent_id=None,
    limit=None,
    offset=0,
    max_ace_scan=MAX_ACE_SCAN,
    analyze=True,
):
    """EXPLAIN the same listing/decision statement used in production."""
    _require_postgres()
    mapped = map_generic_mask(desired_mask)
    params = _params(user.pk, mapped, candidate_ids, parent_id, max_ace_scan)
    params["lim"] = 2147483647 if limit is None else int(limit)
    params["off"] = int(offset)
    prefix = "EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) " if analyze else "EXPLAIN (FORMAT TEXT) "
    sql = prefix + _CTE + _SELECT_DECISIONS + _ORDER_LIMIT
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return "\n".join(row[0] for row in cursor.fetchall())
