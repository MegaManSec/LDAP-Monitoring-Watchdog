# This file is an original work developed by Joshua Rogers<https://joshua.hu/>.
# Licensed under the GPL3.0 License.

import json
import os


def _parse_bool(name, default):
    raw = os.getenv(name, '')
    val = raw.strip()
    if len(val) > 1 and val[0] == val[-1] and val[0] in '"\'':
        val = val[1:-1]
    val = val.lower()
    if not val:
        return default
    if val in ('true', '1', 'yes', 'on'):
        return True
    if val in ('false', '0', 'no', 'off'):
        return False
    raise ValueError(f'{name} must be true/false, 1/0, yes/no or on/off, not {raw!r}')


def _parse_list(val):
    if not val or not val.strip():
        return []
    return [item.strip() for item in val.split(',')]


def _parse_json_dict(val):
    if not val or not val.strip():
        return {}
    return json.loads(val)


CONTROL_UUID = os.getenv('LDAP_WATCHDOG_CONTROL_UUID', '')
CONTROL_USER_ATTRIBUTE = os.getenv('LDAP_WATCHDOG_CONTROL_USER_ATTRIBUTE', '')

LDAP_SERVER = os.getenv('LDAP_WATCHDOG_SERVER', '')
LDAP_USERNAME = os.getenv('LDAP_WATCHDOG_USERNAME', '')
LDAP_PASSWORD = os.getenv('LDAP_WATCHDOG_PASSWORD', '')
LDAP_USE_SSL = _parse_bool('LDAP_WATCHDOG_USE_SSL', True)
LDAP_CA_CERTS_FILE = os.getenv('LDAP_WATCHDOG_CA_CERTS_FILE') or None
LDAP_TLS_VERIFY = _parse_bool('LDAP_WATCHDOG_TLS_VERIFY', True)
BASE_DN = os.getenv('LDAP_WATCHDOG_BASE_DN', '')

DISABLE_COLOR_OUTPUT = _parse_bool('LDAP_WATCHDOG_DISABLE_COLOR_OUTPUT', False)

SEARCH_FILTER = os.getenv('LDAP_WATCHDOG_SEARCH_FILTER', '(&(|(objectClass=inetOrgPerson)(objectClass=groupOfNames)))')
SEARCH_ATTRIBUTE = _parse_list(os.getenv('LDAP_WATCHDOG_SEARCH_ATTRIBUTE', '*,+'))

REFRESH_RATE = int(os.getenv('LDAP_WATCHDOG_REFRESH_RATE', '60'))
NETWORK_TIMEOUT = int(os.getenv('LDAP_WATCHDOG_NETWORK_TIMEOUT', '30'))
if NETWORK_TIMEOUT <= 0:
    raise ValueError('LDAP_WATCHDOG_NETWORK_TIMEOUT must be greater than zero')

SLACK_BULLETPOINT = os.getenv('LDAP_WATCHDOG_SLACK_BULLETPOINT', ' \u2022   ')

IGNORED_UUIDS = _parse_list(os.getenv('LDAP_WATCHDOG_IGNORED_UUIDS', ''))
IGNORED_ATTRIBUTES = _parse_list(os.getenv('LDAP_WATCHDOG_IGNORED_ATTRIBUTES', ''))

CONDITIONAL_IGNORED_ATTRIBUTES = _parse_json_dict(os.getenv('LDAP_WATCHDOG_CONDITIONAL_IGNORED_ATTRIBUTES', '{}'))

SLACK_WEBHOOK = os.getenv('SLACK_WEBHOOK_URL')

if SLACK_WEBHOOK and len(SLACK_WEBHOOK) > 0:
    import requests  # noqa: F401
