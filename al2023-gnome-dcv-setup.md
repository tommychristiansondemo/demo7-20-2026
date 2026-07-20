# Amazon Linux 2023 — GNOME Desktop + NICE DCV Setup Guide
### For AWS Instructor Demo Environment (ISS Overhead Notifier)

This guide sets up a graphical EC2 instance running Amazon Linux 2023 with the official
GNOME desktop, NICE DCV remote display, Python 3.12, and Kiro. When complete, the
finished environment is captured as an AMI. Every class session starts by launching a
fresh instance from that AMI.

---

> ## How This Guide Is Used
>
> **Parts 1–10 are recorded as a video and distributed to students.** They are not
> performed during class. Students who want to build the environment from scratch can
> follow the video. Everyone else launches directly from the shared AMI.
>
> **The live class demo begins after launching an instance from the AMI captured in Part 11.**
>
> **Important:** After launching any instance from the AMI, you must set a fresh password
> for ec2-user before connecting via DCV. Passwords are not preserved in AMI snapshots.
> This takes 30 seconds and is covered in the "Every Time You Launch" section at the end
> of this guide.

---

## Part 1 — Launch the EC2 Instance

### Recommended Instance Configuration

| Setting | Value |
|---|---|
| **AMI** | Amazon Linux 2023 (latest, x86_64) |
| **Instance type** | `t3.large` (2 vCPU, 8 GB RAM) — minimum `t3.medium` |
| **Storage** | 30 GB gp3 |
| **Key pair** | Create or select one at launch; you will need the `.pem` file |
| **IAM Instance Profile** | Attach your demo IAM role at launch (see below) |
| **Security group** | See inbound rules below |

> **Why `t3.large`?** GNOME + DCV + Kiro + a browser comfortably fit in 8 GB. A
> `t3.medium` (4 GB) will work but may feel sluggish during the demo.

### Security Group — Inbound Rules

| Type | Protocol | Port | Source |
|---|---|---|---|
| SSH | TCP | 22 | Your IP |
| Custom TCP | TCP | 8443 | Your IP |

Port 8443 is the NICE DCV default. If you want students to connect to their own
instances, broaden the source to `0.0.0.0/0` or your course CIDR range.

### IAM Instance Profile Permissions

Attach these AWS managed policies to the EC2 instance role at launch time. No credentials
files will exist on the machine — the SDK and CLI pick up temporary credentials
automatically from the EC2 instance metadata service.

- `AmazonBedrockFullAccess`
- `AmazonDynamoDBFullAccess`
- `AmazonSNSFullAccess`
- `AmazonSESFullAccess`
- `AWSLambda_FullAccess`
- `AmazonAPIGatewayAdministrator`
- `AmazonEC2ContainerRegistryFullAccess`
- `CloudFormationFullAccess`
- `IAMFullAccess`
- `AmazonEventBridgeFullAccess`

> **Instructor talking point:** *"Notice I never ran `aws configure` and there are no
> credentials files on this machine. Everything picks up automatically from the IAM role
> I attached at launch — no long-lived credentials anywhere. In production you'd scope
> these down, but for a demo environment this is clean and safe."*

---

## Part 2 — Connect via SSH and Update the System

```bash
ssh -i /path/to/your-key.pem ec2-user@<YOUR_EC2_PUBLIC_IP>
```

Once connected, update all packages before installing anything else:

```bash
sudo dnf update -y
```

This may take 2–3 minutes. Let it complete fully before proceeding.

---

## Part 3 — Install GNOME, NICE DCV, Python 3.12, and Supporting Tools

This block installs everything in one shot. Paste it as a single block and let it run
unattended — plan for 15–20 minutes total.

```bash
# Install the official GNOME desktop group for Amazon Linux 2023
sudo dnf groupinstall "Desktop" -y && \

# Install Node.js and npm (required for AWS CDK)
sudo dnf install -y nodejs npm && \

# Install Python 3.12 alongside the system Python 3.9
# AL2023 ships with Python 3.9 which is too old for Strands Agents (requires 3.10+)
sudo dnf install -y python3.12 python3.12-pip && \

# Import the NICE DCV GPG key, download, extract, and install
sudo rpm --import https://d1uj6qtbmh3dt5.cloudfront.net/NICE-GPG-KEY && \
cd /tmp && \
curl -L -O https://d1uj6qtbmh3dt5.cloudfront.net/nice-dcv-amzn2023-$(arch).tgz && \
tar -xvzf nice-dcv-amzn2023-$(arch).tgz && \
cd nice-dcv-*-amzn2023-$(arch) && \
sudo dnf install -y ./nice-dcv-server-*.rpm ./nice-dcv-web-viewer-*.rpm ./nice-xdcv-*.rpm && \

# Enable DCV to start on boot
sudo systemctl enable dcvserver && \

# Disable GDM — not needed for virtual sessions on headless EC2 instances
# GDM crashes in a loop on headless instances because there is no physical GPU
sudo systemctl disable gdm && \
sudo systemctl set-default multi-user.target
```

