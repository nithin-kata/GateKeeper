"""
GateKeeper: Visitor Management System
Flask + DynamoDB + SNS on AWS EC2 (ap-south-1)

Author: GateKeeper Team
Region: ap-south-1

SETUP NOTES:
  - DynamoDB table: "Visitors" with partition key "visit_id" (String)
  - DynamoDB table: "User" with partition key "user_id" (String)
  - SNS topic: Create one and copy the ARN into SNS_TOPIC_ARN below
  - EC2 IAM Role must have: AmazonDynamoDBFullAccess, AmazonSNSFullAccess
  - No AWS credentials are hardcoded; IAM Role handles auth automatically
"""

import uuid
from datetime import datetime
from functools import wraps

import boto3
from boto3.dynamodb.conditions import Key
from flask import Flask, redirect, render_template, request, session, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash

from dotenv import load_dotenv
import os

load_dotenv()

AWS_ACCESS_KEY_ID = os.getenv("AKIAVDHC7ACWKNYF5QGA")

# ── App Setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = "gatekeeper-secret-key-change-in-production-2024"

AWS_REGION = "ap-south-1"

# ── SNS Configuration ─────────────────────────────────────────────────────────
# STEP 1: Create an SNS Topic in the AWS Console (ap-south-1)
# STEP 2: Subscribe the host's email to the topic
# STEP 3: Paste the Topic ARN below
SNS_TOPIC_ARN = "arn:aws:sns:ap-south-1:350515822764:GateKeeperNotifications"

# Static mapping of host names → email addresses
# In production, store this in DynamoDB or a config file
HOST_CONTACTS = {
    "Nithin Kata":  "nithinkata2903@gmail.com",
    "Sai Vignesh":  "tv110598584@gmail.com",
}

# ── AWS Clients (uses IAM Role on EC2, no hardcoded credentials) ───────────────
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
sns      = boto3.client("sns",      region_name=AWS_REGION)
table    = dynamodb.Table("Visitors")
user_table = dynamodb.Table("User")


