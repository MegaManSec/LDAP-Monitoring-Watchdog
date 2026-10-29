import io
import json
import unittest
from contextlib import redirect_stderr
from unittest.mock import Mock, patch

from ldap3 import Connection, MOCK_SYNC, OFFLINE_SLAPD_2_4, Server
from ldap3.core.exceptions import LDAPException, LDAPSocketReceiveError

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
        entry = dict(
            objectClass=['inetOrgPerson'], cn=['Alice'], sn=['Example'],
            entryUUID=[UUID],
        )
        entry.update(attributes)
        connection.strategy.add_entry(DN, entry)
        with patch.object(watchdog, 'Server'), patch.object(watchdog, 'Connection', return_value=connection):
            return watchdog.retrieve_ldap()

    def test_absent_requested_attribute_is_empty(self):
        config.SEARCH_ATTRIBUTE = ['cn', 'mail', 'entryUUID']
        self.assertEqual(self.retrieve()[UUID]['mail'], [])

    def test_uuid_is_retrieved_with_custom_attribute_selection(self):
        config.SEARCH_ATTRIBUTE = ['cn']
        self.assertEqual(self.retrieve()[UUID]['entryUUID'], [UUID])
        self.assertEqual(config.SEARCH_ATTRIBUTE, ['cn'])

    def test_missing_uuid_rejects_the_snapshot(self):
        with self.assertRaisesRegex(LDAPException, 'no readable entryUUID'):
            self.retrieve(entryUUID=[])

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


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.connection = Mock()
        self.connection.bind.return_value = True
        self.connection.result = {'result': 0}
        self.connection.entries = []
        for patcher in (
            patch.object(watchdog, 'Server'),
            patch.object(watchdog, 'Connection', return_value=self.connection),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_failed_bind_is_not_an_empty_snapshot(self):
        self.connection.bind.return_value = False
        self.connection.result = {'result': 49, 'description': 'invalidCredentials'}
        with self.assertRaisesRegex(LDAPException, 'bind failed'):
            watchdog.retrieve_ldap()
        self.connection.unbind.assert_called_once()

    def test_successful_empty_search_is_a_valid_snapshot(self):
        self.connection.search.return_value = False
        self.assertEqual(watchdog.retrieve_ldap(), {})
        self.connection.unbind.assert_called_once()

    def set_page(self, uuid, cookie, result=0):
        self.connection.entries = [Mock(entry_to_json=Mock(return_value=json.dumps({
            'dn': DN, 'attributes': {'entryUUID': [uuid]},
        })))]
        self.connection.result = {
            'result': result,
            'controls': {'1.2.840.113556.1.4.319': {'value': {'cookie': cookie}}},
        }

    def test_all_pages_are_retrieved(self):
        pages = iter([(UUID, b'next'), ('second', b'')])
        self.connection.search.side_effect = lambda **kwargs: self.set_page(*next(pages))
        self.assertEqual(set(watchdog.retrieve_ldap()), {UUID, 'second'})
        calls = self.connection.search.call_args_list
        self.assertEqual([call[1]['paged_cookie'] for call in calls], [None, b'next'])
        self.connection.unbind.assert_called_once()

    def test_later_page_failure_rejects_the_entire_snapshot(self):
        pages = iter([(UUID, b'next', 0), ('second', b'', 4)])
        self.connection.search.side_effect = lambda **kwargs: self.set_page(*next(pages))
        with self.assertRaisesRegex(LDAPException, 'search failed'):
            watchdog.retrieve_ldap()
        self.connection.unbind.assert_called_once()

    def test_failed_poll_preserves_the_last_successful_snapshot(self):
        old = snapshot(title=['old'])
        new = snapshot(title=['new'])
        for error in (LDAPException('search failed'), LDAPSocketReceiveError('disconnected')):
            with self.subTest(error=type(error).__name__):
                with patch.object(watchdog, 'retrieve_ldap', side_effect=[old, error, new]), \
                        patch.object(watchdog.time, 'sleep', side_effect=[None, None, KeyboardInterrupt]), \
                        patch.object(watchdog, 'compare_ldap_entries') as compare, \
                        redirect_stderr(io.StringIO()):
                    with self.assertRaises(KeyboardInterrupt):
                        watchdog.main()
                compare.assert_called_once_with(old, new)
