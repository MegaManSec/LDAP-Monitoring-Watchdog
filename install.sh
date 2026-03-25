#!/bin/bash
set -e

VENV_PATH="/opt/ldap-watchdog"

if [ ! -d "$VENV_PATH" ]; then
    python3 -m venv "$VENV_PATH"
fi
"$VENV_PATH/bin/pip" install --upgrade pip
"$VENV_PATH/bin/pip" install "LDAP-Monitor[slack]"

if [ "$#" -eq 1 ]; then
    SLACK_WEBHOOK_URL=$1
fi

# Step 1: Create an environment file for configuration
LDAP_DIFF_ENV_FILE="/etc/ldap-watchdog.env"
if [ ! -f "$LDAP_DIFF_ENV_FILE" ]; then
    cat <<EOL > $LDAP_DIFF_ENV_FILE
# LDAP Watchdog Configuration
# See README.md for all available environment variables.
LDAP_WATCHDOG_SERVER=
LDAP_WATCHDOG_BASE_DN=
LDAP_WATCHDOG_USERNAME=
LDAP_WATCHDOG_PASSWORD=
LDAP_WATCHDOG_USE_SSL=true
LDAP_WATCHDOG_REFRESH_RATE=60
SLACK_WEBHOOK_URL=$SLACK_WEBHOOK_URL
EOL
    chmod 600 "$LDAP_DIFF_ENV_FILE"
    echo "Created $LDAP_DIFF_ENV_FILE - edit this file to configure LDAP Watchdog."
fi

# Step 2: Create a service file and logrotate configuration for ldap-watchdog
LDAP_DIFF_LOG_FILE="/var/log/ldap-watchdog.log"
LDAP_DIFF_ERROR_LOG_FILE="/var/log/ldap-watchdog-error.log"
LDAP_DIFF_SERVICE_FILE="/etc/systemd/system/ldap-watchdog.service"
LDAP_DIFF_LOGROTATE_FILE="/etc/logrotate.d/ldap-watchdog"

cat <<EOL > $LDAP_DIFF_SERVICE_FILE
[Unit]
Description=ldap-watchdog Service
After=network.target

[Service]
Type=simple
ExecStart=$VENV_PATH/bin/ldap-watchdog
Restart=always
DynamicUser=yes
EnvironmentFile=$LDAP_DIFF_ENV_FILE
StandardOutput=append:$LDAP_DIFF_LOG_FILE
StandardError=append:$LDAP_DIFF_ERROR_LOG_FILE

[Install]
WantedBy=multi-user.target
EOL

cat <<EOL > $LDAP_DIFF_LOGROTATE_FILE
$LDAP_DIFF_LOG_FILE $LDAP_DIFF_ERROR_LOG_FILE {
    monthly
    rotate 12
    compress
    missingok
    notifempty
    copytruncate
}
EOL


systemctl daemon-reload
systemctl enable ldap-watchdog
systemctl start ldap-watchdog

echo "ldap-watchdog has been installed, the service is started, and log rotation is set up."
echo " - Configuration: $LDAP_DIFF_ENV_FILE"
echo " - Virtual env: $VENV_PATH"
echo " - Systemd service: $LDAP_DIFF_SERVICE_FILE"
echo " - Logs: $LDAP_DIFF_LOG_FILE and $LDAP_DIFF_ERROR_LOG_FILE"
echo " - Log rotation conf: $LDAP_DIFF_LOGROTATE_FILE"