---

## Part 4 — Configure Python 3.12 as the Default and Install Python Packages

```bash
# Make Python 3.12 the default python3 and pip3 for ec2-user
echo 'alias python3=python3.12' >> ~/.bashrc && \
echo 'alias pip3="python3.12 -m pip"' >> ~/.bashrc && \
source ~/.bashrc && \

# Install uv (required for Kiro's AgentCore MCP server)
python3.12 -m pip install uv --user && \
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && \
source ~/.bashrc && \

# Install all packages needed for the ISS demo
python3.12 -m pip install \
    strands-agents \
    strands-agents-tools \
    bedrock-agentcore \
    boto3 \
    aws-cdk-lib && \

# Install AWS CDK globally
sudo npm install -g aws-cdk
```

> **Why Python 3.12?** AL2023's system Python is 3.9. The Strands Agents SDK requires
> Python 3.10 or higher. Installing 3.12 alongside the system Python avoids modifying
> AL2023's managed environment while giving us a fully capable runtime for the demo.

---

## Part 5 — Configure the NICE DCV Virtual Session

Create a systemd service that automatically starts a virtual DCV session on every boot.
Virtual sessions use a dedicated virtual display (`Xdcv`) and are the correct session
type for headless EC2 instances with no physical GPU.

```bash
sudo tee /etc/systemd/system/dcv-demo-session.service > /dev/null << 'EOF'
[Unit]
Description=NICE DCV demo virtual session
After=dcvserver.service
Requires=dcvserver.service

[Service]
ExecStart=/bin/bash -c 'dcv create-session --type=virtual --owner ec2-user --name demo-session demo'
ExecStop=/bin/bash -c 'dcv close-session demo'
Restart=on-failure
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload && \
sudo systemctl enable dcv-demo-session
```

---

## Part 6 — Reboot

```bash
sudo reboot
```

Wait 60–90 seconds for the instance to come back up, then SSH in again:

```bash
ssh -i /path/to/your-key.pem ec2-user@<YOUR_EC2_PUBLIC_IP>
```

Start the DCV session service manually for this first boot (subsequent reboots will
start it automatically):

```bash
sudo systemctl start dcv-demo-session
```

---

## Part 7 — Set the ec2-user Password

NICE DCV's login screen uses Linux PAM authentication — a password is required. SSH
keys alone are not sufficient for the DCV login prompt.

```bash
sudo passwd ec2-user
```

> **Critical note:** This password is **not** preserved when an AMI is captured. Every
> time you launch a new instance from the AMI, you must SSH in and run
> `sudo passwd ec2-user` before you can connect via DCV. This is a 30-second step and
> is covered in the "Every Time You Launch" section at the end of this guide.

---

## Part 8 — Connect via NICE DCV

### Option A: Browser (no install required)

Navigate to:
```
https://<YOUR_EC2_PUBLIC_IP>:8443
```

Accept the self-signed certificate warning — this is expected on EC2. Log in with:
- **Username:** `ec2-user`
- **Password:** the password you just set in Part 7

### Option B: Native DCV Client (recommended for live demos)

