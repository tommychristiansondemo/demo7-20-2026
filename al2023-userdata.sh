#!/bin/bash
# =============================================================================
# ISS Notifier Demo — EC2 User Data Bootstrap Script
# Paste the entire contents of this file into the "User Data" field in the
# EC2 Launch Wizard under "Advanced details" when launching a t3.large
# Amazon Linux 2023 instance.
#
# The script runs automatically on first boot as root.
# Progress is logged to: /var/log/cloud-init-output.log
# Expected runtime: 20-30 minutes. The instance reboots automatically when done.
# After reboot: SSH in, run "sudo passwd ec2-user", then connect via DCV.
# =============================================================================

set -e
exec > >(tee /var/log/iss-demo-setup.log | logger -t iss-demo-setup) 2>&1

echo "===> [1/9] Updating system packages..."
dnf update -y

echo "===> [2/9] Installing GNOME desktop..."
dnf groupinstall "Desktop" -y
sed -i '/^\[daemon\]/a WaylandEnable=false' /etc/gdm/custom.conf
systemctl set-default graphical.target

echo "===> [3/9] Installing dummy X driver for headless display..."
dnf install -y xorg-x11-drv-dummy
tee /etc/X11/xorg.conf > /dev/null << 'EOF'
Section "Device"
    Identifier "DummyDevice"
    Driver "dummy"
    VideoRam 256000
EndSection

Section "Screen"
    Identifier "DummyScreen"
    Device "DummyDevice"
    Monitor "DummyMonitor"
    DefaultDepth 24
    SubSection "Display"
        Depth 24
        Modes "1920x1080"
    EndSubSection
EndSection

Section "Monitor"
    Identifier "DummyMonitor"
    HorizSync 30-70
    VertRefresh 50-75
EndSection
EOF

echo "===> [4/9] Installing NICE DCV..."
cd /tmp
rpm --import https://d1uj6qtbmh3dt5.cloudfront.net/NICE-GPG-KEY
curl -L -O https://d1uj6qtbmh3dt5.cloudfront.net/nice-dcv-amzn2023-$(arch).tgz
tar -xvzf nice-dcv-amzn2023-$(arch).tgz
cd nice-dcv-*-amzn2023-$(arch)
dnf install -y ./nice-dcv-server-*.rpm
dnf install -y ./nice-dcv-web-viewer-*.rpm
dnf install -y ./nice-xdcv-*.rpm
systemctl enable dcvserver

echo "===> [5/9] Configuring NICE DCV automatic console session..."
sed -i "/^\[session-management\/automatic-console-session/a owner=\"ec2-user\"\nstorage-root=\"%home%\"" /etc/dcv/dcv.conf
sed -i "s/^#create-session/create-session/g" /etc/dcv/dcv.conf

echo "===> [6/9] Installing Node.js, npm, and cups..."
dnf install -y nodejs npm cups
usermod -a -G sys dcv
systemctl enable --now cups

echo "===> [7/9] Installing Python 3.12..."
dnf install -y python3.12 python3.12-pip

# Configure Python 3.12 as default for ec2-user
cat >> /home/ec2-user/.bashrc << 'BASHRC'
alias python3=python3.12
alias pip3="python3.12 -m pip"
export PATH="$HOME/.local/bin:$PATH"
BASHRC
chown ec2-user:ec2-user /home/ec2-user/.bashrc

echo "===> [8/9] Installing Python packages and uv..."
# Run pip installs as ec2-user so packages land in the correct user environment
su - ec2-user -c "python3.12 -m pip install uv --user"
su - ec2-user -c "python3.12 -m pip install \
    strands-agents \
    strands-agents-tools \
    bedrock-agentcore \
    boto3 \
    aws-cdk-lib"

echo "===> [9/9] Installing AWS CDK globally..."
npm install -g aws-cdk

echo ""
echo "============================================="
echo "  Setup complete. Instance will reboot now."
echo "  After reboot:"
echo "  1. SSH in and run: sudo passwd ec2-user"
echo "  2. Connect via DCV at https://<YOUR_IP>:8443"
echo "  3. Open terminal in GNOME and run: kiro"
echo "============================================="

reboot
