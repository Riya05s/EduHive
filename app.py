from flask import Flask, render_template, request, redirect, session
import sqlite3

app = Flask(__name__)
app.secret_key = "secret123"


# -----------------------------
# DATABASE CONNECTION
# -----------------------------
def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row   # allows column names
    return conn

# -----------------------------
# INITIALIZE DATABASE
# -----------------------------
def init_db():
    db = get_db()

    db.execute("""
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        section TEXT
    )
    """)

    # UPDATED admins table to include section
    db.execute("""
    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        section TEXT
    )
    """)

    db.execute("""
    CREATE TABLE IF NOT EXISTS courses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        course_name TEXT,
        duration INTEGER,
        domain TEXT,
        platform TEXT,
        status TEXT,
        reason TEXT,
        marks INTEGER DEFAULT 0,
        FOREIGN KEY(student_id) REFERENCES students(id)
)
""")

    db.execute("""
    CREATE TABLE IF NOT EXISTS weekly_updates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id INTEGER,
        week_number INTEGER,
        progress TEXT,
        FOREIGN KEY(course_id) REFERENCES courses(id)
)
""")

    db.execute("""
    CREATE TABLE IF NOT EXISTS session_control (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        is_active INTEGER,
        deadline TEXT,
        domain TEXT,
        min_duration INTEGER,
        platforms TEXT,
        section TEXT UNIQUE -- Added section column to track per-section sessions
)
""")

    db.execute("""
    CREATE TABLE IF NOT EXISTS coordinators (
        section TEXT PRIMARY KEY,
        coordinator_name TEXT
)
""")

    db.commit()
    db.close()


@app.route('/')
def home():
    return render_template('index.html')