Download from **[https://www.amazondcv.com/](https://www.amazondcv.com/)** and connect
to `<YOUR_EC2_PUBLIC_IP>:8443` with the same credentials.

> The native client provides better resolution scaling, clipboard sync, and smoother
> performance than the browser client — noticeably better when screen-sharing during
> a live class.

---

## Part 9 — Install Kiro

From inside the GNOME desktop, open a terminal via the Applications menu or by
right-clicking the desktop.

```bash
source ~/.bashrc && \
cd ~/Downloads && \
curl -L -O https://prod.download.desktop.kiro.dev/releases/stable/linux-x64/signed/0.12.224/tar/kiro-ide-0.12.224-stable-linux-x64.tar.gz && \
tar -xvzf kiro-ide-0.12.224-stable-linux-x64.tar.gz && \
echo 'export PATH="$HOME/Downloads/Kiro:$PATH"' >> ~/.bashrc && \
source ~/.bashrc
```

Launch Kiro:

```bash
kiro
```

Sign in with your **AWS Builder ID** when prompted. This is a one-time browser-based
OAuth login.

> **Version note:** The URL above contains the version number `0.12.224` in two places.
> Before recording your video or running this in class, visit
> **[https://kiro.dev/downloads/](https://kiro.dev/downloads/)**, click
> **Linux (Universal)**, and check the Network tab in your browser's developer tools
> (F12) to confirm the current version URL. Update both occurrences of the version
> number in the `curl` command if a newer version has been released. The extracted
> folder will always be named `Kiro` regardless of version, so the PATH line does
> not need to change.
>
> **AL2023 only:** Use the **Linux (Universal)** download — not the Debian/Ubuntu
> package. AL2023 is RPM-based and the Debian package will not install.

---

## Part 10 — Bootstrap AWS CDK

From the terminal inside the GNOME desktop (or from SSH):

```bash
cdk bootstrap
```

This deploys a small CloudFormation stack to your AWS account that CDK uses for asset
staging. It is a one-time operation per account per region and takes 1–2 minutes. By
running it now and baking it into the AMI, you avoid running it during the live demo.

---

## Part 11 — Capture the AMI

Once everything is working — GNOME desktop accessible via DCV, Kiro installed and
signed in, CDK bootstrapped — stop the instance and create an AMI:

1. In the EC2 console, select your instance
2. **Actions → Image and templates → Create image**
3. Name it something like `kiro-demo-gnome-dcv-v2`
4. Create the image

This AMI is your reusable class starting point. For each class week, launch a fresh
instance from this AMI with the demo IAM role and security group attached.

---

## Every Time You Launch a New Instance from the AMI

These two steps are required after every launch because passwords and active sessions
are not preserved in AMI snapshots:

**Step 1 — SSH in and set the password:**
```bash
ssh -i /path/to/your-key.pem ec2-user@<YOUR_EC2_PUBLIC_IP>
sudo passwd ec2-user
```

**Step 2 — Verify the DCV session is running:**
```bash
sudo dcv list-sessions
```

You should see:
```
Session: 'demo-session' (owner:ec2-user type:virtual)
```

If the session is not listed, start it manually:
```bash
sudo systemctl start dcv-demo-session
```

Then connect via DCV at `https://<YOUR_EC2_PUBLIC_IP>:8443`.

---

## Quick Troubleshooting Reference

| Symptom | Likely Cause | Fix |
|---|---|---|
| Port 8443 connection refused | Security group missing rule or DCV not running | Check security group inbound rules; SSH in and run `sudo systemctl start dcvserver` |
| DCV login — password rejected | Password not set or reset after AMI launch | SSH in and run `sudo passwd ec2-user` |
| "No session available" error | DCV session not created | SSH in and run `sudo systemctl start dcv-demo-session` |
| "Connecting…" spins forever | Session exists but display not ready | SSH in, run `sudo dcv list-sessions`, then `sudo systemctl restart dcv-demo-session` |
| GNOME session freezes or sluggish | Insufficient RAM | Upgrade to `t3.large` or `t3.xlarge` |
| `kiro` command not found | PATH not loaded in this terminal | Run `source ~/.bashrc` or open a new terminal tab |
| `uvx` command not found | PATH not loaded in this terminal | Run `source ~/.bashrc` or open a new terminal tab |
| `python3 --version` shows 3.9 | Alias not loaded | Run `source ~/.bashrc` or open a new terminal tab |
| `strands-agents` not found by pip | Using system pip3 instead of python3.12 | Use `python3.12 -m pip install` explicitly |
| AWS CLI returns credential error | IAM role not attached to instance | Stop instance, attach instance profile in EC2 console, restart |
| `cdk deploy` fails with bootstrap error | CDK not bootstrapped in this account/region | Run `cdk bootstrap` from the terminal |

---

## Cost Estimate (Approximate, us-east-1)

| Resource | Rate |
|---|---|
| `t3.large` EC2 (on-demand) | ~$0.083/hr |
| 30 GB gp3 EBS | ~$0.08/GB/month (~$2.40/month) |
| NICE DCV on EC2 | Free |
| Data transfer out | First 100 GB/month free |

**Stop** (not terminate) the instance between class days to avoid compute charges while
idle. The EBS volume incurs a small charge even when stopped. **Terminate** and clean up
after the class week ends.
