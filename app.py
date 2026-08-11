import os
from datetime import datetime, date
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify
)
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "SUPABASE_URL and SUPABASE_KEY must be set in your .env file"
    )

app = Flask(__name__)
app.secret_key = SECRET_KEY

# Base (anon) client - used for auth operations (login/register)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# =========================================================
# HELPERS
# =========================================================

def get_user_client() -> Client:
    """
    Returns a Supabase client authenticated as the currently logged-in
    user, so that Row Level Security policies apply and the user can
    only read/write their own data.
    """
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    access_token = session.get("access_token")
    refresh_token = session.get("refresh_token")
    if access_token and refresh_token:
        try:
            client.auth.set_session(access_token, refresh_token)
        except Exception:
            pass
        try:
            client.postgrest.auth(access_token)
        except Exception:
            pass
    return client


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


@app.context_processor
def inject_user():
    return {"user": session.get("user"), "current_year": datetime.utcnow().year}


def to_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def compute_stats(trades):
    """Compute dashboard/analytics statistics from a list of trade dicts."""
    stats = {
        "total_trades": len(trades),
        "wins": 0,
        "losses": 0,
        "breakevens": 0,
        "win_rate": 0.0,
        "net_pnl": 0.0,
        "avg_win": 0.0,
        "avg_loss": 0.0,
        "profit_factor": 0.0,
        "best_trade": 0.0,
        "worst_trade": 0.0,
        "max_win_streak": 0,
        "max_loss_streak": 0,
    }
    if not trades:
        return stats

    win_amounts = []
    loss_amounts = []
    gross_profit = 0.0
    gross_loss = 0.0
    cur_win_streak = 0
    cur_loss_streak = 0

    sorted_trades = sorted(trades, key=lambda t: t.get("trade_date") or "")

    for t in sorted_trades:
        pnl = to_float(t.get("profit_loss"))
        stats["net_pnl"] += pnl
        result = (t.get("result") or "").lower()

        if pnl > stats["best_trade"]:
            stats["best_trade"] = pnl
        if pnl < stats["worst_trade"]:
            stats["worst_trade"] = pnl

        if result == "win" or pnl > 0:
            stats["wins"] += 1
            win_amounts.append(pnl)
            gross_profit += pnl
            cur_win_streak += 1
            cur_loss_streak = 0
        elif result == "loss" or pnl < 0:
            stats["losses"] += 1
            loss_amounts.append(pnl)
            gross_loss += abs(pnl)
            cur_loss_streak += 1
            cur_win_streak = 0
        else:
            stats["breakevens"] += 1
            cur_win_streak = 0
            cur_loss_streak = 0

        stats["max_win_streak"] = max(stats["max_win_streak"], cur_win_streak)
        stats["max_loss_streak"] = max(stats["max_loss_streak"], cur_loss_streak)

    decided = stats["wins"] + stats["losses"]
    stats["win_rate"] = round((stats["wins"] / decided) * 100, 2) if decided else 0.0
    stats["avg_win"] = round(sum(win_amounts) / len(win_amounts), 2) if win_amounts else 0.0
    stats["avg_loss"] = round(sum(loss_amounts) / len(loss_amounts), 2) if loss_amounts else 0.0
    stats["profit_factor"] = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)
    stats["net_pnl"] = round(stats["net_pnl"], 2)
    stats["best_trade"] = round(stats["best_trade"], 2)
    stats["worst_trade"] = round(stats["worst_trade"], 2)

    return stats


def build_equity_curve(trades):
    sorted_trades = sorted(trades, key=lambda t: t.get("trade_date") or "")
    labels = []
    values = []
    running = 0.0
    for t in sorted_trades:
        running += to_float(t.get("profit_loss"))
        labels.append(t.get("trade_date"))
        values.append(round(running, 2))
    return labels, values


def group_pnl_by(trades, key):
    grouped = {}
    for t in trades:
        k = t.get(key) or "Unknown"
        grouped[k] = grouped.get(k, 0.0) + to_float(t.get("profit_loss"))
    return {k: round(v, 2) for k, v in grouped.items()}


def group_pnl_by_date(trades):
    grouped = {}
    for t in trades:
        k = t.get("trade_date") or "Unknown"
        grouped[k] = grouped.get(k, 0.0) + to_float(t.get("profit_loss"))
    return dict(sorted(grouped.items()))


def fetch_trades(user_id):
    client = get_user_client()
    result = client.table("trades").select("*").eq("user_id", user_id).order("trade_date", desc=False).execute()
    return result.data or []


# =========================================================
# AUTH ROUTES
# =========================================================