# ── Auth Decorator ────────────────────────────────────────────────────────────
def login_required(f):
    """Redirect to login page if user is not authenticated."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session:
            flash("Please log in to access that page.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


# ── Helper: Send SNS email notification to host ───────────────────────────────
def notify_host(visitor_name: str, host_name: str, purpose: str, visit_id: str):
    """Publish a visitor-arrival message to the SNS topic."""
    host_email = HOST_CONTACTS.get(host_name, "unknown")
    message = (
        f"Hello {host_name},\n\n"
        f"A visitor has arrived to meet you.\n\n"
        f"  Visitor Name : {visitor_name}\n"
        f"  Purpose      : {purpose}\n"
        f"  Visit ID     : {visit_id}\n"
        f"  Time         : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"Please come to the reception. Thank you!\n\n"
        f"-- GateKeeper System"
    )
    try:
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=f"[GateKeeper] Visitor arrived for {host_name}",
            Message=message,
        )
    except Exception as e:
        # Log the error but don't crash the app
        print(f"[SNS ERROR] Could not send notification: {e}")


# ── Route: Landing Page ───────────────────────────────────────────────────────
@app.route("/")
def landing():
    """Public landing page introducing GateKeeper."""
    if "user" in session:
        return redirect(url_for("dashboard"))
    return render_template("landing.html")


# ── Route: Sign Up ────────────────────────────────────────────────────────────
@app.route("/signup", methods=["GET", "POST"])
def signup():
    """Create a new user account."""
    if "user" in session:
        return redirect(url_for("dashboard"))

    if request.method == "GET":
        return render_template("signup.html")

    # ── POST: Validate and create user ────────────────────────────────────────
    name     = request.form.get("name", "").strip()
    email    = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "").strip()
    confirm  = request.form.get("confirm_password", "").strip()

    errors = []
    if not name:
        errors.append("Full name is required.")
    if not email:
        errors.append("Email is required.")
    if not password:
        errors.append("Password is required.")
    elif len(password) < 6:
        errors.append("Password must be at least 6 characters.")
    if password != confirm:
        errors.append("Passwords do not match.")

    if errors:
        return render_template("signup.html", errors=errors, form_data=request.form)

    # Check if email already exists (scan for email match)
    try:
        response = user_table.scan(
            FilterExpression="email = :e",
            ExpressionAttributeValues={":e": email},
        )
        if response.get("Items"):
            errors.append("An account with this email already exists.")
            return render_template("signup.html", errors=errors, form_data=request.form)
    except Exception as e:
        print(f"[DB ERROR] Could not check user: {e}")
        errors.append("Database error. Please try again.")
        return render_template("signup.html", errors=errors, form_data=request.form)

    # Create user record
    user_id = str(uuid.uuid4())
    hashed_password = generate_password_hash(password)
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    user_item = {
        "user_id":    user_id,
        "name":       name,
        "email":      email,
        "password":   hashed_password,
        "created_at": created_at,
    }

    try:
        user_table.put_item(Item=user_item)
    except Exception as e:
        print(f"[DB ERROR] Could not create user: {e}")
        errors.append("Could not create account. Please try again.")
        return render_template("signup.html", errors=errors, form_data=request.form)

    flash("Account created successfully! Please log in.", "success")
    return redirect(url_for("login"))


# ── Route: Login ──────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    """Authenticate an existing user."""
    if "user" in session:
        return redirect(url_for("dashboard"))

    if request.method == "GET":
        return render_template("login.html")

    # ── POST: Validate credentials ────────────────────────────────────────────
    email    = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "").strip()

    errors = []
    if not email:
        errors.append("Email is required.")
    if not password:
        errors.append("Password is required.")

    if errors:
        return render_template("login.html", errors=errors, form_data=request.form)

    # Look up user by email
    try:
        response = user_table.scan(
            FilterExpression="email = :e",
            ExpressionAttributeValues={":e": email},
        )
        users = response.get("Items", [])
    except Exception as e:
        print(f"[DB ERROR] Could not look up user: {e}")
        errors.append("Database error. Please try again.")
        return render_template("login.html", errors=errors, form_data=request.form)

    if not users:
        errors.append("Invalid email or password.")
        return render_template("login.html", errors=errors, form_data=request.form)

    user = users[0]

    # Verify password
    if not check_password_hash(user["password"], password):
        errors.append("Invalid email or password.")
        return render_template("login.html", errors=errors, form_data=request.form)

    # Set session
    session["user"] = {
        "user_id": user["user_id"],
        "name":    user["name"],
        "email":   user["email"],
    }

    flash(f"Welcome back, {user['name']}!", "success")
    return redirect(url_for("dashboard"))


# ── Route: Logout ─────────────────────────────────────────────────────────────
@app.route("/logout")
def logout():
    """Clear the session and redirect to landing page."""
    session.pop("user", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("landing"))


# ── Route: Dashboard (list all visitors, newest first) ────────────────────────
@app.route("/dashboard")
@login_required
def dashboard():
    """Scan all visitor records from DynamoDB and display them."""
    try:
        response = table.scan()
        visitors = response.get("Items", [])

        # Sort by check_in_time descending (newest first)
        visitors.sort(key=lambda v: v.get("check_in_time", ""), reverse=True)
    except Exception as e:
        print(f"[DB ERROR] Could not fetch visitors: {e}")
        visitors = []

    return render_template(
        "index.html",
        visitors=visitors,
        hosts=list(HOST_CONTACTS.keys()),
        user=session.get("user"),
    )


# ── Route: Check-in Form (GET) and Submission (POST) ──────────────────────────
@app.route("/checkin", methods=["GET", "POST"])
@login_required
def checkin():
    """Show the check-in form (GET) or process a new visitor (POST)."""
    if request.method == "GET":
        return render_template("checkin.html", hosts=list(HOST_CONTACTS.keys()), user=session.get("user"))

    # ── POST: Validate and store visitor ──────────────────────────────────────
    name      = request.form.get("name", "").strip()
    phone     = request.form.get("phone", "").strip()
    host_name = request.form.get("host_name", "").strip()
    purpose   = request.form.get("purpose", "").strip()

    # Basic validation: no empty fields
    errors = []
    if not name:
        errors.append("Visitor name is required.")
    if not phone:
        errors.append("Phone number is required.")
    if not host_name:
        errors.append("Host name is required.")
    if not purpose:
        errors.append("Purpose of visit is required.")

    if errors:
        return render_template(
            "checkin.html",
            hosts=list(HOST_CONTACTS.keys()),
            errors=errors,
            form_data=request.form,
            user=session.get("user"),
        )

    # Build the visitor record
    visit_id      = str(uuid.uuid4())        # Unique ID for each visit
    check_in_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    host_contact  = HOST_CONTACTS.get(host_name, "N/A")

    item = {
        "visit_id":      visit_id,
        "name":          name,
        "phone":         phone,
        "host_name":     host_name,
        "host_contact":  host_contact,
        "purpose":       purpose,
        "check_in_time": check_in_time,
        "check_out_time": "",   # Empty until checkout
        "status":        "IN",
    }

    try:
        table.put_item(Item=item)
    except Exception as e:
        print(f"[DB ERROR] Could not save visitor: {e}")
        return render_template(
            "checkin.html",
            hosts=list(HOST_CONTACTS.keys()),
            errors=["Database error. Please try again."],
            user=session.get("user"),
        )

    # Send SNS notification to the host
    notify_host(name, host_name, purpose, visit_id)

    return redirect(url_for("dashboard"))


# ── Route: Checkout ────────────────────────────────────────────────────────────
@app.route("/checkout/<visit_id>")
@login_required
def checkout(visit_id: str):
    """Mark a visitor as OUT and record the checkout time."""
    check_out_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        table.update_item(
            Key={"visit_id": visit_id},
            UpdateExpression="SET #s = :status, check_out_time = :cout",
            ExpressionAttributeNames={"#s": "status"},   # 'status' is a reserved word
            ExpressionAttributeValues={
                ":status": "OUT",
                ":cout":   check_out_time,
            },
        )
    except Exception as e:
        print(f"[DB ERROR] Could not update visitor status: {e}")

    return redirect(url_for("dashboard"))


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Run on all interfaces so EC2 security group can reach it
    # In production, use Gunicorn or Nginx instead of Flask dev server
    app.run(host="0.0.0.0", port=5000, debug=False)
