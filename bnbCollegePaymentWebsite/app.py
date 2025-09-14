from flask import Flask, render_template, request, redirect, url_for, session, flash, g, send_file
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import os
import io
import random
import string
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database.db')

app = Flask(__name__)
app.secret_key = 'replace-this-with-a-secure-random-key'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    cur = db.cursor()
    # Create tables if not exist
    cur.execute("""CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            roll_no TEXT UNIQUE NOT NULL,
            course TEXT NOT NULL,
            department TEXT NOT NULL
        );""")
    cur.execute("""CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        );""")
    cur.execute("""CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            course TEXT,
            FOREIGN KEY(student_id) REFERENCES students(id)
        );""")
    # Ensure a default department account exists
    cur.execute("SELECT id FROM departments WHERE username = ?", ('deptadmin',))
    if not cur.fetchone():
        cur.execute("INSERT INTO departments (username, password) VALUES (?,?)",
                    ('deptadmin', generate_password_hash('admin123')))
    db.commit()

@app.before_request
def before_request():
    # Initialize DB on first request
    if not os.path.exists(DB_PATH):
        open(DB_PATH, 'a').close()
    init_db()

# ---------------- CAPTCHA SUPPORT ---------------- #
def generate_captcha_text(length=5):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def create_captcha_image(text):
    img = Image.new('RGB', (150, 50), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    d.text((10,10), text, font=font, fill=(0,0,0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

@app.route('/captcha')
def captcha():
    text = generate_captcha_text()
    session['captcha_text'] = text
    return send_file(create_captcha_image(text), mimetype='image/png')
# -------------------------------------------------- #

# Simple fees structure (could be moved to DB)
FEES = {
    'BSc Computer Science': 50000,
    'BCom': 40000,
    'BA': 30000,
    'BTech': 120000
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        captcha_input = request.form.get('captcha', '').strip()
        if captcha_input.lower() != session.get('captcha_text', '').lower():
            flash("Invalid captcha. Please try again.")
            return redirect(url_for('register'))

        name = request.form['name'].strip()
        email = request.form['email'].strip().lower()
        password = request.form['password']
        roll_no = request.form['roll_no'].strip()
        course = request.form['course'].strip()
        department = request.form['department'].strip()
        db = get_db()
        cur = db.cursor()
        try:
            cur.execute("INSERT INTO students (name,email,password,roll_no,course,department) VALUES (?,?,?,?,?,?)",
                        (name, email, generate_password_hash(password), roll_no, course, department))
            db.commit()
            flash('Registered successfully. Please login.')
            return redirect(url_for('login'))
        except Exception as e:
            flash('Error during registration: ' + str(e))
            return redirect(url_for('register'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        captcha_input = request.form.get('captcha', '').strip()
        if captcha_input.lower() != session.get('captcha_text', '').lower():
            flash("Invalid captcha. Please try again.")
            return redirect(url_for('login'))

        email = request.form['email'].strip().lower()
        password = request.form['password']
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT * FROM students WHERE email = ?", (email,))
        user = cur.fetchone()
        if user and check_password_hash(user['password'], password):
            session.clear()
            session['user_id'] = user['id']
            session['user_type'] = 'student'
            flash('Logged in successfully.')
            return redirect(url_for('dashboard'))
        flash('Invalid credentials.')
        return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/department/login', methods=['GET','POST'])
def department_login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT * FROM departments WHERE username = ?", (username,))
        dept = cur.fetchone()
        if dept and check_password_hash(dept['password'], password):
            session.clear()
            session['dept_id'] = dept['id']
            session['user_type'] = 'department'
            flash('Department logged in.')
            return redirect(url_for('dept_dashboard'))
        flash('Invalid department credentials.')
        return redirect(url_for('department_login'))
    return render_template('department_login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

def get_current_student():
    if session.get('user_type') == 'student' and session.get('user_id'):
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT * FROM students WHERE id = ?", (session['user_id'],))
        return cur.fetchone()
    return None

@app.route('/dashboard')
def dashboard():
    user = get_current_student()
    if not user:
        return redirect(url_for('login'))
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM payments WHERE student_id = ? ORDER BY date DESC", (user['id'],))
    payments = cur.fetchall()
    return render_template('dashboard.html', user=user, payments=payments)

@app.route('/profile')
def profile():
    user = get_current_student()
    if not user:
        return redirect(url_for('login'))
    return render_template('profile.html', user=user)

@app.route('/profile/edit', methods=['GET','POST'])
def edit_profile():
    user = get_current_student()
    if not user:
        return redirect(url_for('login'))

    if request.method == 'POST':
        captcha_input = request.form.get('captcha', '').strip()
        if captcha_input.lower() != session.get('captcha_text', '').lower():
            flash("Invalid captcha. Please try again.")
            return redirect(url_for('edit_profile'))

        name = request.form['name'].strip()
        course = request.form['course'].strip()
        department = request.form['department'].strip()
        db = get_db()
        cur = db.cursor()
        cur.execute("UPDATE students SET name=?, course=?, department=? WHERE id=?",
                    (name, course, department, user['id']))
        db.commit()
        flash('Profile updated.')
        return redirect(url_for('profile'))

    return render_template('edit_profile.html', user=user)

@app.route('/fees')
def fees():
    return render_template('fees.html', fees=FEES)

@app.route('/payment', methods=['GET','POST'])
def payment():
    user = get_current_student()
    if not user:
        return redirect(url_for('login'))
    if request.method == 'POST':
        course = request.form['course']
        amount = float(request.form['amount'])
        db = get_db()
        cur = db.cursor()
        cur.execute("INSERT INTO payments (student_id, amount, status, course) VALUES (?,?,?,?)",
                    (user['id'], amount, 'Paid', course))
        db.commit()
        payment_id = cur.lastrowid
        cur.execute("SELECT * FROM payments WHERE id=?", (payment_id,))
        payment = cur.fetchone()
        return render_template('success.html', payment=payment)
    default_amount = list(FEES.values())[0]
    return render_template('payment.html', fees=FEES, default_amount=default_amount)

@app.route('/department/dashboard')
def dept_dashboard():
    if session.get('user_type') != 'department':
        return redirect(url_for('department_login'))
    db = get_db()
    cur = db.cursor()
    cur.execute("""
    SELECT payments.id,
           payments.amount,
           payments.status,
           payments.date,
           students.name AS student_name,
           students.roll_no AS roll_no
    FROM payments
    JOIN students ON payments.student_id = students.id
    ORDER BY payments.date DESC
    """)
    payments = cur.fetchall()
    return render_template('dept_dashboard.html', payments=payments)

@app.route('/forgot_password', methods=['GET','POST'])
def forgot_password():
    if request.method == 'POST':
        captcha_input = request.form.get('captcha', '').strip()
        if captcha_input.lower() != session.get('captcha_text', '').lower():
            flash("Invalid captcha. Please try again.")
            return redirect(url_for('forgot_password'))
            
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        roll_no = request.form['roll_no'].strip()
        new_password = request.form['new_password']

        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT * FROM students WHERE email=? AND roll_no=?", (email, roll_no))
        user = cur.fetchone()
        if user:
            hashed_pw = generate_password_hash(new_password)
            cur.execute("UPDATE students SET password=? WHERE id=?", (hashed_pw, user['id']))
            db.commit()
            flash("Password reset successful. Please login with your new password.", "success")
            return redirect(url_for('login'))
        else:
            flash("No matching student found. Check your Email and Roll No.", "danger")
            return redirect(url_for('forgot_password'))
    return render_template('forgot_password.html')

if __name__ == '__main__':
    app.run(debug=True)
