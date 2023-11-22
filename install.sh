#!/bin/bash

if [ "$#" -eq 1 ]; then
    SLACK_WEBHOOK_URL=$1
fi

# Step 1: Install ldap-stalker.py
LDAP_DIFF_EXECUTABLE="/usr/local/bin/ldap-stalker.py"
cp ldap-stalker.py "$LDAP_DIFF_EXECUTABLE"
chmod +x "$LDAP_DIFF_EXECUTABLE"

# Step 2: Create a service file and logrotate configuration for ldap-stalker
LDAP_DIFF_LOG_FILE="/var/log/ldap-stalker.log"
LDAP_DIFF_SERVICE_FILE="/etc/systemd/system/ldap-stalker.service"
LDAP_DIFF_LOGROTATE_FILE="/etc/logrotate.d/ldap-stalker"

cat <<EOL > $LDAP_DIFF_SERVICE_FILE
[Unit]
Description=ldap-stalker Service
After=network.target

[Service]
ExecStart=$LDAP_DIFF_EXECUTABLE
Restart=always
DynamicUser=yes
Environment=SLACK_WEBHOOK_URL=$SLACK_WEBHOOK_URL
StandardOutput=append:$LDAP_DIFF_LOG_FILE
StandardError=append:$LDAP_DIFF_LOG_FILE

[Install]
WantedBy=default.target
EOL

cat <<EOL > $LDAP_DIFF_LOGROTATE_FILE
$LDAP_DIFF_LOG_FILE {
    daily
    rotate 31
    compress
    missingok
    notifempty
    copytruncate
}
EOL

# Step 3: Reload systemd and start the ldap-stalker service
systemctl daemon-reload
systemctl start ldap-stalker

# Step 4: Enable the ldap-stalker service to start at boot
systemctl enable ldap-stalker

echo "ldap-stalker has been installed, the service is started, and log rotation is set up."
