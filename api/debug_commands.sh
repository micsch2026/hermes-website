#!/bin/bash
# DEBUG COMMANDS

echo "=== 1. authorized_keys check ==="
cat /home/hermes/.ssh/authorized_keys

echo ""
echo "=== 2. SSH Config ==="
grep -E "PubkeyAuthentication|PermitRootLogin|PasswordAuthentication" /etc/ssh/sshd_config

echo ""
echo "=== 3. sshd status ==="
systemctl status sshd | head -5
