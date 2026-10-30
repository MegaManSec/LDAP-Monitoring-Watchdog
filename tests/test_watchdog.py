import copy
import importlib
import io
import json
import os
import socket
import ssl
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import Mock, patch

from ldap3 import Connection, MOCK_SYNC, OFFLINE_SLAPD_2_4, Server
from ldap3.core.exceptions import LDAPException, LDAPSocketReceiveError
import requests

from ldap_watchdog import config, watchdog


UUID = '11111111-1111-1111-1111-111111111111'
DN = 'cn=Alice,dc=example,dc=com'
CERTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'certs')


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

    def test_conditional_filter_leaves_snapshots_unchanged(self):
        for change_type, old, new in (
            ('additions', snapshot(), snapshot(memberOf=['ignored', 'important'])),
            ('removals', snapshot(memberOf=['ignored', 'important']), snapshot()),
        ):
            with self.subTest(change_type=change_type):
                expected = copy.deepcopy((old, new))
                with patch.object(watchdog, 'announce') as announce, redirect_stderr(io.StringIO()):
                    watchdog.compare_ldap_entries(old, new)
                self.assertEqual(announce.call_args[0][2][change_type], [{'memberOf': ['important']}])
                self.assertEqual((old, new), expected)


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

    def test_truncation_keeps_the_changed_entry_in_the_header(self):
        for op_type in ('add', 'delete'):
            message, _ = watchdog.generate_message(DN, op_type, {
                'member': [f'uid=user{i},ou=People,dc=example,dc=com' for i in range(100)],
            })
            with self.subTest(op_type=op_type):
                header = message.partition('\n')[0]
                self.assertIn(DN, header)
                self.assertEqual(watchdog.truncate_slack_message(message).partition('\n')[0], header)

    def test_truncation_replaces_the_longest_words_first(self):
        for words, expected in (
            (['b' * 2500, 'a' * 2500, 'c' * 100], ['[...truncated...]', 'a' * 2500, 'c' * 100]),
            (['x' * 2000, 'y' * 600, 'x' * 2000, 'z' * 20], ['[...truncated...]', 'y' * 600, '[...truncated...]', 'z' * 20]),
        ):
            with self.subTest(words=[len(word) for word in words]):
                self.assertEqual(watchdog.truncate_slack_message(' '.join(words)), ' '.join(expected))

    def test_truncation_of_large_groups_is_fast(self):
        message, _ = watchdog.generate_message(DN, 'delete', {
            'member': [f'uid=user{i:06d},ou=People,dc=example,dc=com' for i in range(8000)],
        })
        start = time.perf_counter()
        truncated = watchdog.truncate_slack_message(message)
        self.assertLess(time.perf_counter() - start, 1)
        self.assertEqual(len(truncated), 4000)


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


class TLSTests(unittest.TestCase):
    def test_ldaps_requires_a_trusted_certificate(self):
        connection = Mock()
        connection.bind.return_value = False
        with patch.multiple(config, LDAP_SERVER='ldaps://localhost', LDAP_CA_CERTS_FILE=None), \
                patch.object(watchdog, 'Connection', return_value=connection) as factory:
            with self.assertRaises(LDAPException):
                watchdog.retrieve_ldap()
        server = factory.call_args[0][0]
        self.assertTrue(server.ssl)
        self.assertEqual(server.tls.validate, ssl.CERT_REQUIRED)

    def requests_received(self, certificate, host, ca_certs_file, verify=True):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(os.path.join(CERTS, certificate))
        server_names, received = [], []
        context.sni_callback = lambda tls, server_name, _: server_names.append(server_name)
        listener = socket.socket()
        listener.settimeout(5)
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)

        def serve():
            with listener:
                try:
                    with listener.accept()[0] as client, context.wrap_socket(client, server_side=True) as tls:
                        if tls.recv(1):
                            received.append(server_names[-1])
                except OSError:
                    pass

        server = threading.Thread(target=serve)
        server.start()
        with patch.multiple(config, LDAP_SERVER=f'ldaps://{host}:{listener.getsockname()[1]}',
                            LDAP_CA_CERTS_FILE=ca_certs_file and os.path.join(CERTS, ca_certs_file),
                            LDAP_TLS_VERIFY=verify, LDAP_USERNAME='', LDAP_PASSWORD='', NETWORK_TIMEOUT=5):
            with self.assertRaises(LDAPException):
                watchdog.retrieve_ldap()
        server.join()
        return received

    def test_certificate_is_verified_for_dns_names_and_ip_addresses(self):
        for host, server_name in (('localhost', 'localhost'), ('127.0.0.1', None)):
            with self.subTest(host=host):
                self.assertEqual(self.requests_received('localhost.pem', host, 'localhost.pem'), [server_name])

    def test_mismatched_or_untrusted_certificates_are_rejected(self):
        for certificate, host, ca_certs_file in (
            ('ldap.example.com.pem', 'localhost', 'ldap.example.com.pem'),
            ('ldap.example.com.pem', '127.0.0.1', 'ldap.example.com.pem'),
            ('localhost.pem', 'localhost', None),
        ):
            with self.subTest(certificate=certificate, host=host, ca_certs_file=ca_certs_file):
                self.assertEqual(self.requests_received(certificate, host, ca_certs_file), [])

    def test_verification_can_be_turned_off(self):
        for certificate, host in (('ldap.example.com.pem', 'localhost'), ('localhost.pem', '127.0.0.1')):
            with self.subTest(certificate=certificate, host=host):
                self.assertEqual(len(self.requests_received(certificate, host, None, verify=False)), 1)


