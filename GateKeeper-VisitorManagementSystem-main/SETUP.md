# GateKeeper – AWS Setup & Deployment Guide
## Visitor Management System | Region: ap-south-1 (Mumbai)

---

## Project Structure

```
GateKeeper/
├── app.py
├── requirements.txt
└── templates/
    ├── index.html       ← Dashboard
    └── checkin.html     ← Check-in form
```

---

## Step 1 – Create DynamoDB Table

1. Open **AWS Console → DynamoDB → Create Table**
2. Settings:
   - **Table name**: `Visitors`
   - **Partition key**: `visit_id` (type: String)
   - Leave sort key empty
3. Keep all other defaults → click **Create Table**

---

## Step 2 – Create SNS Topic & Subscribe Hosts

1. Open **AWS Console → SNS → Topics → Create Topic**
2. Settings:
   - **Type**: Standard
   - **Name**: `GateKeeperNotifications`
3. Click **Create Topic** — copy the **Topic ARN** (you'll need it in `app.py`)

### Add Email Subscriptions (one per host):
4. Click **Create Subscription**:
   - **Protocol**: Email
   - **Endpoint**: host's email address (e.g. alice@example.com)
5. Repeat for each host in `HOST_CONTACTS` dict in `app.py`
6. Each host must click the **confirmation link** in their inbox before they receive notifications

### Update app.py:
```python
SNS_TOPIC_ARN = "arn:aws:sns:ap-south-1:YOUR_ACCOUNT_ID:GateKeeperNotifications"
```

---

## Step 3 – Create an IAM Role for EC2

This lets EC2 call DynamoDB and SNS without hardcoding credentials.

1. Open **AWS Console → IAM → Roles → Create Role**
2. **Trusted entity type**: AWS Service → **EC2** → Next
3. Attach these policies:
   - `AmazonDynamoDBFullAccess`
   - `AmazonSNSFullAccess`
4. **Role name**: `GateKeeperEC2Role`
5. Click **Create Role**

---

## Step 4 – Launch an EC2 Instance

1. Open **AWS Console → EC2 → Launch Instance**
2. Settings:
   - **AMI**: Amazon Linux 2023 (free tier eligible)
   - **Instance type**: t2.micro
   - **Key pair**: Create or select one (save the .pem file)
   - **IAM instance profile**: Select `GateKeeperEC2Role`
3. **Security Group** – allow inbound:
   - Port **22** (SSH) from your IP
   - Port **5000** (Custom TCP) from `0.0.0.0/0` (or your IP for security)
4. Launch the instance

---

## Step 5 – Deploy the App on EC2

SSH into your EC2 instance:
```bash
ssh -i your-key.pem ec2-user@<EC2-PUBLIC-IP>
```

Install dependencies:
```bash
sudo yum update -y
sudo yum install python3-pip -y
```

Upload project files (run from your local machine):
```bash
scp -i your-key.pem -r ./GateKeeper ec2-user@<EC2-PUBLIC-IP>:~/
```

On EC2, install Python packages and run:
```bash
cd ~/GateKeeper
pip3 install -r requirements.txt
python3 app.py
```

Access the app in your browser:
```
http://<EC2-PUBLIC-IP>:5000
```

---

## Step 6 – (Optional) Run as a Background Service

Keep the app running after you close SSH:

```bash
nohup python3 app.py > gatekeeper.log 2>&1 &
```

Or create a systemd service for auto-restart on reboot:

```bash
sudo nano /etc/systemd/system/gatekeeper.service
```

Paste:
```ini
[Unit]
Description=GateKeeper Visitor Management
After=network.target

[Service]
User=ec2-user
WorkingDirectory=/home/ec2-user/GateKeeper
ExecStart=/usr/bin/python3 app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable gatekeeper
sudo systemctl start gatekeeper
sudo systemctl status gatekeeper
```

---

## Customising Host Contacts

Edit the `HOST_CONTACTS` dict in `app.py` to add your real hosts:

```python
HOST_CONTACTS = {
    "Alice Johnson":  "alice@yourcompany.com",
    "Bob Smith":      "bob@yourcompany.com",
    "Carol Williams": "carol@yourcompany.com",
}
```

Each name added here must also be subscribed to the SNS topic (Step 2).

---

## Quick Troubleshooting

| Issue | Fix |
|---|---|
| `NoCredentialsError` | Confirm the EC2 instance has the IAM Role attached |
| SNS notification not received | Check email subscription is confirmed in SNS console |
| DynamoDB `ResourceNotFoundException` | Ensure table name is exactly `Visitors` in `ap-south-1` |
| Port 5000 unreachable | Check EC2 Security Group allows inbound TCP on port 5000 |
| App crashes on start | Run `python3 app.py` directly and read the error output |
