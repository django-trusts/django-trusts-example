"""Query-count assertions and inspected plans for representative shapes."""

from pathlib import Path

from django.db import connection
from django.test.utils import CaptureQueriesContext

from winfs.constants import R
from winfs.evaluate import access_check, authorized_pks, explain_access_sql
from winfs.fixtures import allow, file, folder, local_group
from winfs.inherit import set_dacl_protected

from .support import FixtureMixin, PostgresTestCase

PLAN_DIR = Path(__file__).resolve().parents[2] / "docs" / "winfs-plans"


class QueryPlanTests(FixtureMixin, PostgresTestCase):
    def _assert_one_statement(self, fn):
        with CaptureQueriesContext(connection) as captured:
            result = fn()
        self.assertEqual(
            len(captured.captured_queries),
            1,
            "expected one SQL statement, got %s:\n%s"
            % (
                len(captured.captured_queries),
                "\n---\n".join(q["sql"] for q in captured.captured_queries),
            ),
        )
        return result

    def _write_plan(self, name, sql):
        PLAN_DIR.mkdir(parents=True, exist_ok=True)
        (PLAN_DIR / name).write_text(sql + "\n", encoding="utf-8")
        self.assertIn("CTE", sql)
        self.assertNotIn("function win_access_check", sql.lower())

    def test_shallow_file_one_query(self):
        allow(self.notes, self.data["alice"], R)
        decision = self._assert_one_statement(
            lambda: access_check(self.alice, self.notes, R)
        )
        self.assertTrue(decision.allowed)
        plan = explain_access_sql(self.alice, R, candidate_ids=[self.notes.pk], limit=1)
        self._write_plan("shallow.txt", plan)

    def test_depth_8_one_query(self):
        admin = self.data["admin"]
        alice = self.data["alice"]
        volume = self.data["volume"]
        current = folder(volume, "p0", admin, parent=self.vol)
        allow(current, alice, R, oi=True, ci=True)
        for i in range(1, 8):
            current = folder(volume, "p%s" % i, admin, parent=current)
        leaf = file(volume, "deep.txt", alice, parent=current)
        decision = self._assert_one_statement(lambda: access_check(self.alice, leaf, R))
        self.assertTrue(decision.allowed)
        plan = explain_access_sql(self.alice, R, candidate_ids=[leaf.pk], limit=1)
        self._write_plan("depth-8.txt", plan)

    def test_thousand_siblings_two_groups_one_query(self):
        ops = local_group("ops", "S-1-5-21-1000-1-1-513", members=(self.data["alice"],))
        allow(self.proj, self.eng, R, oi=True)
        allow(self.proj, ops, R, oi=True)
        volume = self.data["volume"]
        admin = self.data["admin"]
        created = []
        for i in range(1000):
            created.append(
                file(volume, "sib-%04d.txt" % i, admin, parent=self.proj).pk
            )
        pks = self._assert_one_statement(
            lambda: authorized_pks(
                self.alice,
                R,
                parent_id=self.proj.pk,
                limit=25,
                offset=0,
            )
        )
        self.assertEqual(len(pks), 25)
        self.assertEqual(pks[0], self.readme.pk)
        listed = authorized_pks(self.alice, R, parent_id=self.proj.pk)
        self.assertEqual(len(listed), 1001)  # 1000 siblings + readme.txt; secret is IO
        self.assertIn(self.readme.pk, listed)
        self.assertNotIn(self.secret.pk, listed)
        plan = explain_access_sql(
            self.alice,
            R,
            parent_id=self.proj.pk,
            limit=25,
        )
        self._write_plan("siblings-1000.txt", plan)
        self.assertTrue(created)

    def test_protected_midtree_one_query(self):
        allow(self.proj, self.eng, R, oi=True, ci=True)
        set_dacl_protected(self.secret, preserve=False)
        decision = self._assert_one_statement(
            lambda: access_check(self.alice, self.notes, R)
        )
        self.assertFalse(decision.allowed)
        pks = self._assert_one_statement(
            lambda: authorized_pks(self.alice, R, parent_id=self.secret.pk)
        )
        self.assertEqual(pks, [])
        plan = explain_access_sql(
            self.alice,
            R,
            candidate_ids=[self.notes.pk],
            limit=1,
        )
        self._write_plan("protected-midtree.txt", plan)