class ConfigTests(unittest.TestCase):
    BOOLEANS = (
        ('LDAP_WATCHDOG_USE_SSL', 'LDAP_USE_SSL', True),
        ('LDAP_WATCHDOG_TLS_VERIFY', 'LDAP_TLS_VERIFY', True),
        ('LDAP_WATCHDOG_DISABLE_COLOR_OUTPUT', 'DISABLE_COLOR_OUTPUT', False),
    )

    def setUp(self):
        self.addCleanup(importlib.reload, config)

    def load(self, **environ):
        with patch.dict(os.environ, environ):
            importlib.reload(config)

    def test_booleans_accept_common_spellings_and_default_when_empty(self):
        for variable, attribute, default in self.BOOLEANS:
            for value, expected in (
                ('', default), ('  ', default), ('""', default), ('" "', default),
                ('true', True), ('TRUE', True), (' yes ', True), ('"1"', True), ("'on'", True), ('" true "', True),
                ('false', False), ('Off', False), ('"no"', False), ('0 ', False),
            ):
                with self.subTest(variable=variable, value=value):
                    self.load(**{variable: value})
                    self.assertIs(getattr(config, attribute), expected)

    def test_unrecognized_booleans_are_rejected(self):
        for variable, _, _ in self.BOOLEANS:
            for value in ('enabled', 'ture', '"true', '\'true"'):
                with self.subTest(variable=variable, value=value):
                    with self.assertRaises(ValueError) as raised:
                        self.load(**{variable: value})
                    self.assertIn(variable, str(raised.exception))
                    self.assertIn(repr(value), str(raised.exception))

    def test_empty_settings_use_their_defaults(self):
        for value in ('', '  '):
            with self.subTest(value=value):
                self.load(**dict.fromkeys((
                    'LDAP_WATCHDOG_SEARCH_FILTER', 'LDAP_WATCHDOG_SEARCH_ATTRIBUTE',
                    'LDAP_WATCHDOG_REFRESH_RATE', 'LDAP_WATCHDOG_NETWORK_TIMEOUT',
                ), value))
                self.assertEqual(
                    (config.SEARCH_FILTER, config.SEARCH_ATTRIBUTE, config.REFRESH_RATE, config.NETWORK_TIMEOUT),
                    ('(&(|(objectClass=inetOrgPerson)(objectClass=groupOfNames)))', ['*', '+'], 60, 30),
                )


class NetworkTests(unittest.TestCase):
    def test_ldap_waits_are_bounded_for_authenticated_and_anonymous_binds(self):
        for username, password in (('', ''), ('alice', 'password')):
            with self.subTest(authenticated=bool(username)):
                connection = Mock()
                connection.bind.return_value = False
                with patch.multiple(config, LDAP_SERVER='localhost', LDAP_CA_CERTS_FILE=None,
                                    LDAP_USERNAME=username, LDAP_PASSWORD=password, NETWORK_TIMEOUT=7), \
                        patch.object(watchdog, 'Connection', return_value=connection) as factory:
                    with self.assertRaises(LDAPException):
                        watchdog.retrieve_ldap()
                self.assertEqual(factory.call_args[0][0].connect_timeout, 7)
                self.assertEqual(factory.call_args[1]['receive_timeout'], 7)

    def test_slack_failures_are_reported_without_losing_console_output(self):
        response = requests.Response()
        response.status_code = 429
        response.url = 'https://example.invalid/secret-webhook'
        for failure in (response, requests.ConnectionError('secret-webhook')):
            with self.subTest(failure=type(failure).__name__):
                output, errors = io.StringIO(), io.StringIO()
                with patch.multiple(config, SLACK_WEBHOOK=response.url, NETWORK_TIMEOUT=7), \
                        patch.object(watchdog, 'requests', requests, create=True), \
                        patch.object(requests, 'post') as post, \
                        redirect_stdout(output), redirect_stderr(errors):
                    if isinstance(failure, Exception):
                        post.side_effect = failure
                    else:
                        post.return_value = failure
                    watchdog.announce(DN, 'add', {'cn': ['Alice']})
                self.assertIn('Alice', output.getvalue())
                self.assertIn('Slack notification failed', errors.getvalue())
                self.assertIn('ConnectionError' if isinstance(failure, Exception) else 'HTTP 429', errors.getvalue())
                self.assertNotIn('secret-webhook', errors.getvalue())
                self.assertEqual(post.call_args[1]['timeout'], 7)
