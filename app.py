from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin,
    login_user, logout_user,
    login_required, current_user
)
from flask_bcrypt import Bcrypt
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import os, json, re
from datetime import datetime
from dotenv import load_dotenv

# ✅ RULE ENGINE
from rule_based_analyzer import analyze_ingredients

# ---------------- CONFIG ----------------
load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")

os.makedirs(INSTANCE_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(INSTANCE_DIR, 'nutriguard.db')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = UPLOAD_DIR

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
    default_limits=["200 per day", "50 per hour"]
)
limiter.init_app(app)

# ---------------- MODELS ----------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

    age = db.Column(db.Integer)
    gender = db.Column(db.String(20))

    dietary_preferences = db.Column(db.Text, default="[]")
    allergies = db.Column(db.Text, default="[]")
    medical_conditions = db.Column(db.Text, default="[]")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Analysis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    product_name = db.Column(db.String(200))
    ingredients_text = db.Column(db.Text)

    safety_score = db.Column(db.Integer)
    traffic_light = db.Column(db.String(20))
    analysis_result = db.Column(db.Text)
    input_method = db.Column(db.String(20))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ---------------- HELPERS ----------------
def extract_text_from_image(_path):
    # OCR disabled safely for Render
    return ""


def clean_ingredients(text):
    text = re.sub(r"[^\w\s,]", "", text)
    return [i.strip() for i in text.split(",") if i.strip()]


# ---------------- ROUTES ----------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        user = User(
            username=request.form["username"],
            email=request.form["email"],
            password=bcrypt.generate_password_hash(
                request.form["password"]
            ).decode("utf-8")
        )
        db.session.add(user)
        db.session.commit()
        return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form["email"]).first()
        if user and bcrypt.check_password_hash(
            user.password, request.form["password"]
        ):
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Invalid credentials", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    total_analyses = Analysis.query.filter_by(
        user_id=current_user.id
    ).count()

    recent_analyses = Analysis.query.filter_by(
        user_id=current_user.id
    ).order_by(Analysis.created_at.desc()).limit(5).all()

    profile_complete = all([
        current_user.age,
        current_user.gender,
        json.loads(current_user.dietary_preferences or "[]"),
        json.loads(current_user.allergies or "[]"),
        json.loads(current_user.medical_conditions or "[]")
    ])

    return render_template(
        "dashboard.html",
        analyses=recent_analyses,
        total_analyses=total_analyses,
        profile_complete=profile_complete
    )



@app.route("/history")
@login_required
def history():
    analyses = Analysis.query.filter_by(
        user_id=current_user.id
    ).order_by(Analysis.created_at.desc()).all()

    return render_template("history.html", analyses=analyses)


# ---------------- PROFILE (✅ FIXED) ----------------
@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        current_user.age = request.form.get("age", type=int)
        current_user.gender = request.form.get("gender")

        current_user.dietary_preferences = json.dumps(
            request.form.getlist("dietary_preferences")
        )

        current_user.allergies = json.dumps(
            [a.strip().lower() for a in request.form.get("allergies", "").split(",") if a.strip()]
        )

        current_user.medical_conditions = json.dumps(
            [m.strip().lower() for m in request.form.get("medical_conditions", "").split(",") if m.strip()]
        )

        db.session.commit()
        flash("Profile updated successfully", "success")
        return redirect(url_for("profile"))

    # ✅ THIS WAS MISSING BEFORE
    dietary_prefs = json.loads(current_user.dietary_preferences or "[]")
    allergies = ", ".join(json.loads(current_user.allergies or "[]"))
    medical_conditions = ", ".join(json.loads(current_user.medical_conditions or "[]"))

    return render_template(
        "profile.html",
        dietary_prefs=dietary_prefs,
        allergies=allergies,
        medical_conditions=medical_conditions
    )


@app.route("/analyze", methods=["GET", "POST"])
@login_required
@limiter.limit("10 per minute")
def analyze():
    if request.method == "POST":
        ingredients_text = request.form.get("ingredients_text", "")
        ingredients = clean_ingredients(ingredients_text)

        result = analyze_ingredients(ingredients)
        result["ingredients"] = ingredients

        analysis = Analysis(
            user_id=current_user.id,
            product_name=request.form.get("product_name", "Unnamed Product"),
            ingredients_text=ingredients_text,
            safety_score=result["safety_score"],
            traffic_light=result["traffic_light"],
            analysis_result=json.dumps(result),
            input_method="text"
        )

        db.session.add(analysis)
        db.session.commit()

        return redirect(url_for("result", analysis_id=analysis.id))

    return render_template("analyze.html")


@app.route("/result/<int:analysis_id>")
@login_required
def result(analysis_id):
    analysis = Analysis.query.get_or_404(analysis_id)
    data = json.loads(analysis.analysis_result)
    return render_template("result.html", analysis=analysis, data=data)


# ---------------- INIT DB ----------------
with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True)
