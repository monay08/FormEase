from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import json
import uuid

app = Flask(__name__)
app.secret_key = 'ncaf23983ry!@@#2wdskdw^&*'  # change this to something secure


# ---------- DATABASE SETUP ----------
def init_db():
    conn = sqlite3.connect('form.db')
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
                    created_by INTEGER,
                    FOREIGN KEY(created_by) REFERENCES users(id)
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS responses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    form_id TEXT,
                    answers TEXT,
                    FOREIGN KEY(form_id) REFERENCES forms(id)
                )''')
    conn.commit()
    conn.close()

init_db()


# ---------- AUTH ROUTES ----------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_pw = generate_password_hash(password)

        conn = sqlite3.connect('form.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_pw))
            conn.commit()
            flash('Registration successful! You can now log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already exists.', 'error')
        finally:
            conn.close()

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect('form.db')
        c = conn.cursor()
        c.execute("SELECT id, password FROM users WHERE username=?", (username,))
        user = c.fetchone()
        conn.close()

        # Debug: print to terminal to see if user exists
        print("User fetched:", user)

        if user and check_password_hash(user[1], password):
            session['user_id'] = user[0]
            session['username'] = username
            print("✅ Login successful for:", username)
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password.', 'error')
            print("❌ Login failed for:", username)

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('login'))


# ---------- ROUTES ----------
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('form.db')
    c = conn.cursor()
    # Show all forms (you can filter later if you want)
    c.execute("""
        SELECT id, title, created_by FROM forms
    """)
    forms = c.fetchall()
    conn.close()

    return render_template('index.html', forms=forms, username=session.get('username'))


@app.route('/create', methods=['GET', 'POST'])
def create_form():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form['title']
        questions = []

        q_texts = request.form.getlist('question')
        q_types = request.form.getlist('type')
        q_options = request.form.getlist('options')

        for text, qtype, opts in zip(q_texts, q_types, q_options):
            options = [opt.strip() for opt in opts.split(',')] if qtype in ['multiple', 'checkbox'] else []
            questions.append({'text': text, 'type': qtype, 'options': options})

        form_id = str(uuid.uuid4())

        conn = sqlite3.connect('form.db')
        c = conn.cursor()
        c.execute("INSERT INTO forms (id, title, questions, created_by) VALUES (?, ?, ?, ?)",
                  (form_id, title, json.dumps(questions), session['user_id']))
        conn.commit()
        conn.close()
        flash("Form created successfully!", "success")
        return redirect(url_for('index'))

    return render_template('create_form.html')


@app.route('/form/<form_id>', methods=['GET', 'POST'])
def view_form(form_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('form.db')
    c = conn.cursor()
    c.execute("SELECT title, questions, created_by FROM forms WHERE id=?", (form_id,))
    form = c.fetchone()
    conn.close()

    if not form:
        return "Form not found!"

    title, questions_json, created_by = form

    # Prevent creator from answering their own form
    if session['user_id'] == created_by:
        flash("You can't answer your own form!", 'error')
        return redirect(url_for('index'))

    questions = json.loads(questions_json)

    if request.method == 'POST':
        answers = {}
        for q in questions:
            if q['type'] == 'checkbox':
                answers[q['text']] = request.form.getlist(q['text'])
            else:
                answers[q['text']] = request.form.get(q['text'])

        conn = sqlite3.connect('form.db')
        c = conn.cursor()
        c.execute("INSERT INTO responses (form_id, answers) VALUES (?, ?)",
                  (form_id, json.dumps(answers)))
        conn.commit()
        conn.close()

        flash("Your response has been submitted successfully!", "success")
        return redirect(url_for('index'))

    return render_template('view_form.html', title=title, questions=questions)


@app.route('/responses/<form_id>')
def view_responses(form_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('form.db')
    c = conn.cursor()
    c.execute("SELECT title, questions, created_by FROM forms WHERE id=?", (form_id,))
    form = c.fetchone()
    c.execute("SELECT answers FROM responses WHERE form_id=?", (form_id,))
    responses = c.fetchall()
    conn.close()

    if not form:
        return "Form not found!"

    title, questions_json, created_by = form
    questions = json.loads(questions_json)
    responses = [json.loads(r[0]) for r in responses]

    # Only creator can view responses
    if session['user_id'] != created_by:
        flash("You don't have permission to view responses for this form.", "error")
        return redirect(url_for('index'))

    return render_template('responses.html', title=title, questions=questions, responses=responses)


# ---------- DELETE FORM ----------
@app.route('/delete_form/<form_id>', methods=['POST'])
def delete_form(form_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('form.db')
    c = conn.cursor()
    # Verify ownership before deleting
    c.execute("SELECT created_by FROM forms WHERE id=?", (form_id,))
    form = c.fetchone()
    if not form or form[0] != session['user_id']:
        conn.close()
        flash("You don't have permission to delete this form.", "error")
        return redirect(url_for('index'))

    # Delete all responses and then the form
    c.execute("DELETE FROM responses WHERE form_id=?", (form_id,))
    c.execute("DELETE FROM forms WHERE id=?", (form_id,))
    conn.commit()
    conn.close()
    flash("Form deleted successfully!", "success")
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True)
