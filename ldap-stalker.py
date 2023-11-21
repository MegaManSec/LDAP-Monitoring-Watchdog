#!/usr/bin/python3

# This file is an original work developed by Joshua Rogers<https://joshua.hu/>.
# Licensed under the GPL3.0 License.  You should have received a copy of the GNU General Public License along with Foobar. If not, see <https://www.gnu.org/licenses/>.

import re
from ldap3 import Server, Connection, ALL, SUBTREE
import json
import os
import sys
from datetime import datetime
import requests
import time


CONTROL_UUID = ''
CONTROL_USER_ATTRIBUTE = ''

LDAP_SERVER = ''
LDAP_USERNAME = ''
LDAP_PASSWORD = ''
LDAP_USE_SSL = True
BASE_DN = ''

DISABLE_COLOR_OUTPUT = False

SEARCH_FILTER = '(&(|(objectClass=inetOrgPerson)(objectClass=groupOfNames)))'
SEARCH_ATTRIBUTE = ['*', '+']

REFRESH_RATE = 60

SLACK_BULLETPOINT = ' \u2022   '

IGNORED_UUIDS = []
IGNORED_ATTRIBUTES = []

CONDITIONAL_IGNORED_ATTRIBUTES = {}

SLACK_WEBHOOK = os.getenv('SLACK_WEBHOOK_URL')

def col(op_type):
    """
    Returns ANSI color codes for different LDAP operation types.

    Parameters:
    - op_type (str): LDAP operation type ('add', 'delete', 'modify').

    Returns:
    - str: ANSI color code.
    """
    if DISABLE_COLOR_OUTPUT:
        return ''
    return {'add': "\033[1m\033[32m", 'delete': "\033[3m\033[31m", 'modify': "\033[33m"}[op_type]


def retrieve_ldap():
    """
    Connects to the LDAP server and retrieves LDAP entries.

    Returns:
    - dict: Dictionary containing LDAP entries.
    """
    entries = {}
    server = Server(LDAP_SERVER, use_ssl=LDAP_USE_SSL, get_info=ALL)
    if LDAP_USERNAME and LDAP_PASSWORD:
        conn = Connection(server, user=LDAP_USERNAME, password=LDAP_PASSWORD)
        if not conn.bind():
            print('Error in bind:', conn.result, file=sys.stderr)
            return entries
    else:
        conn = Connection(server)
        if not conn.bind():
            print('Anonymous bind failed:', conn.result, file=sys.stderr)
            return entries

    conn.search(search_base=BASE_DN, search_filter=SEARCH_FILTER, search_scope=SUBTREE, attributes=SEARCH_ATTRIBUTE)

    for entry in conn.entries:
        entry = json.loads(entry.entry_to_json())
        entry_dict = entry['attributes']
        for attr_name, attr_value in entry_dict.items():
            attr_value = attr_value[0]
            # Some entries may be encoded using base64 and provided by a dictionary.
            # In that case, replace the dictionary with a string of the encoded data.
            if isinstance(attr_value, dict) and len(attr_value) == 2 and 'encoded' in attr_value and 'encoding' in attr_value and attr_value['encoding'] == 'base64':
                decoded_value = attr_value['encoded']
                entry_dict[attr_name] = decoded_value

        entry_dict['dn'] = [entry['dn']]
        entries[entry_dict['entryUUID'][0]] = entry_dict

    return entries

