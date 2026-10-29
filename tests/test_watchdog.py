import io
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from ldap_watchdog import config, watchdog


UUID = '11111111-1111-1111-1111-111111111111'
DN = 'cn=Alice,dc=example,dc=com'


def snapshot(**attributes):
    return {UUID: dict(entryUUID=[UUID], dn=[DN], cn=['Alice'], **attributes)}


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        settings = patch.multiple(
            config, CONTROL_UUID='', IGNORED_UUIDS=[], IGNORED_ATTRIBUTES=[],
            CONDITIONAL_IGNORED_ATTRIBUTES={'memberOf': ['ignored']},
        )
        settings.start()
        self.addCleanup(settings.stop)

    def test_conditional_filter_preserves_unignored_multivalued_changes(self):
        for change_type, old, new in (
            ('additions', ['existing'], ['existing', 'ignored', 'important']),
            ('removals', ['existing', 'ignored', 'important'], ['existing']),
        ):
            with self.subTest(change_type=change_type):
                with patch.object(watchdog, 'announce') as announce, redirect_stderr(io.StringIO()):
                    watchdog.compare_ldap_entries(snapshot(memberOf=old), snapshot(memberOf=new))
                announce.assert_called_once()
                self.assertEqual(announce.call_args[0][2][change_type], [{'memberOf': {'important'}}])

    def test_conditional_filter_suppresses_only_ignored_changes(self):
        with patch.object(watchdog, 'announce') as announce, redirect_stderr(io.StringIO()):
            watchdog.compare_ldap_entries(
                snapshot(memberOf=['existing']), snapshot(memberOf=['existing', 'ignored']),
            )
        announce.assert_not_called()
