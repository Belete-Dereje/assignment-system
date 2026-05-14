from flask import Flask, redirect, url_for, render_template, request, jsonify
from config import Config
from auth import auth_bp, login_manager
from routes_admin import admin_bp
from routes_teacher import teacher_bp
from routes_student import student_bp
import sqlite3
import os

def init_db():
    conn = sqlite3.connect('assignments.db')
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT UNIQUE NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            is_approved INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""CREATE TABLE IF NOT EXISTS students (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE REFERENCES users(id), department TEXT NOT NULL, year INTEGER NOT NULL)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS teachers (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE REFERENCES users(id), departments TEXT NOT NULL, years TEXT NOT NULL, courses TEXT NOT NULL)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS assignments (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT, teacher_id INTEGER REFERENCES teachers(id), course_name TEXT NOT NULL, department TEXT NOT NULL, year INTEGER NOT NULL, deadline TIMESTAMP NOT NULL, late_submission INTEGER DEFAULT 0, penalty_per_day REAL DEFAULT 0.0, max_score REAL DEFAULT 100.0, is_group INTEGER DEFAULT 0, max_group_size INTEGER DEFAULT 1, teacher_comment TEXT, files TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    # Ensure legacy DBs have max_score column
    cur.execute("PRAGMA table_info(assignments)")
    cols = [r[1] for r in cur.fetchall()]
    if 'max_score' not in cols:
        try:
            cur.execute("ALTER TABLE assignments ADD COLUMN max_score REAL DEFAULT 100.0")
        except Exception:
            pass
    if 'is_group' not in cols:
        try:
            cur.execute("ALTER TABLE assignments ADD COLUMN is_group INTEGER DEFAULT 0")
        except Exception:
            pass
    if 'max_group_size' not in cols:
        try:
            cur.execute("ALTER TABLE assignments ADD COLUMN max_group_size INTEGER DEFAULT 1")
        except Exception:
            pass
    cur.execute("""CREATE TABLE IF NOT EXISTS submissions (id INTEGER PRIMARY KEY AUTOINCREMENT, assignment_id INTEGER REFERENCES assignments(id), student_id INTEGER REFERENCES students(id), files TEXT, student_comment TEXT, submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP, grade REAL, feedback TEXT, evaluated_at TIMESTAMP, status TEXT DEFAULT 'submitted', complaint TEXT, complaint_status TEXT, group_id INTEGER)""")
    # ensure legacy DB has group_id
    cur.execute("PRAGMA table_info(submissions)")
    subs_cols = [r[1] for r in cur.fetchall()]
    if 'group_id' not in subs_cols:
        try:
            cur.execute("ALTER TABLE submissions ADD COLUMN group_id INTEGER")
        except Exception:
            pass
    cur.execute("""CREATE TABLE IF NOT EXISTS allowed_late_submissions (id INTEGER PRIMARY KEY AUTOINCREMENT, assignment_id INTEGER REFERENCES assignments(id), student_id INTEGER REFERENCES students(id), reason TEXT, allowed_by INTEGER REFERENCES teachers(id))""")
    
    conn.commit()
    conn.close()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    with app.app_context():
        init_db()
    
    login_manager.init_app(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(teacher_bp)
    app.register_blueprint(student_bp)
    
    @app.route('/')
    def index():
        return render_template('landing.html')
    
    @app.route('/sync/data', methods=['GET'])
    def sync_data():
        conn = sqlite3.connect('assignments.db')
        cur = conn.cursor()
        tables = ['users', 'students', 'teachers', 'assignments', 'submissions', 'allowed_late_submissions']
        data = {}
        for t in tables:
            cur.execute(f"SELECT * FROM {t}")
            rows = cur.fetchall()
            data[t] = [list(r) for r in rows]
        conn.close()
        return jsonify(data)
    
    @app.route('/sync/update', methods=['POST'])
    def sync_update():
        data = request.json
        conn = sqlite3.connect('assignments.db')
        cur = conn.cursor()
        for table, rows in data.items():
            if rows:
                for row in rows:
                    placeholders = ','.join(['?'] * len(row))
                    try:
                        cur.execute(f"INSERT OR REPLACE INTO {table} VALUES ({placeholders})", row)
                    except:
                        pass
        conn.commit()
        conn.close()
        return jsonify({'status': 'ok'})
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
# Replace the old sync_update with this smarter version
