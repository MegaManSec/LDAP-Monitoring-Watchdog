#!/bin/bash
set -e

VENV_PATH="/opt/ldap-watchdog"

if [ ! -d "$VENV_PATH" ]; then
    python3 -m venv "$VENV_PATH"
fi
"$VENV_PATH/bin/pip" install --upgrade pip
"$VENV_PATH/bin/pip" install ldap3 requests

if [ "$#" -eq 1 ]; then
    SLACK_WEBHOOK_URL=$1
fi

# Step 1: Install ldap-watchdog.py
LDAP_DIFF_EXECUTABLE="/usr/local/bin/ldap-watchdog.py"
cp ldap-watchdog.py "$LDAP_DIFF_EXECUTABLE"
chmod +x "$LDAP_DIFF_EXECUTABLE"
chown root:root "$LDAP_DIFF_EXECUTABLE"

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
ExecStart=$VENV_PATH/bin/python $LDAP_DIFF_EXECUTABLE
Restart=always
DynamicUser=yes
Environment=SLACK_WEBHOOK_URL=$SLACK_WEBHOOK_URL
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
echo " - Main script: $LDAP_DIFF_EXECUTABLE"
echo " - Virtual env: $VENV_PATH"
echo " - Systemd service: $LDAP_DIFF_SERVICE_FILE"
echo " - Logs: $LDAP_DIFF_LOG_FILE and $LDAP_DIFF_ERROR_LOG_FILE"
echo " - Log rotation conf: $LDAP_DIFF_LOGROTATE_FILE"