@app.route("/")
def index():
    if session.get("user"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("login.html")

        try:
            response = supabase.auth.sign_in_with_password(
                {"email": email, "password": password}
            )
            if response.user and response.session:
                session["user"] = {
                    "id": response.user.id,
                    "email": response.user.email,
                }
                session["access_token"] = response.session.access_token
                session["refresh_token"] = response.session.refresh_token
                flash("Welcome back!", "success")
                return redirect(url_for("dashboard"))
            else:
                flash("Invalid email or password.", "error")
        except Exception as e:
            flash(f"Login failed: {str(e)}", "error")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        errors = []
        if not email or "@" not in email:
            errors.append("Please provide a valid email address.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long.")
        if password != confirm_password:
            errors.append("Passwords do not match.")

        if errors:
            for err in errors:
                flash(err, "error")
            return render_template("register.html")

        try:
            response = supabase.auth.sign_up(
                {"email": email, "password": password}
            )
            if response.user:
                flash("Account created successfully! Please log in.", "success")
                return redirect(url_for("login"))
            else:
                flash("Registration failed. Please try again.", "error")
        except Exception as e:
            flash(f"Registration failed: {str(e)}", "error")

    return render_template("register.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        if not email:
            flash("Please enter your email address.", "error")
            return render_template("forgot_password.html")
        try:
            supabase.auth.reset_password_for_email(email)
        except Exception:
            pass
        flash("If an account exists for that email, a reset link has been sent.", "success")
        return redirect(url_for("login"))
    return render_template("forgot_password.html")


@app.route("/logout")
def logout():
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
@login_required
def dashboard():
    user_id = session["user"]["id"]
    try:
        trades = fetch_trades(user_id)
    except Exception as e:
        flash(f"Could not load trades: {str(e)}", "error")
        trades = []

    stats = compute_stats(trades)
    equity_labels, equity_values = build_equity_curve(trades)
    pnl_by_day = group_pnl_by_date(trades)
    wins_losses = {"Wins": stats["wins"], "Losses": stats["losses"], "Breakeven": stats["breakevens"]}

    recent_trades = list(reversed(trades))[:10]

    return render_template(
        "dashboard.html",
        stats=stats,
        recent_trades=recent_trades,
        equity_labels=equity_labels,
        equity_values=equity_values,
        pnl_by_day=pnl_by_day,
        wins_losses=wins_losses,
    )


# =========================================================
# ADD TRADE
# =========================================================

@app.route("/add-trade", methods=["GET", "POST"])
@login_required
def add_trade():
    if request.method == "POST":
        user_id = session["user"]["id"]

        trade_data = {
            "user_id": user_id,
            "trade_date": request.form.get("trade_date"),
            "symbol": request.form.get("symbol", "").upper().strip(),
            "direction": request.form.get("direction"),
            "entry_price": to_float(request.form.get("entry_price")),
            "exit_price": to_float(request.form.get("exit_price"), None),
            "stop_loss": to_float(request.form.get("stop_loss"), None),
            "take_profit": to_float(request.form.get("take_profit"), None),
            "lot_size": to_float(request.form.get("lot_size"), None),
            "risk_percent": to_float(request.form.get("risk_percent"), None),
            "profit_loss": to_float(request.form.get("profit_loss")),
            "strategy": request.form.get("strategy"),
            "session": request.form.get("session"),
            "timeframe": request.form.get("timeframe"),
            "market_condition": request.form.get("market_condition"),
            "result": request.form.get("result"),
            "notes": request.form.get("notes"),
            "mistakes": request.form.get("mistakes"),
            "emotions": request.form.get("emotions"),
            "screenshot_url": request.form.get("screenshot_url"),
        }

        if not trade_data["trade_date"] or not trade_data["symbol"] or not trade_data["direction"]:
            flash("Trade date, symbol, and direction are required.", "error")
            return render_template("add_trade.html", form_data=request.form)

        try:
            client = get_user_client()
            client.table("trades").insert(trade_data).execute()
            flash("Trade saved successfully.", "success")
            return redirect(url_for("dashboard"))
        except Exception as e:
            flash(f"Could not save trade: {str(e)}", "error")
            return render_template("add_trade.html", form_data=request.form)

    return render_template("add_trade.html", form_data={})


# =========================================================
# TRADE HISTORY
# =========================================================

@app.route("/trades")
@login_required
def trades():
    user_id = session["user"]["id"]
    try:
        all_trades = fetch_trades(user_id)
    except Exception as e:
        flash(f"Could not load trades: {str(e)}", "error")
        all_trades = []

    symbol_filter = request.args.get("symbol", "").strip().upper()
    result_filter = request.args.get("result", "")
    direction_filter = request.args.get("direction", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    search_query = request.args.get("q", "").strip().lower()
    sort_order = request.args.get("sort", "desc")

    filtered = all_trades
    if symbol_filter:
        filtered = [t for t in filtered if (t.get("symbol") or "").upper() == symbol_filter]
    if result_filter:
        filtered = [t for t in filtered if (t.get("result") or "") == result_filter]
    if direction_filter:
        filtered = [t for t in filtered if (t.get("direction") or "") == direction_filter]
    if date_from:
        filtered = [t for t in filtered if (t.get("trade_date") or "") >= date_from]
    if date_to:
        filtered = [t for t in filtered if (t.get("trade_date") or "") <= date_to]
    if search_query:
        filtered = [
            t for t in filtered
            if search_query in (t.get("symbol") or "").lower()
            or search_query in (t.get("strategy") or "").lower()
            or search_query in (t.get("notes") or "").lower()
        ]

    filtered = sorted(filtered, key=lambda t: t.get("trade_date") or "", reverse=(sort_order == "desc"))

    symbols = sorted({t.get("symbol") for t in all_trades if t.get("symbol")})

    return render_template(
        "trades.html",
        trades=filtered,
        symbols=symbols,
        filters={
            "symbol": symbol_filter,
            "result": result_filter,
            "direction": direction_filter,
            "date_from": date_from,
            "date_to": date_to,
            "q": request.args.get("q", ""),
            "sort": sort_order,
        },
    )


@app.route("/trade/<trade_id>")
@login_required
def view_trade(trade_id):
    user_id = session["user"]["id"]
    client = get_user_client()
    result = client.table("trades").select("*").eq("id", trade_id).eq("user_id", user_id).execute()
    if not result.data:
        flash("Trade not found.", "error")
        return redirect(url_for("trades"))
    return render_template("view_trade.html", trade=result.data[0])


@app.route("/trade/<trade_id>/edit", methods=["GET", "POST"])
@login_required
def edit_trade(trade_id):
    user_id = session["user"]["id"]
    client = get_user_client()

    if request.method == "POST":
        trade_data = {
            "trade_date": request.form.get("trade_date"),
            "symbol": request.form.get("symbol", "").upper().strip(),
            "direction": request.form.get("direction"),
            "entry_price": to_float(request.form.get("entry_price")),
            "exit_price": to_float(request.form.get("exit_price"), None),
            "stop_loss": to_float(request.form.get("stop_loss"), None),
            "take_profit": to_float(request.form.get("take_profit"), None),
            "lot_size": to_float(request.form.get("lot_size"), None),
            "risk_percent": to_float(request.form.get("risk_percent"), None),
            "profit_loss": to_float(request.form.get("profit_loss")),
            "strategy": request.form.get("strategy"),
            "session": request.form.get("session"),
            "timeframe": request.form.get("timeframe"),
            "market_condition": request.form.get("market_condition"),
            "result": request.form.get("result"),
            "notes": request.form.get("notes"),
            "mistakes": request.form.get("mistakes"),
            "emotions": request.form.get("emotions"),
            "screenshot_url": request.form.get("screenshot_url"),
        }
        try:
            client.table("trades").update(trade_data).eq("id", trade_id).eq("user_id", user_id).execute()
            flash("Trade updated successfully.", "success")
            return redirect(url_for("trades"))
        except Exception as e:
            flash(f"Could not update trade: {str(e)}", "error")

    result = client.table("trades").select("*").eq("id", trade_id).eq("user_id", user_id).execute()
    if not result.data:
        flash("Trade not found.", "error")
        return redirect(url_for("trades"))

    return render_template("edit_trade.html", trade=result.data[0])


@app.route("/trade/<trade_id>/delete", methods=["POST"])
@login_required
def delete_trade(trade_id):
    user_id = session["user"]["id"]
    try:
        client = get_user_client()
        client.table("trades").delete().eq("id", trade_id).eq("user_id", user_id).execute()
        flash("Trade deleted.", "success")
    except Exception as e:
        flash(f"Could not delete trade: {str(e)}", "error")
    return redirect(url_for("trades"))


# =========================================================
# ANALYTICS
# =========================================================

@app.route("/analytics")
@login_required
def analytics():
    user_id = session["user"]["id"]
    try:
        all_trades = fetch_trades(user_id)
    except Exception as e:
        flash(f"Could not load trades: {str(e)}", "error")
        all_trades = []

    stats = compute_stats(all_trades)
    equity_labels, equity_values = build_equity_curve(all_trades)
    daily_pnl = group_pnl_by_date(all_trades)
    pnl_by_symbol = group_pnl_by(all_trades, "symbol")
    pnl_by_strategy = group_pnl_by(all_trades, "strategy")
    pnl_by_session = group_pnl_by(all_trades, "session")
    wins_losses = {"Wins": stats["wins"], "Losses": stats["losses"], "Breakeven": stats["breakevens"]}

    # Weekly / monthly aggregation
    weekly = {}
    monthly = {}
    for t in all_trades:
        d = t.get("trade_date")
        if not d:
            continue
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
        except ValueError:
            continue
        week_key = f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"
        month_key = dt.strftime("%Y-%m")
        pnl = to_float(t.get("profit_loss"))
        weekly[week_key] = weekly.get(week_key, 0.0) + pnl
        monthly[month_key] = monthly.get(month_key, 0.0) + pnl

    weekly = dict(sorted(weekly.items()))
    monthly = dict(sorted(monthly.items()))

    return render_template(
        "analytics.html",
        stats=stats,
        equity_labels=equity_labels,
        equity_values=equity_values,
        daily_pnl=daily_pnl,
        weekly_pnl=weekly,
        monthly_pnl=monthly,
        pnl_by_symbol=pnl_by_symbol,
        pnl_by_strategy=pnl_by_strategy,
        pnl_by_session=pnl_by_session,
        wins_losses=wins_losses,
    )


# =========================================================
# CALENDAR
# =========================================================

@app.route("/calendar")
@login_required
def calendar():
    user_id = session["user"]["id"]
    try:
        all_trades = fetch_trades(user_id)
    except Exception as e:
        flash(f"Could not load trades: {str(e)}", "error")
        all_trades = []

    by_date = {}
    for t in all_trades:
        d = t.get("trade_date")
        if not d:
            continue
        entry = by_date.setdefault(d, {"pnl": 0.0, "count": 0, "trades": []})
        entry["pnl"] += to_float(t.get("profit_loss"))
        entry["count"] += 1
        entry["trades"].append(t)

    for d in by_date:
        by_date[d]["pnl"] = round(by_date[d]["pnl"], 2)

    return render_template("calendar.html", calendar_data=by_date)


# =========================================================
# SETTINGS
# =========================================================

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    user_id = session["user"]["id"]
    client = get_user_client()

    if request.method == "POST":
        profile_data = {
            "default_currency": request.form.get("default_currency"),
            "default_platform": request.form.get("default_platform"),
            "default_timezone": request.form.get("default_timezone"),
            "default_risk_percent": to_float(request.form.get("default_risk_percent")),
            "theme": request.form.get("theme", "dark"),
        }
        try:
            client.table("profiles").update(profile_data).eq("id", user_id).execute()
            flash("Settings saved.", "success")
        except Exception as e:
            flash(f"Could not save settings: {str(e)}", "error")
        return redirect(url_for("settings"))

    try:
        result = client.table("profiles").select("*").eq("id", user_id).execute()
        profile = result.data[0] if result.data else {}
    except Exception:
        profile = {}

    return render_template("settings.html", profile=profile)


# =========================================================
# PROFILE
# =========================================================

@app.route("/profile")
@login_required
def profile():
    user_id = session["user"]["id"]
    client = get_user_client()

    try:
        profile_result = client.table("profiles").select("*").eq("id", user_id).execute()
        profile_data = profile_result.data[0] if profile_result.data else {}
    except Exception:
        profile_data = {}

    try:
        all_trades = fetch_trades(user_id)
    except Exception:
        all_trades = []

    stats = compute_stats(all_trades)

    return render_template("profile.html", profile=profile_data, stats=stats)


# =========================================================
# SECURITY
# =========================================================

@app.route("/security", methods=["GET", "POST"])
@login_required
def security():
    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(new_password) < 8:
            flash("New password must be at least 8 characters long.", "error")
            return redirect(url_for("security"))

        if new_password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("security"))

        try:
            client = get_user_client()
            client.auth.update_user({"password": new_password})
            flash("Password updated successfully.", "success")
        except Exception as e:
            flash(f"Could not update password: {str(e)}", "error")

        return redirect(url_for("security"))

    return render_template("security.html")


# =========================================================
# ERROR HANDLERS
# =========================================================

@app.errorhandler(404)
def not_found_error(error):
    return render_template("error.html", code=404, message="Page not found."), 404


@app.errorhandler(500)
def internal_error(error):
    return render_template("error.html", code=500, message="Something went wrong on our end."), 500


if __name__ == "__main__":
    app.run(debug=True)