def generate_message(dn_uuid, op_type, changes):
    """
    Generates formatted messages for Slack and console output based on LDAP changes.

    Parameters:
    - dn_uuid (str): LDAP entry's UUID.
    - op_type (str): LDAP operation type ('add', 'delete', 'modify').
    - changes (dict): Dictionary containing LDAP attribute changes.

    Returns:
    - tuple: (str, str) Tuple containing Slack and console-formatted messages.
    """
    now = datetime.now()
    timestamp = now.strftime('%d/%m/%Y %H:%M:%S')

    rst_col = "\033[0m"
    stt_col = "\033[1m\033[35m"
    if DISABLE_COLOR_OUTPUT:
        rst_col = ""
        stt_col = ""

    bl = f"{SLACK_BULLETPOINT}{op_type}"

    slack_msg = f"*[{timestamp}] {op_type} {dn_uuid}*\n"
    print_msg = f"[{stt_col}{timestamp}{rst_col}] {op_type}{col(op_type)} {dn_uuid}{rst_col}\n"

    if op_type == 'modify':
        for additions in changes['additions']:
            for key, vals in additions.items():
                for val in vals:
                    slack_msg += f"{SLACK_BULLETPOINT}add *'{key}'* to *'{val}'*\n"
                    print_msg += f"{SLACK_BULLETPOINT}add '{col('modify')}{key}{rst_col}' to '{col('add')}{val}{rst_col}'\n"
        for removals in changes['removals']:
            for key, vals in removals.items():
                for val in vals:
                    slack_msg += f"{SLACK_BULLETPOINT}delete *'{key}'* was _'{val}'_\n"
                    print_msg += f"{SLACK_BULLETPOINT}delete '{col('modify')}{key}{rst_col}' was '{col('delete')}{val}{rst_col}'\n"
        for modifications in changes['modifications']:
            for key, val in modifications.items():
                slack_msg += f"{SLACK_BULLETPOINT}modify *'{key}'* to *'{val[1]}'* was _'{val[0]}'_\n"
                print_msg += f"{SLACK_BULLETPOINT}modify '{col('modify')}{key}{rst_col}' to '{col('add')}{val[1]}{rst_col}' was '{col('delete')}{val[0]}{rst_col}'\n"
    elif op_type == 'delete':
        for key, vals in changes.items():
            for val in vals:
                slack_msg += f"{bl} *'{key}'* was _'{val}'_\n"
                print_msg += f"{bl} '{col('modify')}{key}{rst_col}' was '{col('delete')}{val}{rst_col}'\n"
    elif op_type == 'add':
        for key, vals in changes.items():
            for val in vals:
                slack_msg += f"{bl} *'{key}'* to *'{val}'*\n"
                print_msg += f"{bl} '{col('modify')}{key}{rst_col}' to '{col('add')}{val}{rst_col}'\n"

    return slack_msg, print_msg


def announce(dn_uuid, op_type, changes):
    """
    Sends notification messages to Slack and prints to the console.

    Parameters:
    - dn_uuid (str): LDAP entry's UUID.
    - op_type (str): LDAP operation type ('add', 'delete', 'modify').
    - changes (dict): Dictionary containing LDAP attribute changes.

    Returns:
    - None
    """
    slack_msg, print_msg = generate_message(dn_uuid, op_type, changes)
    send_to_slack(slack_msg)
    print(print_msg)


def truncate_slack_message(message):
    """
    Truncates long Slack messages to fit within the character limit.

    Parameters:
    - message (str): Slack message.

    Returns:
    - str: Truncated Slack message.
    """
    while len(message) > 4000:
        longest_word = max(message.split(), key=len)
        message = message.replace(longest_word, "[...truncated...]")

    return message


def send_to_slack(message):
    """
    Sends a formatted message to Slack.

    Parameters:
    - message (str): Formatted message.

    Returns:
    - None
    """
    if SLACK_WEBHOOK is None or len(SLACK_WEBHOOK) == 0:
        return

    message = truncate_slack_message(message)

    headers = {'Content-type': 'application/json'}
    data = {'text': message}
    requests.post(SLACK_WEBHOOK, headers=headers, data=json.dumps(data))


def check_control_user(old_entries, new_entries):
    """
    Checks if the control user's LDAP entry has changed.

    Parameters:
    - old_entries (dict): Dictionary containing old LDAP entries.
    - new_entries (dict): Dictionary containing new LDAP entries.

    Returns:
    - bool: True if the control user's entry has changed, False otherwise.
    """
    control_user_found = False
    if CONTROL_UUID not in new_entries or CONTROL_UUID not in old_entries:
      return control_user_found

    new_entry = new_entries[CONTROL_UUID]
    old_entry = old_entries[CONTROL_UUID]

    if CONTROL_USER_ATTRIBUTE and len(CONTROL_USER_ATTRIBUTE) > 0:
        # If using CONTROL_USER_ATTRIBUTE, only compare that attribute as long as it exists in both new_entry and old_entry.
        if CONTROL_USER_ATTRIBUTE in new_entry and CONTROL_USER_ATTRIBUTE in old_entry and new_entry[CONTROL_USER_ATTRIBUTE] != old_entry[CONTROL_USER_ATTRIBUTE]:
          control_user_found = True
    else:
        # Otherwise, check that at least one attribute has changed, regardless of what it is.
        for new_attribute in new_entry.keys():
            if new_attribute in old_entry and old_entry[new_attribute] != new_entry[new_attribute]:
                control_user_found = True
                break

    return control_user_found


