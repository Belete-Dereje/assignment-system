from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
import psycopg2
from config import Config

auth_bp = Blueprint('auth', __name__)

login_manager = LoginManager()
login_manager.login_view = 'auth.login'

def get_db():
    conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI.replace('cockroachdb://', 'postgresql://'))
    conn.autocommit = True
    return conn


@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, user_id, first_name, last_name, email, role, is_approved FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    if user:
        from flask_login import UserMixin
        class User(UserMixin):
            pass
        u = User()
        u.id = user[0]
        u.user_id = user[1]
        u.first_name = user[2]
        u.last_name = user[3]
        u.email = user[4]
        u.role = user[5]
        u.is_approved = user[6]
        return u
    return None


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        user_id = request.form.get('user_id', '').strip()
        role = request.form.get('role', '').strip()
        
        if not all([first_name, last_name, email, password, confirm_password, user_id, role]):
            flash('All fields are required!', 'danger')
            return render_template('register.html')
        
        if password != confirm_password:
            flash('Passwords do not match!', 'danger')
            return render_template('register.html')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters!', 'danger')
            return render_template('register.html')
        
        if role == 'student' and not user_id.startswith('DBU'):
            flash('Student ID must start with DBU!', 'danger')
            return render_template('register.html')
        
        if role == 'teacher' and not user_id.startswith('T'):
            flash('Teacher ID must start with T!', 'danger')
            return render_template('register.html')
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE email = %s OR user_id = %s", (email, user_id))
        if cur.fetchone():
            flash('Email or ID already registered!', 'danger')
            cur.close()
            conn.close()
            return render_template('register.html')
        
        from werkzeug.security import generate_password_hash
        password_hash = generate_password_hash(password)
        
        is_approved = True if role == 'student' else False
        
        cur.execute(
            "INSERT INTO users (user_id, first_name, last_name, email, password_hash, role, is_approved) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (user_id, first_name, last_name, email, password_hash, role, is_approved)
        )
        new_user_id = cur.fetchone()[0]
        
        if role == 'student':
            department = request.form.get('department', '').strip()
            year = request.form.get('year', '').strip()
            
            if not department or not year:
                flash('Department and Year are required for students!', 'danger')
                cur.close()
                conn.close()
                return render_template('register.html')
            
            cur.execute(
                "INSERT INTO students (user_id, department, year) VALUES (%s, %s, %s)",
                (new_user_id, department, int(year))
            )
        elif role == 'teacher':
            departments = request.form.get('departments', '').strip()
            years = request.form.get('years', '').strip()
            courses = request.form.get('courses', '').strip()
            
            if not departments or not years or not courses:
                flash('Departments, Years, and Courses are required for teachers!', 'danger')
                cur.close()
                conn.close()
                return render_template('register.html')
            
            cur.execute(
                "INSERT INTO teachers (user_id, departments, years, courses) VALUES (%s, %s, %s, %s)",
                (new_user_id, departments, years, courses)
            )
        
        cur.close()
        conn.close()
        
        if role == 'teacher':
            flash('Registration successful! Wait for admin approval to login.', 'success')
        else:
            flash('Registration successful! You can now login.', 'success')
        
        return redirect(url_for('auth.login'))
    
    return render_template('register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        user_id = request.form.get('user_id', '').strip()
        password = request.form.get('password', '').strip()
        
        if not all([email, user_id, password]):
            flash('All fields are required!', 'danger')
            return render_template('login.html')
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, user_id, first_name, last_name, email, password_hash, role, is_approved FROM users WHERE email = %s AND user_id = %s",
            (email, user_id)
        )
        user = cur.fetchone()
        cur.close()
        conn.close()
        
        if user:
            from werkzeug.security import check_password_hash
            if check_password_hash(user[5], password):
                if user[6] == 'admin' or user[7]:
                    from flask_login import UserMixin
                    class User(UserMixin):
                        pass
                    u = User()
                    u.id = user[0]
                    u.user_id = user[1]
                    u.first_name = user[2]
                    u.last_name = user[3]
                    u.email = user[4]
                    u.role = user[6]
                    u.is_approved = user[7]
                    
                    login_user(u)
                    
                    if user[6] == 'admin':
                        return redirect(url_for('admin.dashboard'))
                    elif user[6] == 'teacher':
                        return redirect(url_for('teacher.dashboard'))
                    else:
                        return redirect(url_for('student.dashboard'))
                else:
                    flash('Your account is not yet approved by admin.', 'warning')
            else:
                flash('Invalid email, ID, or password!', 'danger')
        else:
            flash('Invalid email, ID, or password!', 'danger')
    
    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
