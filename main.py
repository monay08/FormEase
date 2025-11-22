from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, json, uuid

app = Flask(__name__)
app.secret_key = "formease_secret_2025"


# ---------- DATABASE ----------
def init_db():
    conn = sqlite3.connect("form.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS forms (
        id TEXT PRIMARY KEY,
        title TEXT,
        questions TEXT,
        show_score INTEGER DEFAULT 1,
        created_by INTEGER,
        FOREIGN KEY(created_by) REFERENCES users(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS responses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        form_id TEXT,
        user_id INTEGER,
        answers TEXT,
        total_score REAL,
        FOREIGN KEY(form_id) REFERENCES forms(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    conn.commit()
    conn.close()


init_db()


def get_db_connection():
    conn = sqlite3.connect("form.db")
    conn.row_factory = sqlite3.Row
    return conn


# ---------- AUTH ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        hashed_pw = generate_password_hash(password)

        conn = get_db_connection()
        try:
            conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_pw))
            conn.commit()
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Username already exists.", "danger")
        finally:
            conn.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("index"))
        else:
            flash("Invalid username or password", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))


# ---------- FORMS ----------
@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    forms = conn.execute("SELECT * FROM forms ORDER BY rowid DESC").fetchall()
    conn.close()
    return render_template("index.html", forms=forms)


@app.route("/create", methods=["GET", "POST"])
def create_form():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        title = request.form["title"]
        show_score = 1 if "show_score" in request.form else 0

        questions = []
        texts = request.form.getlist("question")
        types = request.form.getlist("type")
        options = request.form.getlist("options")
        corrects = request.form.getlist("correct")
        scores = request.form.getlist("score")

        for qtext, qtype, opts, correct, score in zip(texts, types, options, corrects, scores):
            q_opts = [o.strip() for o in opts.split(",")] if qtype in ["multiple", "checkbox"] else []
            q_correct = [c.strip() for c in correct.split(",")] if correct else []
            questions.append({
                "id": str(uuid.uuid4()),
                "question": qtext,
                "type": qtype,
                "options": q_opts,
                "correct": q_correct,
                "score": float(score) if score else 0
            })

        form_id = str(uuid.uuid4())
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO forms (id, title, questions, show_score, created_by) VALUES (?, ?, ?, ?, ?)",
            (form_id, title, json.dumps(questions), show_score, session["user_id"])
        )
        conn.commit()
        conn.close()

        flash("Form created successfully!", "success")
        return redirect(url_for("index"))

    return render_template("create_form.html")


@app.route("/form/<form_id>", methods=["GET", "POST"])
def view_form(form_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    form = conn.execute("SELECT * FROM forms WHERE id=?", (form_id,)).fetchone()
    if not form:
        conn.close()
        return "Form not found"

    # Load questions from JSON
    questions = json.loads(form["questions"])

    # Check if current user is the creator
    is_creator = form["created_by"] == session["user_id"]

    # ✅ If creator → preview mode only
    if is_creator:
        conn.close()
        return render_template("view_form.html", form=form, questions=questions, is_creator=True)

    # Prevent re-answering
    existing = conn.execute(
        "SELECT * FROM responses WHERE form_id=? AND user_id=?", (form_id, session["user_id"])
    ).fetchone()
    if existing:
        flash("You have already answered this form.", "info")
        conn.close()
        return redirect(url_for("index"))

    # Handle submission (normal user)
    if request.method == "POST":
        total_score = 0
        answers = {}

        for q in questions:
            user_ans = request.form.getlist(q["id"])
            if q["type"] == "short":
                user_ans = [user_ans[0].strip()] if user_ans else []
            answers[q["id"]] = user_ans

            # Scoring
            correct = [c.strip().lower() for c in q["correct"]]
            given = [a.strip().lower() for a in user_ans]
            score_val = q["score"]

            if q["type"] in ["multiple", "short"]:
                if given and correct and given == correct:
                    total_score += score_val
            elif q["type"] == "checkbox" and correct:
                correct_set, given_set = set(correct), set(given)
                if not given_set:
                    continue
                intersection = len(correct_set & given_set)
                incorrect = len(given_set - correct_set)
                if intersection > 0 and incorrect == 0:
                    partial = (intersection / len(correct_set)) * score_val
                    total_score += partial

        conn.execute(
            "INSERT INTO responses (form_id, user_id, answers, total_score) VALUES (?, ?, ?, ?)",
            (form_id, session["user_id"], json.dumps(answers), total_score)
        )
        conn.commit()
        conn.close()

        if form["show_score"]:
            flash(f"You scored {total_score:.2f} points!", "success")
        else:
            flash("Your response has been recorded!", "success")
        return redirect(url_for("index"))

    conn.close()
    return render_template("view_form.html", form=form, questions=questions, is_creator=False)


@app.route("/responses/<form_id>")
def view_responses(form_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    form = conn.execute("SELECT * FROM forms WHERE id=?", (form_id,)).fetchone()
    if not form:
        conn.close()
        return "Form not found"

    # Only form creator can view responses
    if form["created_by"] != session["user_id"]:
        flash("You are not allowed to view responses of this form.", "danger")
        conn.close()
        return redirect(url_for("index"))

    responses = conn.execute(
        "SELECT r.*, u.username FROM responses r JOIN users u ON r.user_id = u.id WHERE form_id=? ORDER BY r.rowid DESC",
        (form_id,)
    ).fetchall()
    conn.close()
    return render_template("view_responses.html", form=form, responses=responses)


@app.route("/responses/<form_id>/<int:response_id>")
def view_response_detail(form_id, response_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    form = conn.execute("SELECT * FROM forms WHERE id=?", (form_id,)).fetchone()
    if not form:
        conn.close()
        return "Form not found"

    # Only form creator can view this
    if form["created_by"] != session["user_id"]:
        flash("You are not allowed to view this response.", "danger")
        conn.close()
        return redirect(url_for("index"))

    # Fetch the specific response and its user
    response = conn.execute(
        "SELECT r.*, u.username FROM responses r JOIN users u ON r.user_id = u.id WHERE r.id=? AND r.form_id=?",
        (response_id, form_id)
    ).fetchone()

    if not response:
        conn.close()
        flash("Response not found.", "danger")
        return redirect(url_for("view_responses", form_id=form_id))

    # Load form questions and user's answers
    questions = json.loads(form["questions"])
    user_answers = json.loads(response["answers"])

    conn.close()
    return render_template(
        "view_response_detail.html",
        form=form,
        response=response,
        questions=questions,
        user_answers=user_answers
    )


@app.route("/delete_form/<form_id>", methods=["POST"])
def delete_form(form_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    form = conn.execute("SELECT * FROM forms WHERE id=?", (form_id,)).fetchone()
    if not form or form["created_by"] != session["user_id"]:
        flash("Unauthorized deletion.", "danger")
        conn.close()
        return redirect(url_for("index"))

    conn.execute("DELETE FROM responses WHERE form_id=?", (form_id,))
    conn.execute("DELETE FROM forms WHERE id=?", (form_id,))
    conn.commit()
    conn.close()
    flash("Form deleted successfully.", "success")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