def compare_ldap_entries(old_entries, new_entries):
    """
    Compares old and new LDAP entries and announces modifications.

    Parameters:
    - old_entries (dict): Dictionary containing old LDAP entries.
    - new_entries (dict): Dictionary containing new LDAP entries.

    Returns:
    - None
    """
    if len(CONTROL_UUID) > 0 and not check_control_user(old_entries, new_entries):
        print('Could not confirm the control user change.', file=sys.stderr)
        return

    # XXX: The next four lines of code do not consider ignored UUIDs or ignored attributes.
    for uuid in old_entries.keys() - new_entries.keys():
        # Any entries that are in old_entries but not new_entries are deletions.
        announce(f"{old_entries[uuid]['dn'][0]} ({old_entries[uuid]['entryUUID'][0]})", "delete", old_entries[uuid])

    for uuid in new_entries.keys() - old_entries.keys():
        # Any entries that are in new_entries but not old_entries are additions.
        announce(f"{new_entries[uuid]['dn'][0]} ({new_entries[uuid]['entryUUID'][0]})", "add", new_entries[uuid])

    for uuid in old_entries.keys() & new_entries.keys():
        if uuid in IGNORED_UUIDS:
            continue  # TODO: print that it was skipped?
        if old_entries[uuid] != new_entries[uuid]:
            changes = {}
            changes.setdefault("additions", [])
            changes.setdefault("modifications", [])
            changes.setdefault("removals", [])
            for key in old_entries[uuid].keys() | new_entries[uuid].keys():
                val1 = old_entries[uuid].get(key)
                val2 = new_entries[uuid].get(key)
                if val1 != val2:
                    if val1 is None:
                        changes["additions"].append({key: val2})
                    elif val2 is None:
                        changes["removals"].append({key: val1})
                    else:
                        if len(val1) == len(val2) == 1:  # if the attribute has only one value, it is probably a modification.
                            changes["modifications"].append({key: (val1[0], val2[0])})
                        else:
                            added = set(val2) - set(val1)
                            removed = set(val1) - set(val2)
                            if added:
                                changes["additions"].append({key: added})
                            if removed:
                                changes["removals"].append({key: removed})

            for change_type in ["additions", "modifications", "removals"]:
                for attr_name in IGNORED_ATTRIBUTES:
                    for each in changes[change_type]:
                        if attr_name in each:
                            print(f"Ignoring {old_entries[uuid]['dn'][0]} ({old_entries[uuid]['entryUUID'][0]}) {each}", file=sys.stderr)
                            while each in changes[change_type]:
                                changes[change_type].remove(each)

            for change_type in ["additions", "modifications", "removals"]:
                for attr_name, ignored_attrs in CONDITIONAL_IGNORED_ATTRIBUTES.items():
                    i = 0
                    while i < len(changes[change_type]):
                        each = changes[change_type][i]
                        if attr_name in each:
                            if change_type == "modifications":
                                old_attr_value = each[attr_name][0]
                                new_attr_value = each[attr_name][1]
                                if old_attr_value in ignored_attrs or new_attr_value in ignored_attrs:
                                    print(f"Ignoring {change_type} of {old_entries[uuid]['dn'][0]} ({old_entries[uuid]['entryUUID'][0]}) {attr_name}: from {old_attr_value} to {new_attr_value}", file=sys.stderr)
                                    changes[change_type].pop(i)
                                    continue
                            else:
                                items_to_remove = []
                                for added_or_removed in each[attr_name].copy():
                                    if added_or_removed in ignored_attrs:
                                        print(f"Ignoring {change_type} of {old_entries[uuid]['dn'][0]} ({old_entries[uuid]['entryUUID'][0]}) {attr_name}: {added_or_removed}", file=sys.stderr)
                                        while added_or_removed in changes[change_type][i][attr_name]:
                                            changes[change_type][i][attr_name].remove(added_or_removed)
                                if len(changes[change_type][i][attr_name]) == 0:
                                    changes[change_type].pop(i)
                                    continue
                        i += 1

            changes_to_announce = False
            for change_type in ["additions", "modifications", "removals"]:
                if len(changes[change_type]) > 0:
                    changes_to_announce = True
                    break
            if changes_to_announce:
                announce(f"{old_entries[uuid]['dn'][0]} ({old_entries[uuid]['entryUUID'][0]})", "modify", changes)


if __name__ == '__main__':
    new_entries = retrieve_ldap()
    while True:
        time.sleep(REFRESH_RATE)
        old_entries = new_entries
        retrieved_entries = retrieve_ldap()
        if len(retrieved_entries) == 0:
            continue
        new_entries = retrieved_entries
        compare_ldap_entries(old_entries, new_entries)
