from flask import Flask, redirect, url_for, render_template
from config import Config
from auth import auth_bp, login_manager
from routes_admin import admin_bp
from routes_teacher import teacher_bp
from routes_student import student_bp
import psycopg2
import os

def init_db():
    conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI.replace('cockroachdb://', 'postgresql://'))
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(20) UNIQUE NOT NULL,
            first_name VARCHAR(50) NOT NULL,
            last_name VARCHAR(50) NOT NULL,
            email VARCHAR(120) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(20) NOT NULL,
            is_approved BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id SERIAL PRIMARY KEY,
            user_id INTEGER UNIQUE REFERENCES users(id),
            department VARCHAR(100) NOT NULL,
            year INTEGER NOT NULL
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS teachers (
            id SERIAL PRIMARY KEY,
            user_id INTEGER UNIQUE REFERENCES users(id),
            departments VARCHAR(500) NOT NULL,
            years VARCHAR(100) NOT NULL,
            courses VARCHAR(500) NOT NULL
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS assignments (
            id SERIAL PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            description TEXT,
            teacher_id INTEGER REFERENCES teachers(id),
            course_name VARCHAR(100) NOT NULL,
            department VARCHAR(100) NOT NULL,
            year INTEGER NOT NULL,
            deadline TIMESTAMP NOT NULL,
            late_submission BOOLEAN DEFAULT FALSE,
            penalty_per_day FLOAT DEFAULT 0.0,
            teacher_comment TEXT,
            files VARCHAR(1000),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id SERIAL PRIMARY KEY,
            assignment_id INTEGER REFERENCES assignments(id),
            student_id INTEGER REFERENCES students(id),
            files VARCHAR(1000),
            student_comment TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            grade FLOAT,
            feedback TEXT,
            evaluated_at TIMESTAMP,
            status VARCHAR(20) DEFAULT 'submitted',
            complaint TEXT,
            complaint_status VARCHAR(20)
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS allowed_late_submissions (
            id SERIAL PRIMARY KEY,
            assignment_id INTEGER REFERENCES assignments(id),
            student_id INTEGER REFERENCES students(id),
            reason TEXT,
            allowed_by INTEGER REFERENCES teachers(id)
        )
    """)
    
    conn.commit()
    cur.close()
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
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
