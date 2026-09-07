from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
import json
import os
import threading

app = Flask(__name__)

# Educational/demo application only. Do not use for real banking.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=True,
)

# =========================
# PRINCE BANKING
# =========================

app.secret_key = os.environ.get("FLASK_SECRET_KEY", "prince-banking-demo-key")



@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data:; form-action 'self'; frame-ancestors 'none'"
    return response

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# JSON file is saved beside app.py by default.
# Optional: set BANK_DATA_FILE to use another JSON path.
DATA_FILE = os.environ.get(
    "BANK_DATA_FILE",
    os.path.join(BASE_DIR, "bank_data.json")
)

DATA_DIR = os.path.dirname(os.path.abspath(DATA_FILE))
os.makedirs(DATA_DIR, exist_ok=True)

LOCK = threading.Lock()


# =========================
# DATABASE
# =========================

def create_database():

    data = {
        "users": [
            {
                "account_no": "ADMIN001",
                "name": "Prince Banking Admin",
                "email": "admin@princebanking.com",
                "phone": "",
                "account_type": "Admin",
                "password_hash": generate_password_hash("admin123"),
                "balance": 0.0,
                "transactions": []
            }
        ]
    }

    with open(DATA_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)


def load_database():

    # Create the file only if it does not exist.
    # IMPORTANT: Never overwrite an existing database just because
    # it contains an older/legacy structure.
    if not os.path.exists(DATA_FILE):
        create_database()

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            raise ValueError("bank_data.json must contain a JSON object")

        # Keep the current Flask database structure.
        data.setdefault("users", [])

        # ---------------------------------------------------------
        # MIGRATE OLD ACC100001 / ACC100002 ... records
        # ---------------------------------------------------------
        # Your old bank_data.json used records such as:
        # "ACC100001": {"name": ..., "pin": ..., "history": ...}
        #
        # The current Flask app uses:
        # "users": [{"account_no": ..., "password_hash": ...}]
        #
        # Convert old records into the users list without deleting
        # the old records. If the account already exists in users,
        # the current users-list record is kept.
        existing_accounts = {
            str(user.get("account_no", ""))
            for user in data.get("users", [])
            if isinstance(user, dict)
        }

        migrated = False

        for key, old_user in list(data.items()):
            if not (
                isinstance(key, str)
                and key.startswith("ACC")
                and key[3:].isdigit()
                and isinstance(old_user, dict)
            ):
                continue

            account_no = key[3:]

            if account_no in existing_accounts:
                continue

            pin = str(old_user.get("pin", ""))

            transactions = []
            old_history = old_user.get("history", old_user.get("transactions", []))

            if isinstance(old_history, list):
                for item in old_history:
                    if not isinstance(item, dict):
                        continue

                    tx_type = str(item.get("type", "Transaction"))
                    amount = float(item.get("amount", 0) or 0)

                    if tx_type.lower() == "deposit":
                        title = "Cash Deposit"
                        tx_type_new = "deposit"
                        amount_text = f"+₹{amount:,.2f}"
                    elif tx_type.lower() == "withdrawal":
                        title = "Cash Withdrawal"
                        tx_type_new = "withdraw"
                        amount_text = f"-₹{amount:,.2f}"
                    elif tx_type.lower() == "account opening":
                        title = "Account Opening"
                        tx_type_new = "deposit"
                        amount_text = f"+₹{amount:,.2f}"
                    else:
                        title = tx_type
                        tx_type_new = tx_type.lower()
                        amount_text = f"₹{amount:,.2f}"

                    transactions.append({
                        "title": title,
                        "amount": amount_text,
                        "type": tx_type_new,
                        "date": str(item.get("date", ""))
                    })

            new_user = {
                "account_no": account_no,
                "name": str(old_user.get("name", "")),
                "email": str(old_user.get("email", "")),
                "phone": str(old_user.get("phone", old_user.get("mobile", ""))),
                "account_type": str(
                    old_user.get("account_type", old_user.get("type", "Savings"))
                ),
                "password_hash": (
                    generate_password_hash(pin) if pin
                    else generate_password_hash("000000")
                ),
                "balance": float(old_user.get("balance", 0) or 0),
                "transactions": transactions
            }

            data["users"].append(new_user)
            existing_accounts.add(account_no)
            migrated = True

        # ---------------------------------------------------------
        # Make sure the admin account exists.
        # ---------------------------------------------------------
        admin_exists = any(
            isinstance(user, dict)
            and user.get("account_no") == "ADMIN001"
            for user in data.get("users", [])
        )

        if not admin_exists:
            data["users"].insert(0, {
                "account_no": "ADMIN001",
                "name": "Prince Banking Admin",
                "email": "admin@princebanking.com",
                "phone": "",
                "account_type": "Admin",
                "password_hash": generate_password_hash("admin123"),
                "balance": 0.0,
                "transactions": []
            })
            migrated = True

        # Save the migration once. Existing data is preserved.
        if migrated:
            save_database(data)

        return data

    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        # Do NOT silently destroy an existing database.
        # A backup is created before rebuilding the file.
        backup_file = DATA_FILE + ".broken"

        try:
            if os.path.exists(DATA_FILE):
                import shutil
                shutil.copy2(DATA_FILE, backup_file)
        except OSError:
            pass

        create_database()

        with open(DATA_FILE, "r", encoding="utf-8") as file:
            return json.load(file)


