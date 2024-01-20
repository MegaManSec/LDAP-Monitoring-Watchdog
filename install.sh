#!/bin/bash
set -e

pip3 install ldap3

if [ "$#" -eq 1 ]; then
    pip3 install requests
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
ExecStart=$LDAP_DIFF_EXECUTABLE
Restart=always
DynamicUser=yes
Environment=SLACK_WEBHOOK_URL=$SLACK_WEBHOOK_URL
StandardOutput=append:$LDAP_DIFF_LOG_FILE
StandardError=append:$LDAP_DIFF_ERROR_LOG_FILE

[Install]
WantedBy=default.target
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

# Step 3: Reload systemd and start the ldap-watchdog service
systemctl daemon-reload
systemctl start ldap-watchdog

# Step 4: Enable the ldap-watchdog service to start at boot
systemctl enable ldap-watchdog

echo "LDAP-Watchdog has been installed in $LDAP_DIFF_EXECUTABLE, and a service has been installed in $LDAP_DIFF_SERVICE_FILE. The service is started and logging to $LDAP_DIFF_LOG_FILE and $LDAP_DIFF_ERROR_LOG_FILE, and log rotation is set up in $LDAP_DIFF_LOGROTATE_FILE."
