import io
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from ldap3 import Connection, MOCK_SYNC, OFFLINE_SLAPD_2_4, Server

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


class MessageTests(unittest.TestCase):
    def test_short_messages_are_unchanged(self):
        for message in ('', 'hello', 'x' * 4000):
            self.assertEqual(watchdog.truncate_slack_message(message), message)

    def test_truncation_handles_many_short_words_and_whitespace(self):
        group_message, _ = watchdog.generate_message(DN, 'add', {
            'member': [f'uid=user{i},ou=People,dc=example,dc=com' for i in range(100)],
        })
        for message in ('word ' * 1000, ' ' * 5000, group_message):
            with self.subTest(length=len(message)):
                truncated = watchdog.truncate_slack_message(message)
                self.assertLessEqual(len(truncated), 4000)
                self.assertIn('[...truncated...]', truncated)

    def test_truncation_preserves_text_after_a_large_value(self):
        message = 'photo ' + 'x' * 5000 + ' important change'
        self.assertEqual(
            watchdog.truncate_slack_message(message),
            'photo [...truncated...] important change',
        )


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        settings = patch.multiple(
            config, LDAP_SERVER='mock', LDAP_USERNAME='', LDAP_PASSWORD='',
            BASE_DN='dc=example,dc=com', SEARCH_FILTER='(objectClass=inetOrgPerson)',
            SEARCH_ATTRIBUTE=['*', '+'], CONTROL_UUID='', IGNORED_UUIDS=[],
            IGNORED_ATTRIBUTES=[], CONDITIONAL_IGNORED_ATTRIBUTES={},
        )
        settings.start()
        self.addCleanup(settings.stop)

    def retrieve(self, **attributes):
        connection = Connection(Server('mock', get_info=OFFLINE_SLAPD_2_4), client_strategy=MOCK_SYNC)
        connection.strategy.add_entry(DN, dict(
            objectClass=['inetOrgPerson'], cn=['Alice'], sn=['Example'],
            entryUUID=[UUID], **attributes,
        ))
        with patch.object(watchdog, 'Server'), patch.object(watchdog, 'Connection', return_value=connection):
            return watchdog.retrieve_ldap()

    def test_absent_requested_attribute_is_empty(self):
        config.SEARCH_ATTRIBUTE = ['cn', 'mail', 'entryUUID']
        self.assertEqual(self.retrieve()[UUID]['mail'], [])

    def test_all_binary_values_are_preserved(self):
        entry = self.retrieve(jpegPhoto=[b'\xff\x00', b'\x03\xfc'])[UUID]
        self.assertEqual(entry['jpegPhoto'], ['/wA=', 'A/w='])

    def test_binary_changes_compare_whole_values(self):
        old = self.retrieve(jpegPhoto=[b'\xff\x00'])
        new = self.retrieve(jpegPhoto=[b'\x03\xfc'])
        with patch.object(watchdog, 'announce') as announce:
            watchdog.compare_ldap_entries(old, new)
        announce.assert_called_once()
        self.assertEqual(announce.call_args[0][2]['modifications'], [{'jpegPhoto': ('/wA=', 'A/w=')}])