def save_database(data):
    """Save the complete demo-bank data to bank_data.json."""
    temporary_file = DATA_FILE + ".tmp"

    try:
        with open(
            temporary_file,
            "w",
            encoding="utf-8"
        ) as file:
            json.dump(
                data,
                file,
                indent=4,
                ensure_ascii=False
            )
            file.flush()
            os.fsync(file.fileno())

        os.replace(temporary_file, DATA_FILE)
        print(f"JSON SAVED: {os.path.abspath(DATA_FILE)}")

    except Exception as error:
        try:
            if os.path.exists(temporary_file):
                os.remove(temporary_file)
        except OSError:
            pass

        print(f"JSON SAVE ERROR: {error}")
        raise


def find_user(account_no):

    database = load_database()

    for user in database.get("users", []):

        if str(user.get("account_no", "")) == str(account_no):

            return user

    return None


# =========================
# LOGIN PROTECTION
# =========================

def login_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if "account_no" not in session:

            return redirect(
                url_for("login")
            )

        return function(*args, **kwargs)

    return wrapper


def admin_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if session.get("is_admin") is not True:

            flash(
                "Admin access required.",
                "error"
            )

            return redirect(
                url_for("dashboard")
            )

        return function(*args, **kwargs)

    return wrapper


@app.route("/robots.txt")
def robots():
    return "User-agent: *\nDisallow: /\n", 200, {"Content-Type": "text/plain; charset=utf-8"}


# =========================
# HOME
# =========================

@app.route("/")
def home():

    if "account_no" in session:

        if session.get("is_admin"):

            return redirect(
                url_for("admin")
            )

        return redirect(
            url_for("dashboard")
        )

    return redirect(
        url_for("login")
    )


# =========================
# LOGIN
# =========================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        account_no = request.form.get(
            "account_no",
            ""
        ).strip().upper()

        password = request.form.get(
            "password",
            ""
        )

        user = find_user(account_no)

        if user:

            password_hash = user.get(
                "password_hash",
                ""
            )

            # Support hashed passwords
            if password_hash:

                try:

                    password_correct = check_password_hash(
                        password_hash,
                        password
                    )

                except Exception:

                    password_correct = False

            else:

                password_correct = False

            if password_correct:

                session["account_no"] = user.get(
                    "account_no"
                )

                session["is_admin"] = (
                    user.get("account_type") == "Admin"
                )

                if session["is_admin"]:

                    return redirect(
                        url_for("admin")
                    )

                return redirect(
                    url_for("dashboard")
                )

        flash(
            "Invalid account number or password.",
            "error"
        )

    return render_template(
        "login.html"
    )


# =========================
# LOGOUT
# =========================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# =========================
# REGISTER
# =========================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip()

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        account_type = request.form.get(
            "account_type",
            "Savings"
        )

        password = request.form.get(
            "password",
            ""
        )

        confirm_password = request.form.get(
            "confirm_password",
            ""
        )

        # Name validation
        if not name:

            flash(
                "Please enter your name.",
                "error"
            )

            return render_template(
                "register.html"
            )

        # Password validation
        if len(password) < 6:

            flash(
                "Password must contain at least 6 characters.",
                "error"
            )

            return render_template(
                "register.html"
            )

        if password != confirm_password:

            flash(
                "Passwords do not match.",
                "error"
            )

            return render_template(
                "register.html"
            )

        if account_type not in [
            "Savings",
            "Current"
        ]:

            account_type = "Savings"

        with LOCK:

            database = load_database()

            # Generate new account number
            numbers = []

            for user in database.get(
                "users",
                []
            ):

                account = str(
                    user.get(
                        "account_no",
                        ""
                    )
                )

                if account.isdigit():

                    numbers.append(
                        int(account)
                    )

            if numbers:

                new_account = max(
                    numbers
                ) + 1

            else:

                new_account = 100001

            new_account = str(
                new_account
            )

            new_user = {

                "account_no": new_account,

                "name": name,

                "email": email,

                "phone": phone,

                "account_type": account_type,

                "password_hash":
                    generate_password_hash(
                        password
                    ),

                "balance": 0.0,

                "transactions": []

            }

            database.setdefault(
                "users",
                []
            ).append(
                new_user
            )

            save_database(
                database
            )

        return render_template(
            "register.html",
            created_account=new_account
        )

    return render_template(
        "register.html"
    )


# =========================
# DASHBOARD
# =========================

