# LDAP Watchdog

## Overview
LDAP Watchdog is a tool designed to monitor record changes in an LDAP directory in real-time.
It provides a mechanism to track and visualize modifications, additions, and removals to user and group entries, allowing users to correlate expected changes with actual changes and identify potential security incidents.
It was created with OpenLDAP and Linux in mind, and needs a server that gives every entry an `entryUUID` (RFC 4530), so Active Directory, which uses `objectGUID` instead, is not supported.
It is written in Python and requires the ldap3 library, plus requests for Slack notifications.

This software was written by [Joshua Rogers](https://joshua.hu/).

If you're interested in any of the following, then LDAP Watchdog is for you:
- Know what's going on in your LDAP directory on-demand with Slack webhook integration.
- See new hires, leavers, and promotions as they appear in LDAP.
- Monitor _when_ and what HR is doing.
- Detect unauthorized changes in LDAP.
- Monitor for accidentally leaked data.
- Detect when users are logging in and out of LDAP.

In addition to monitoring for modifications, additions, and removals in an LDAP directory, it can be configured to ignore specific attributes, or even fine-tuned to ignore fine-grained attributes depending on their old/new values.

Changes are always printed to the terminal, and are also forwarded to a Slack webhook if one is configured. Colored output can be turned off.

Previously named LDAP-Stalker (because monitoring changes of an LDAP directory is an excellent way to stalk changes in a company: learn about promotions before they're announced, new hires, leavers, etc.), a blog post about the details and history of this project [can be found here](https://joshua.hu/ldap-watchdog-openldap-python-monitoring-tool-realtime-directory-slack-notifications).

## Examples (No Filtering)

Note: in the below examples, changes to entryCSN and modifyTimestamp on existing entries can be ignored by setting `LDAP_WATCHDOG_IGNORED_ATTRIBUTES=entryCSN,modifyTimestamp`.

### Terminal (with color) output:

![Example of the output from LDAP Watchdog](https://raw.githubusercontent.com/MegaManSec/LDAP-Monitoring-Watchdog/main/example.png "LDAP Watchdog")

### Slack output:

![Example of the output from LDAP Watchdog in Slack](https://raw.githubusercontent.com/MegaManSec/LDAP-Monitoring-Watchdog/main/example-slack.png "LDAP Watchdog")

## Features

1.  **Real-time Monitoring:** LDAP Watchdog continuously monitors an LDAP directory for changes in user and group entries.

2.  **Change Comparison:** The tool compares changes between consecutive LDAP searches, highlighting additions, modifications, and deletions.

3.  **Control User Verification:** LDAP Watchdog supports a control user mechanism, triggering an error if the control user's changes are not found.

4.  **Flexible LDAP Filtering:** Users can customize LDAP filtering using the `LDAP_WATCHDOG_SEARCH_FILTER` environment variable to focus on specific object classes or attributes.

5.  **Slack Integration:** Receive real-time notifications on Slack for added, modified, or deleted LDAP entries.

6.  **Customizable Output:** Console output provides clear and colored indications of additions, modifications, and deletions for easy visibility.

7.  **Ignored Entries and Attributes:** Users can specify UUIDs and attributes to ignore when comparing changes to existing entries.

8.  **Conditional Ignored Attributes:** Users can ignore changes to an attribute only when they involve specific values, such as one group in `memberOf`.


## Requirements
- Python 3.10+.
- The `ldap3` package. If using a Slack webhook, the `requests` package is also required.

## Installation

### PyPI

```bash
pip install LDAP-Monitor
```

To include Slack webhook support:

```bash
pip install "LDAP-Monitor[slack]"
```

### Docker

```bash
docker pull megamansec/ldap-monitor
```

Or from GitHub Container Registry:

```bash
docker pull ghcr.io/megamansec/ldap-monitoring-watchdog
```

### From Source

```bash
git clone https://github.com/MegaManSec/LDAP-Monitoring-Watchdog.git
cd LDAP-Monitoring-Watchdog
pip install ".[slack]"
```

### Upgrading

**From 1.x:** Since 2.0.0, LDAPS connections verify the server certificate and that it matches the host name or IP address in `LDAP_WATCHDOG_SERVER`; 1.0.0 checked neither. Before upgrading, set `LDAP_WATCHDOG_CA_CERTS_FILE` if the certificate is self-signed or from a private CA, and if it does not match that name, use a matching certificate or set `LDAP_WATCHDOG_TLS_VERIFY=false` (see the TLS notes under [Configuration](#configuration)). The [release notes](https://github.com/MegaManSec/LDAP-Monitoring-Watchdog/releases/tag/v2.0.0) list the other changes.

**From 1.x or 2.0.0:** Since 2.0.1, boolean settings only accept the values listed under [Configuration](#configuration). Earlier versions read anything other than `true`, `1` or `yes` as false. Now an unrecognized value stops the process at startup, an empty value means the default, and `on` or a quoted `"true"` means true. For example, an empty `LDAP_WATCHDOG_USE_SSL` with a bare host name now connects with LDAPS on port 636 instead of plain LDAP on port 389.

## Usage

### Running with pip install

```bash
export LDAP_WATCHDOG_SERVER='ldaps://ldaps.intra.lan'
export LDAP_WATCHDOG_BASE_DN='dc=mouse,dc=com'
export LDAP_WATCHDOG_USERNAME='cn=Emily,ou=People,dc=mouse,dc=com'
export LDAP_WATCHDOG_PASSWORD='qwerty123'
ldap-watchdog
```

Or using `python -m`:

```bash
python -m ldap_watchdog
```

### Running with Docker

```bash
docker run -d --restart unless-stopped \
  -e LDAP_WATCHDOG_SERVER='ldaps://ldaps.intra.lan' \
  -e LDAP_WATCHDOG_BASE_DN='dc=mouse,dc=com' \
  -e LDAP_WATCHDOG_USERNAME='cn=Emily,ou=People,dc=mouse,dc=com' \
  -e LDAP_WATCHDOG_PASSWORD='qwerty123' \
  -e SLACK_WEBHOOK_URL='https://hooks.slack.com/services/[...]' \
  -e LDAP_WATCHDOG_IGNORED_ATTRIBUTES='entryCSN,modifyTimestamp,telephoneNumber,roomNumber,gecos' \
  -e LDAP_WATCHDOG_DISABLE_COLOR_OUTPUT='true' \
  megamansec/ldap-monitor
```

### Systemd Installation (Debian-based)

A Debian-based installation script, [install.sh](https://github.com/MegaManSec/LDAP-Monitoring-Watchdog/blob/main/install.sh), is provided. It needs Python 3.10 or later and the `python3-venv` package. When run as root from a clone of this repository, this script:

1. Creates (if necessary) a Python virtual environment in `/opt/ldap-watchdog`.
2. Installs LDAP Watchdog from the clone into that virtual environment, with the dependency versions pinned in `requirements.txt`.
3. Creates an environment file at `/etc/ldap-watchdog.env` for configuration, unless one already exists.
4. Installs, enables and starts a systemd service (`/etc/systemd/system/ldap-watchdog.service`) that runs **ldap-watchdog** in the background as an unprivileged dynamic user, so a CA bundle must be world-readable.
5. Configures logging to `/var/log/ldap-watchdog.log` and `/var/log/ldap-watchdog-error.log`.
6. Sets up log rotation in `/etc/logrotate.d/ldap-watchdog`.

Rerunning the script from an updated clone upgrades the installation.

You may optionally pass a single argument to `install.sh` to set the `SLACK_WEBHOOK_URL` when the environment file is first created:

```bash
sudo ./install.sh "https://hooks.slack.com/services/[...]"
```

After installation, edit `/etc/ldap-watchdog.env` to configure the LDAP connection settings (the service fails until then), then restart the service:

```bash
sudo systemctl restart ldap-watchdog
```

## Configuration

All configuration is done via environment variables; an empty value is the same as an unset one, except for `LDAP_WATCHDOG_SLACK_BULLETPOINT`. The following variables are supported:

### General Settings

| Environment Variable | Description | Default |
|---|---|---|
| `LDAP_WATCHDOG_SERVER` | LDAP server URL or host name (e.g. `ldaps://ldaps.intra.lan`). Required. | `""` |
| `LDAP_WATCHDOG_BASE_DN` | Base Distinguished Name for LDAP searches | `""` |
| `LDAP_WATCHDOG_USERNAME` | Bind DN for authentication (e.g. `cn=Emily,ou=People,dc=mouse,dc=com`). If this or the password is empty, the bind is anonymous. | `""` |
| `LDAP_WATCHDOG_PASSWORD` | Password for `LDAP_WATCHDOG_USERNAME` | `""` |
| `LDAP_WATCHDOG_USE_SSL` | Set to `true` to use SSL (LDAPS, default port 636 instead of 389), `false` otherwise. An `ldaps://` or `ldap://` scheme in `LDAP_WATCHDOG_SERVER` overrides this. | `true` |
| `LDAP_WATCHDOG_CA_CERTS_FILE` | Optional PEM CA bundle for verifying the LDAP server certificate. If unset, system trust roots are used. | Unset |
| `LDAP_WATCHDOG_TLS_VERIFY` | Set to `false` to skip verifying the LDAP server certificate and host name. The connection is still encrypted but not authenticated. | `true` |
| `LDAP_WATCHDOG_SEARCH_FILTER` | LDAP filter for user and group entries | `(&(\|(objectClass=inetOrgPerson)(objectClass=groupOfNames)))` |
| `LDAP_WATCHDOG_SEARCH_ATTRIBUTE` | Comma-separated list of attributes to retrieve. [`*,+`](https://joshua.hu/tracking-secret-ldap-login-times-with-modifytimestamp-heuristics) is used by default to include operational attributes. `entryUUID` is always requested and must be readable for every entry. | `*,+` |
| `LDAP_WATCHDOG_REFRESH_RATE` | Whole number of seconds to wait after each LDAP search before the next one | `60` |
| `LDAP_WATCHDOG_NETWORK_TIMEOUT` | Positive integer timeout in seconds for LDAP and Slack connection/read operations. This limits individual waits, not the total duration of a poll. | `30` |
| `LDAP_WATCHDOG_DISABLE_COLOR_OUTPUT` | Set to `true` to disable colored output, which is used even when output goes to a file or `docker logs` | `false` |

Boolean settings accept `true`, `yes`, `on` or `1` and `false`, `no`, `off` or `0`, in any case and optionally quoted; any other value stops the process at startup.

LDAPS connections verify the server certificate and check that it is valid for the host name or IP address in `LDAP_WATCHDOG_SERVER`. For a private CA, set `LDAP_WATCHDOG_CA_CERTS_FILE` to a readable PEM CA bundle; in Docker, mount the bundle into the container and use its container path. A self-signed server certificate can be used as the bundle itself. If the certificate can't be provided or doesn't match the server's name, `LDAP_WATCHDOG_TLS_VERIFY=false` turns verification off; anyone on the network path can then impersonate the server and capture the bind password. For a server without TLS, use an `ldap://` URL or set `LDAP_WATCHDOG_USE_SSL=false`.

### Control User

| Environment Variable | Description | Default |
|---|---|---|
| `LDAP_WATCHDOG_CONTROL_UUID` | `entryUUID` of a control user that is changed (e.g. by a cron job) before every poll. Unless one of its attributes present in both snapshots has a new value, the comparison is rejected with an error. The user must match the base DN and search filter, and its changes are announced unless the ignore filters hide them, e.g. by listing it in `LDAP_WATCHDOG_IGNORED_UUIDS`. | `""` |
| `LDAP_WATCHDOG_CONTROL_USER_ATTRIBUTE` | Specific attribute to check in the control user. If set, it must exist in both snapshots and its value must differ. | `""` |

A failed control check logs an error and skips that comparison. The next poll compares against the most recent successfully retrieved snapshot; changes from a rejected comparison are not replayed. A failed LDAP retrieval instead preserves the previous snapshot and is retried on the next poll. Failure to retrieve the initial snapshot stops the process.

### Slack Integration

| Environment Variable | Description | Default |
|---|---|---|
| `SLACK_WEBHOOK_URL` | Slack Webhook URL for notifications. Requires the `slack` extra (`pip install "LDAP-Monitor[slack]"`). | Unset |
| `LDAP_WATCHDOG_SLACK_BULLETPOINT` | Text that starts each line of changes in Slack and console output | &bull; with one space before and three after |

Slack delivery is best effort: HTTP and network failures are logged to stderr, and monitoring and console output continue. Failed notifications are not queued or retried. Messages longer than 4,000 characters are shortened by replacing their longest words with `[...truncated...]`; if that is not enough, they are cut at 4,000 characters, dropping their last lines (additions are listed first, then removals, then modifications). Console output is never shortened.

### Ignored Entries and Attributes

These filters apply to attribute changes on entries present in both snapshots. Entry additions and deletions are always announced with all retrieved attributes, including for ignored UUIDs. UUIDs are `entryUUID` values, shown in parentheses after the DN in each message, and names and values must match exactly, including case (`modifyTimestamp`, not `modifytimestamp`). Changes hidden by `LDAP_WATCHDOG_IGNORED_ATTRIBUTES` or `LDAP_WATCHDOG_CONDITIONAL_IGNORED_ATTRIBUTES` are still written to stderr with their values; those of ignored UUIDs are skipped silently.

| Environment Variable | Description | Default |
|---|---|---|
| `LDAP_WATCHDOG_IGNORED_UUIDS` | Comma-separated list of UUIDs whose attribute changes are ignored | `""` |
| `LDAP_WATCHDOG_IGNORED_ATTRIBUTES` | Comma-separated list of attributes whose changes are ignored on existing entries | `""` |
| `LDAP_WATCHDOG_CONDITIONAL_IGNORED_ATTRIBUTES` | JSON string of attributes to conditionally ignore (see below) | `{}` |

### Conditional Ignored Attributes

The `LDAP_WATCHDOG_CONDITIONAL_IGNORED_ATTRIBUTES` variable accepts a JSON object where keys are attribute names and values are arrays of values to ignore (an array even for one value):

```bash
export LDAP_WATCHDOG_CONDITIONAL_IGNORED_ATTRIBUTES='{
  "objectClass": ["posixAccount"],
  "memberOf": ["cn=mailing-list-user,ou=Accessgroups,dc=mouse,dc=com", "cn=interns,ou=Accessgroups,dc=mouse,dc=com"],
  "organizationalStatus": ["researcher"]
}'
```

If an attribute has exactly one value before and after, the whole change is hidden when either value is listed (see Limitations). Otherwise only the listed values are dropped from the added or removed values. Invalid JSON stops the process at startup.

## Example Configuration

```bash
export LDAP_WATCHDOG_CONTROL_UUID='a71c6e4c-8881-4a03-95bf-4fc25d5e6359'
export LDAP_WATCHDOG_SERVER='ldaps://ldaps.intra.lan'
export LDAP_WATCHDOG_BASE_DN='dc=mouse,dc=com'
export LDAP_WATCHDOG_USERNAME='cn=Emily,ou=People,dc=mouse,dc=com'
export LDAP_WATCHDOG_PASSWORD='qwerty123'
export LDAP_WATCHDOG_USE_SSL='true'
export LDAP_WATCHDOG_TLS_VERIFY='true'
export LDAP_WATCHDOG_REFRESH_RATE='60'
export LDAP_WATCHDOG_NETWORK_TIMEOUT='30'
export LDAP_WATCHDOG_DISABLE_COLOR_OUTPUT='false'
export LDAP_WATCHDOG_IGNORED_UUIDS='a71c6e4c-8881-4a03-95bf-4fc25d5e6359,e191c564-6e6d-42c1-ae51-bda0509fe846,8655e0d9-ecdc-46ce-ba42-1fa3dfbf5faa'
export LDAP_WATCHDOG_IGNORED_ATTRIBUTES='entryCSN,modifyTimestamp,telephoneNumber,roomNumber,gecos'
export LDAP_WATCHDOG_CONDITIONAL_IGNORED_ATTRIBUTES='{"objectClass":["posixAccount"],"memberOf":["cn=mailing-list-user,ou=Accessgroups,dc=mouse,dc=com","cn=interns,ou=Accessgroups,dc=mouse,dc=com"],"organizationalStatus":["researcher"]}'
export SLACK_WEBHOOK_URL='https://hooks.slack.com/services/[...]'

ldap-watchdog
```

## Limitations
1. The `LDAP_WATCHDOG_CONDITIONAL_IGNORED_ATTRIBUTES` configuration may unfortunately hide important changes that are not intended to be hidden. This may happen if an attribute has a single value which is changed. This is because conditional ignored attributes will hide changes to the attribute both when the value is changed __to__ _as well as_ __from__ the ignored value; for example, if a user is a memberOf _cn=mailing-list-user,ou=Accessgroups,dc=mouse,dc=com_ which gets __changed__ to _cn=super-administrator,ou=Accessgroups,dc=mouse,dc=com_, it will be missed.
2. Similar to #1, there is no real way to determine whether a change is really a change in some cases, or a removal and then addition at the same time. In theory, it doesn't really matter, however it's important to note.
3. LDAP Watchdog polls rather than receiving changes as they happen: after each search it waits `LDAP_WATCHDOG_REFRESH_RATE` seconds, then retrieves all matching entries again and compares them with the previous snapshot. A change made and undone between two polls is never reported, and the timestamp on each message is when the change was detected, not when it was made (which `modifyTimestamp` records).


## Development

Install the package with Slack support and run the regression tests:

```bash
pip install ".[slack]"
python -m unittest discover -s tests
```

`requirements.txt` pins every dependency for the Docker image and `install.sh`. After changing the dependencies in `setup.py`, regenerate it with `pip-compile --extra=slack --output-file=requirements.txt setup.py`.

## License
This project is licensed under [GPL-3.0-or-later](https://github.com/MegaManSec/LDAP-Monitoring-Watchdog/blob/main/LICENSE).
