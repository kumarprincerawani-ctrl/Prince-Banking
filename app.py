from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
import json
import os
import threading

app = Flask(__name__)

# =========================
# PRINCE BANKING
# =========================

app.secret_key = "prince-banking-demo-key"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "bank_data.json")

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
    if not os.path.exists(DATA_FILE):
        create_database()

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            create_database()

            with open(DATA_FILE, "r", encoding="utf-8") as file:
                data = json.load(file)

        data.setdefault("users", [])

        return data

    except Exception:
        create_database()

        with open(DATA_FILE, "r", encoding="utf-8") as file:
            return json.load(file)


def save_database(data):
    temporary_file = DATA_FILE + ".tmp"

    with open(temporary_file, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)

    os.replace(temporary_file, DATA_FILE)


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
            return redirect(url_for("login"))

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

            return redirect(url_for("dashboard"))

        return function(*args, **kwargs)

    return wrapper


# =========================
# HOME
# =========================

@app.route("/")
def home():

    if "account_no" in session:

        if session.get("is_admin"):
            return redirect(url_for("admin"))

        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))


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

    return render_template("login.html")


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

                new_account = max(numbers) + 1

            else:

                new_account = 100001

            new_account = str(new_account)

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
            ).append(new_user)

            save_database(database)

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
        reversed(transactions)
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
        ).append(transaction)

        save_database(database)

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
        ).append(transaction)

        save_database(database)

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

            users.append(user)

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

        save_database(database)

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