@app.route("/dashboard")
@login_required
def dashboard():

    user = find_user(
        session["account_no"]
    )

    if not user:

        session.clear()

        return redirect(
            url_for("login")
        )

    account_type = user.get(
        "account_type",
        "Savings"
    )

    user["account_type"] = account_type

    balance = float(
        user.get(
            "balance",
            0
        )
    )

    transactions = user.get(
        "transactions",
        []
    )

    transactions = list(
        reversed(
            transactions
        )
    )

    return render_template(
        "dashboard.html",
        user=user,
        balance=balance,
        transactions=transactions[:10]
    )


# =========================
# DEPOSIT
# =========================

@app.route(
    "/deposit",
    methods=["POST"]
)
@login_required
def deposit():

    try:

        amount = float(
            request.form.get(
                "amount",
                0
            )
        )

    except (ValueError, TypeError):

        amount = 0

    if amount <= 0:

        flash(
            "Enter a valid amount.",
            "error"
        )

        return redirect(
            url_for("dashboard")
        )

    with LOCK:

        database = load_database()

        user = None

        for item in database.get(
            "users",
            []
        ):

            if str(
                item.get("account_no")
            ) == str(
                session["account_no"]
            ):

                user = item
                break

        if not user:

            flash(
                "Account not found.",
                "error"
            )

            return redirect(
                url_for("logout")
            )

        current_balance = float(
            user.get(
                "balance",
                0
            )
        )

        user["balance"] = round(
            current_balance + amount,
            2
        )

        transaction = {

            "title": "Cash Deposit",

            "amount":
                f"+₹{amount:,.2f}",

            "type": "deposit",

            "date":
                datetime.now().strftime(
                    "%d %b %Y, %I:%M %p"
                )

        }

        user.setdefault(
            "transactions",
            []
        ).append(
            transaction
        )

        save_database(
            database
        )

    flash(
        f"₹{amount:,.2f} deposited successfully.",
        "success"
    )

    return redirect(
        url_for("dashboard")
    )


# =========================
# WITHDRAW
# =========================

@app.route(
    "/withdraw",
    methods=["POST"]
)
@login_required
def withdraw():

    try:

        amount = float(
            request.form.get(
                "amount",
                0
            )
        )

    except (ValueError, TypeError):

        amount = 0

    if amount <= 0:

        flash(
            "Enter a valid amount.",
            "error"
        )

        return redirect(
            url_for("dashboard")
        )

    with LOCK:

        database = load_database()

        user = None

        for item in database.get(
            "users",
            []
        ):

            if str(
                item.get("account_no")
            ) == str(
                session["account_no"]
            ):

                user = item
                break

        if not user:

            flash(
                "Account not found.",
                "error"
            )

            return redirect(
                url_for("logout")
            )

        current_balance = float(
            user.get(
                "balance",
                0
            )
        )

        if amount > current_balance:

            flash(
                "Insufficient balance.",
                "error"
            )

            return redirect(
                url_for("dashboard")
            )

        user["balance"] = round(
            current_balance - amount,
            2
        )

        transaction = {

            "title": "Cash Withdrawal",

            "amount":
                f"-₹{amount:,.2f}",

            "type": "withdraw",

            "date":
                datetime.now().strftime(
                    "%d %b %Y, %I:%M %p"
                )

        }

        user.setdefault(
            "transactions",
            []
        ).append(
            transaction
        )

        save_database(
            database
        )

    flash(
        f"₹{amount:,.2f} withdrawn successfully.",
        "success"
    )

    return redirect(
        url_for("dashboard")
    )


# =========================
# ADMIN DASHBOARD
# =========================

@app.route("/admin")
@login_required
@admin_required
def admin():

    database = load_database()

    users = []

    total_balance = 0.0

    for user in database.get(
        "users",
        []
    ):

        if user.get(
            "account_type"
        ) != "Admin":

            users.append(
                user
            )

            total_balance += float(
                user.get(
                    "balance",
                    0
                )
            )

    return render_template(
        "admin.html",
        users=users,
        total_balance=total_balance
    )


# =========================
# DELETE CUSTOMER
# =========================

@app.route(
    "/admin/delete/<account_no>",
    methods=["POST"]
)
@login_required
@admin_required
def delete_user(account_no):

    with LOCK:

        database = load_database()

        original_users = database.get(
            "users",
            []
        )

        database["users"] = [

            user

            for user in original_users

            if not (
                str(
                    user.get(
                        "account_no",
                        ""
                    )
                ) == str(account_no)

                and

                user.get(
                    "account_type"
                ) != "Admin"
            )

        ]

        save_database(
            database
        )

    flash(
        "Customer account removed.",
        "success"
    )

    return redirect(
        url_for("admin")
    )


# =========================
# RUN SERVER
# =========================

if __name__ == "__main__":

    print("")
    print("================================")
    print("       PRINCE BANKING")
    print("================================")
    print("")

    print(
        "Database : bank_data.json"
    )

    print(
        "Admin Account : ADMIN001"
    )

    print(
        "Admin Password: admin123"
    )

    print("")

    print(
        "Open: http://127.0.0.1:5000"
    )

    print("")

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )