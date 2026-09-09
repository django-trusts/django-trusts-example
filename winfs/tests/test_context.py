"""Honest Context registration; no Trustee / Trust grant path."""

import inspect

from trusts.context import Context, ContextNotRegistered
from trusts.trustee import Trustee

from winfs import evaluate
from winfs.evaluate import access_check
from winfs.fixtures import standard_tree
from winfs.models import WinNode, WinSecurityDescriptor, WinStream

from .support import PostgresTestCase


class ContextRegistrationTests(PostgresTestCase):
    def setUp(self):
        super().setUp()
        self.data = standard_tree()

    def test_direct_node_to_descriptor(self):
        Context.ensure_frozen()
        adapter = Context.get(WinNode)
        self.assertEqual(adapter.kind, Context.KIND_DIRECT)
        self.assertEqual(adapter.decl, "security_descriptor")
        self.assertIs(adapter.scope_model(), WinSecurityDescriptor)
        self.assertTrue(
            Context.resolves_to_scope(
                self.data["notes"],
                self.data["notes"].security_descriptor,
            )
        )

    def test_related_stream_shares_node_dacl_not_parent(self):
        stream = WinStream.objects.create(node=self.data["notes"], name="Zone.Identifier")
        Context.ensure_frozen()
        adapter = Context.get(WinStream)
        self.assertEqual(adapter.kind, Context.KIND_RELATED)
        self.assertEqual(adapter.decl, "node")
        self.assertTrue(
            Context.resolves_to_scope(stream, self.data["notes"].security_descriptor)
        )
        self.assertFalse(
            Context.resolves_to_scope(stream, self.data["secret"].security_descriptor)
        )
        child_via_parent = Context.filter_by_scope(
            WinNode.objects.all(),
            self.data["secret"].security_descriptor,
        )
        self.assertNotIn(self.data["notes"], list(child_via_parent))

    def test_evaluate_module_has_no_trust_or_trustee_grant_path(self):
        source = inspect.getsource(evaluate)
        self.assertNotIn("from trusts.models", source)
        self.assertNotIn("from trusts.trustee", source)
        self.assertNotIn("from trusts.trustee import", source)
        self.assertNotIn("django.contrib.auth.models", source)

    def test_no_honest_trustee_register_is_recorded(self):
        # Negative validation from r2: Trustee is a grant-path compiler.
        self.assertTrue(hasattr(Trustee, "register"))
        self.assertNotIn("Trustee.register", inspect.getsource(evaluate))

    def test_unregistered_model_is_deny(self):
        from winfs.constants import R

        decision = access_check(self.data["users"]["alice"], self.data["alice"].sid, R)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.error, "context_not_registered")
        with self.assertRaises(ContextNotRegistered):
            Context.get(type(self.data["alice"].sid))