#-----------------------
# START SESSION
#----------------------
@app.route('/start_session', methods=['POST'])
def start_session():
    if 'admin_id' not in session:
        return redirect('/admin')

    # Get the specific section from the admin's session
    admin_section = session.get('admin_section') 
    deadline = request.form.get('deadline')
    domain = request.form.get('domain')
    min_duration = request.form.get('min_duration')
    platforms = request.form.getlist('platforms')
    platforms_str = ",".join(platforms)

    db = get_db()
    
    # Check if a session control row exists for THIS specific section
    session_exists = db.execute("SELECT id FROM session_control WHERE section = ?", (admin_section,)).fetchone()

    if session_exists:
        # Update only the row belonging to this admin's section
        db.execute("""
            UPDATE session_control 
            SET is_active = 1, deadline = ?, domain = ?, min_duration = ?, platforms = ?
            WHERE section = ?
        """, (deadline, domain, min_duration, platforms_str, admin_section))
    else:
        # Create a new session entry for this section
        db.execute("""
            INSERT OR REPLACE INTO session_control 
            (is_active, deadline, domain, min_duration, platforms, section)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (1, deadline, domain, min_duration, platforms_str, admin_section))

    db.commit()
    db.close()
    return redirect('/admin_dashboard')

# -----------------------------
# STUDENT PROFILE
# -----------------------------
@app.route('/student_profile', methods=['GET', 'POST'])
def student_profile():
    if 'student_id' not in session:
        return redirect('/student_login')

    db = get_db()
    student_id = session['student_id']
    success_msg = None

    if request.method == 'POST':
        # Grab updated data from the form
        name = request.form.get('name')
        email = request.form.get('email')
        section = request.form.get('section')
        roll_number = request.form.get('roll_number')
        branch = request.form.get('branch')

        # Update the student record
        try:
            db.execute("""
                UPDATE students 
                SET name=?, email=?, section=?, roll_number=?, branch=? 
                WHERE id=?
            """, (name, email, section, roll_number, branch, student_id))
            db.commit()
            success_msg = "Profile updated successfully!"
        except sqlite3.IntegrityError:
            success_msg = "Error: Email might already be in use."

    # Fetch current student data to pre-fill the form
    student = db.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()

    # Advanced Feature: Calculate Performance Stats for the student
    total_courses = db.execute("SELECT COUNT(*) FROM courses WHERE student_id=?", (student_id,)).fetchone()[0]
    approved_courses = db.execute("SELECT COUNT(*) FROM courses WHERE student_id=? AND status='Approved'", (student_id,)).fetchone()[0]
    
    # Calculate total marks (handle None if no marks exist)
    total_marks_query = db.execute("SELECT SUM(marks) FROM courses WHERE student_id=?", (student_id,)).fetchone()[0]
    total_marks = total_marks_query if total_marks_query else 0

    stats = {
        'total_courses': total_courses,
        'approved_courses': approved_courses,
        'total_marks': total_marks
    }

    db.close()
    return render_template('student_profile.html', student=student, stats=stats, success_msg=success_msg)

#-----------------------------
# END SESSION
#-----------------------------
@app.route('/end_session', methods=['POST'])
def end_session():
    if 'admin_id' not in session:
        return redirect('/admin')

    admin_section = session.get('admin_section')
    db = get_db()
    
    # Only deactivate the session for the current admin's section
    db.execute("UPDATE session_control SET is_active = 0 WHERE section = ?", (admin_section,))
    db.commit()
    db.close()

    return redirect('/admin_dashboard')




# -----------------------------
# STUDENT LOGIN
# -----------------------------
@app.route('/student_login', methods=['GET', 'POST'])
def student_login():

    if request.method == 'POST':

        email = request.form['username']
        password = request.form['password']

        db = get_db()

        user = db.execute(
            "SELECT * FROM students WHERE email=? AND password=?",
            (email, password)
        ).fetchone()

        db.close()

        if user:

            session['student_id'] = user[0]
            return redirect('/student_dashboard')

        else:
            return "Invalid Credentials"

    return render_template('student_login.html')


# -----------------------------
# WEEKLY UPDATES
# -----------------------------
@app.route('/submit_weekly_update', methods=['POST'])
def submit_weekly_update():

    if 'student_id' not in session:
        return redirect('/')

    course_id = request.form.get('course_id')
    week_number = request.form.get('week_number')
    content = request.form.get('content')

    if not course_id or not week_number or not content:
        return "Missing form data", 400

    db = get_db()

    db.execute("""
        INSERT INTO weekly_updates (course_id, week_number, progress, marks)
        VALUES (?, ?, ?, ?)
    """, (course_id, week_number, content, 0))

    db.commit()
    db.close()

    return redirect('/student_dashboard')


@app.route('/grade_update/<int:update_id>', methods=['POST'])
def grade_update(update_id):

    if 'admin_id' not in session:
        return redirect('/admin')

    new_marks = int(request.form.get('marks', 0))

    db = get_db()

    update_info = db.execute(
        "SELECT course_id FROM weekly_updates WHERE id=?",
        (update_id,)
    ).fetchone()

    if update_info:

        course_id = update_info[0]

        db.execute(
            "UPDATE weekly_updates SET marks=? WHERE id=?",
            (new_marks, update_id)
        )

        total_result = db.execute(
            "SELECT SUM(marks) FROM weekly_updates WHERE course_id=?",
            (course_id,)
        ).fetchone()

        new_total = total_result[0] if total_result[0] else 0

        db.execute(
            "UPDATE courses SET marks=? WHERE id=?",
            (new_total, course_id)
        )

        db.commit()

    db.close()

    return redirect('/admin_dashboard')


# -----------------------------
# STUDENT REGISTER
# -----------------------------
@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        section = request.form['section']

        db = get_db()

        try:

            db.execute(
                "INSERT INTO students (name, email, password, section) VALUES (?, ?, ?, ?)",
                (name, email, password, section)
            )

            db.commit()

            return redirect('/student_login')

        except sqlite3.IntegrityError:

            return "⚠️ Email already registered!"

        finally:

            db.close()

    return render_template('register.html')


# -----------------------------
# ADMIN LOGIN
# -----------------------------
@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        admin = db.execute(
            "SELECT * FROM admins WHERE username=? AND password=?",
            (username, password)
        ).fetchone()
        db.close()

        if admin:
            session['admin_id'] = admin['id']
            session['admin_section'] = admin['section'] # Store section in session
            return redirect('/admin_dashboard')
        else:
            return "Invalid Admin Credentials"
    return render_template('admin_login.html')


# -----------------------------
# ADMIN REGISTER
# -----------------------------
@app.route('/admin_register', methods=['GET', 'POST'])
def admin_register():

    if request.method == 'POST':

        username = request.form['name']
        email = request.form['email']
        password = request.form['password']
        section = request.form['section']

        db = get_db()

        try:

            db.execute(
                "INSERT INTO admins (username, password, section) VALUES (?, ?, ?)",
                (username, password, section)
            )

            db.commit()

            return redirect('/admin')

        except sqlite3.IntegrityError:

            return "Admin already exists"

        finally:

            db.close()

    return render_template('admin_register.html')


# -----------------------------
# STUDENT DASHBOARD
# -----------------------------
@app.route('/student_dashboard', methods=['GET', 'POST'])
def student_dashboard():
    if 'student_id' not in session:
        return redirect('/')

    db = get_db()
    
    # 1. NEW: Get the student's info to identify their section
    student = db.execute(
        "SELECT section FROM students WHERE id = ?", 
        (session['student_id'],)
    ).fetchone()
    student_section = student['section']

    if request.method == 'POST':
        # 2. UPDATE: Fetch session control ONLY for the student's section
        session_data = db.execute(
            "SELECT * FROM session_control WHERE section = ?", 
            (student_section,)
        ).fetchone()

        if not session_data or session_data[1] == 0:
            return "Session not active for your section"

        course_name = request.form['course']
        duration = int(request.form['duration'])
        domain = request.form['domain']
        platform = request.form['platform']

        allowed_domain = session_data[3]
        min_duration = session_data[4]
        allowed_platforms = [
            p.strip() for p in session_data[5].split(",")
        ]

        if (
            domain == allowed_domain and
            duration >= min_duration and
            platform in allowed_platforms
        ):
            status = "Approved"
            reason = "Automatically approved by system"
        else:
            status = "pending"
            reason = "Waiting for admin review"

        db.execute("""
           INSERT INTO courses
           (student_id, course_name, duration, domain, platform, status, reason, marks)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           """,
           (
               session['student_id'],
               course_name,
               duration,
               domain,
               platform,
               status,
               reason,
               0
           )
        )
        db.commit()

    courses = db.execute(
        "SELECT * FROM courses WHERE student_id=?",
        (session['student_id'],)
    ).fetchall()

    # 3. UPDATE: Fetch the session data for the dashboard display (filtered by section)
    session_data = db.execute(
        "SELECT * FROM session_control WHERE section = ?", 
        (student_section,)
    ).fetchone()

    updates = db.execute(
        "SELECT id, course_id, week_number, progress, marks FROM weekly_updates"
    ).fetchall()

    return render_template(
        'student_dashboard.html',
        courses=courses,
        updates=updates,
        session_data=session_data
    )

# -----------------------------
# ADMIN DASHBOARD
# -----------------------------
@app.route('/admin_dashboard')
def admin_dashboard():
    if 'admin_id' not in session:
        return redirect('/admin')

    db = get_db()
    admin_section = session.get('admin_section')

    # Fetch session status for the current admin's perspective
    session_data = db.execute("SELECT * FROM session_control WHERE section = ?", (admin_section,)).fetchone()

    # Filter courses: Only show students from the same section
    courses = db.execute("""
        SELECT courses.*, students.name
        FROM courses
        JOIN students ON courses.student_id = students.id
        WHERE students.section = ?
    """, (admin_section,)).fetchall()
   
    # Filter updates: Only show students from the same section
    updates = db.execute("""
        SELECT
            weekly_updates.id,
            weekly_updates.course_id,
            weekly_updates.week_number,
            weekly_updates.progress,
            IFNULL(weekly_updates.marks, 0),
            students.name,
            courses.course_name
        FROM weekly_updates
        JOIN courses ON weekly_updates.course_id = courses.id
        JOIN students ON courses.student_id = students.id
        WHERE students.section = ?
    """, (admin_section,)).fetchall()
   
    return render_template(
        'admin_dashboard.html',
        courses=courses,
        updates=updates,
        session_data=session_data
    )


# -----------------------------
# ADMIN PROFILE
# -----------------------------
@app.route('/admin_profile')
def admin_profile():
    if 'admin_id' not in session:
        return redirect('/admin')

    db = get_db()
    admin_section = session.get('admin_section')

    admin = db.execute("SELECT * FROM admins WHERE id=?", (session['admin_id'],)).fetchone()

    # Count only students in this admin's section
    total_students = db.execute(
        "SELECT COUNT(*) FROM students WHERE section=?", (admin_section,)
    ).fetchone()[0]

    # Count only courses in this admin's section
    total_courses = db.execute("""
        SELECT COUNT(*) FROM courses 
        JOIN students ON courses.student_id = students.id 
        WHERE students.section=?
    """, (admin_section,)).fetchone()[0]

    db.close()
    return render_template('admin_profile.html', admin=admin, 
                           total_students=total_students, total_courses=total_courses)

# -----------------------------
# LOGOUT
# -----------------------------
@app.route('/logout')
def logout():

    session.clear()

    return redirect('/')


@app.route('/update_status/<int:course_id>', methods=['POST'])
def update_status(course_id):

    if 'admin_id' not in session:
        return redirect('/admin')

    status = request.form.get('status')
    reason = request.form.get('reason')

    db = get_db()

    db.execute("""
        UPDATE courses
        SET status = ?, reason = ?
        WHERE id = ?
    """, (status, reason, course_id))

    db.commit()
    db.close()

    return redirect('/admin_dashboard')



# -----------------------------
# MAIN
# -----------------------------
if __name__ == "__main__":

    init_db()

    db = get_db()

    # ensure students table has required columns (section, roll_number, branch)
    cursor = db.execute("PRAGMA table_info(students)")
    columns = [col[1] for col in cursor.fetchall()]

    if "section" not in columns:
        db.execute("ALTER TABLE students ADD COLUMN section TEXT")
        db.commit()
    
    # --- ADD THESE NEW LINES FOR THE ADVANCED PROFILE FEATURES ---
    if "roll_number" not in columns:
        db.execute("ALTER TABLE students ADD COLUMN roll_number TEXT")
        db.commit()
        
    if "branch" not in columns:
        db.execute("ALTER TABLE students ADD COLUMN branch TEXT")
        db.commit()
    # -------------------------------------------------------------

    # ensure admins section column exists
    cursor = db.execute("PRAGMA table_info(admins)")
    columns = [col[1] for col in cursor.fetchall()]

    if "section" not in columns:

        db.execute("ALTER TABLE admins ADD COLUMN section TEXT")
        db.commit()
    
    # ensure weekly_updates marks column exists
    cursor = db.execute("PRAGMA table_info(weekly_updates)")
    columns = [col[1] for col in cursor.fetchall()]

    if "marks" not in columns:
        db.execute("ALTER TABLE weekly_updates ADD COLUMN marks INTEGER DEFAULT 0")
        db.commit()

    # default admin
    admin = db.execute(
        "SELECT * FROM admins WHERE username='admin'"
    ).fetchone()

    if not admin:

        db.execute(
            "INSERT INTO admins (username, password, section) VALUES (?, ?, ?)",
            ("admin", "admin123", "Admin")
        )

        db.commit()
    cursor = db.execute("PRAGMA table_info(session_control)")
    columns = [col[1] for col in cursor.fetchall()]

    if "section" not in columns:
        try:
            db.execute("ALTER TABLE session_control ADD COLUMN section TEXT")
            db.commit()
            print("Added 'section' column to session_control table successfully.")
        except Exception as e:
            print(f"Error updating session_control: {e}")

    db.close()

    app.run(debug=True)