from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
import sqlite3
from datetime import datetime

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def get_db():
    conn = sqlite3.connect('assignments.db')
    conn.row_factory = sqlite3.Row
    return conn


@admin_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM users WHERE role = 'student'")
    student_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users WHERE role = 'teacher' AND is_approved = 1")
    teacher_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users WHERE role = 'teacher' AND is_approved = 0")
    pending_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
    admin_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM assignments")
    assignment_count = cur.fetchone()[0]
    
    # Get departments
    depts = set()
    cur.execute("SELECT department FROM students")
    for row in cur.fetchall():
        if row[0]: depts.add(row[0])
    cur.execute("SELECT departments FROM teachers")
    for row in cur.fetchall():
        if row[0]:
            for d in row[0].split(','):
                depts.add(d.strip())
    departments = sorted(list(depts))
    
    # Get years
    years = set()
    cur.execute("SELECT year FROM students")
    for row in cur.fetchall():
        if row[0]: years.add(str(row[0]))
    cur.execute("SELECT years FROM teachers")
    for row in cur.fetchall():
        if row[0]:
            for y in row[0].split(','):
                years.add(y.strip())
    years = sorted(list(years))
    
    # Pending teachers
    cur.execute("""
        SELECT u.id, u.user_id, u.first_name, u.last_name, u.email, t.departments, t.years, t.courses
        FROM users u JOIN teachers t ON u.id = t.user_id
        WHERE u.role = 'teacher' AND u.is_approved = 0
    """)
    pending_teachers = cur.fetchall()
    
    # Approved teachers
    cur.execute("""
        SELECT u.id, u.user_id, u.first_name, u.last_name, u.email, t.departments, t.years
        FROM users u JOIN teachers t ON u.id = t.user_id
        WHERE u.role = 'teacher' AND u.is_approved = 1
    """)
    approved_teachers = cur.fetchall()
    
    # Settings
    cur.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    
    cur.execute("SELECT setting_key, setting_value FROM system_settings WHERE setting_key IN ('reg_student', 'reg_teacher')")
    settings = {row['setting_key']: row['setting_value'] for row in cur.fetchall()}
    settings.setdefault('reg_student', 'on')
    settings.setdefault('reg_teacher', 'on')
    
    conn.close()
    
    return render_template('admin/dashboard.html',
                         student_count=student_count,
                         teacher_count=teacher_count,
                         pending_count=pending_count,
                         admin_count=admin_count,
                         assignment_count=assignment_count,
                         departments=departments,
                         years=years,
                         pending_teachers=pending_teachers,
                         approved_teachers=approved_teachers,
                         settings=settings)


@admin_bp.route('/approve/<int:user_id>')
@login_required
def approve(user_id):
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_approved = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    flash('Teacher approved!', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/reject/<int:user_id>')
@login_required
def reject(user_id):
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM teachers WHERE user_id = ?", (user_id,))
    cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    flash('Teacher rejected!', 'danger')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/users', endpoint='manage_users')
@login_required
def manage_users():
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    cur = conn.cursor()
    
    role_filter = request.args.get('role', '').strip()
    year_filter = request.args.get('year', '').strip()
    dept_filter = request.args.get('department', '').strip()
    
    query = "SELECT id, user_id, first_name, last_name, email, role, is_approved, created_at FROM users WHERE 1=1"
    params = []
    
    if role_filter:
        query += " AND role = ?"
        params.append(role_filter)
    
    query += " ORDER BY created_at DESC"
    
    cur.execute(query, params)
    all_users = cur.fetchall()
    
    # Filter by year/department in Python (since SQLite can't do complex joins easily)
    filtered_users = []
    for u in all_users:
        include = True
        if year_filter and u['role'] == 'student':
            cur.execute("SELECT year FROM students WHERE user_id = ?", (u['id'],))
            row = cur.fetchone()
            if not row or str(row[0]) != year_filter:
                include = False
        if dept_filter and u['role'] == 'student':
            cur.execute("SELECT department FROM students WHERE user_id = ?", (u['id'],))
            row = cur.fetchone()
            if not row or row[0] != dept_filter:
                include = False
        if year_filter and u['role'] == 'teacher':
            cur.execute("SELECT years FROM teachers WHERE user_id = ?", (u['id'],))
            row = cur.fetchone()
            if not row or year_filter not in row[0]:
                include = False
        if dept_filter and u['role'] == 'teacher':
            cur.execute("SELECT departments FROM teachers WHERE user_id = ?", (u['id'],))
            row = cur.fetchone()
            if not row or dept_filter not in row[0]:
                include = False
        if include:
            filtered_users.append(u)
    
    # Get departments/years for filters
    depts = set()
    cur.execute("SELECT department FROM students")
    for row in cur.fetchall():
        if row[0]: depts.add(row[0])
    cur.execute("SELECT departments FROM teachers")
    for row in cur.fetchall():
        if row[0]:
            for d in row[0].split(','):
                depts.add(d.strip())
    departments = sorted(list(depts))
    
    years = set()
    cur.execute("SELECT year FROM students")
    for row in cur.fetchall():
        if row[0]: years.add(str(row[0]))
    cur.execute("SELECT years FROM teachers")
    for row in cur.fetchall():
        if row[0]:
            for y in row[0].split(','):
                years.add(y.strip())
    years = sorted(list(years))
    
    conn.close()
    
    return render_template('admin/users.html', users=filtered_users, departments=departments, years=years,
                         role_filter=role_filter, year_filter=year_filter, dept_filter=dept_filter)


@admin_bp.route('/edit-user/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cur.fetchone()
    
    if not user:
        flash('User not found!', 'danger')
        return redirect(url_for('admin.manage_users'))
    
    student_data = None
    teacher_data = None
    if user['role'] == 'student':
        cur.execute("SELECT department, year FROM students WHERE user_id = ?", (user_id,))
        student_data = cur.fetchone()
    elif user['role'] == 'teacher':
        cur.execute("SELECT departments, years, courses FROM teachers WHERE user_id = ?", (user_id,))
        teacher_data = cur.fetchone()
    
    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip()
        new_password = request.form.get('password', '').strip()
        is_active = 1 if request.form.get('is_active') == 'on' else 0
        
        cur.execute("UPDATE users SET first_name=?, last_name=?, email=?, is_approved=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                   (first_name, last_name, email, is_active, user_id))
        
        if new_password:
            from werkzeug.security import generate_password_hash
            cur.execute("UPDATE users SET password_hash=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                       (generate_password_hash(new_password), user_id))
        
        if user['role'] == 'student':
            dept = request.form.get('department', '').strip()
            year = request.form.get('year', '').strip()
            if dept and year:
                cur.execute("UPDATE students SET department=?, year=? WHERE user_id=?", (dept, int(year), user_id))
        elif user['role'] == 'teacher':
            depts = request.form.get('departments', '').strip()
            years = request.form.get('years', '').strip()
            courses = request.form.get('courses', '').strip()
            cur.execute("UPDATE teachers SET departments=?, years=?, courses=? WHERE user_id=?",
                       (depts, years, courses, user_id))
        
        conn.commit()
        conn.close()
        flash('User updated!', 'success')
        return redirect(url_for('admin.manage_users'))
    
    conn.close()
    return render_template('admin/edit_user.html', user=user, student_data=student_data, teacher_data=teacher_data)


@admin_bp.route('/toggle-user/<int:user_id>')
@login_required
def toggle_user(user_id):
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT is_approved FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    if row:
        new_status = 1 if row[0] == 0 else 0
        cur.execute("UPDATE users SET is_approved = ? WHERE id = ?", (new_status, user_id))
        conn.commit()
        flash('User status updated!', 'success')
    conn.close()
    return redirect(url_for('admin.manage_users'))


@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    
    if request.method == 'POST':
        reg_student = request.form.get('reg_student', 'off')
        reg_teacher = request.form.get('reg_teacher', 'off')
        
        cur.execute("INSERT OR REPLACE INTO system_settings (setting_key, setting_value) VALUES ('reg_student', ?)", (reg_student,))
        cur.execute("INSERT OR REPLACE INTO system_settings (setting_key, setting_value) VALUES ('reg_teacher', ?)", (reg_teacher,))
        conn.commit()
        flash('Settings saved!', 'success')
    
    cur.execute("SELECT setting_key, setting_value FROM system_settings")
    settings = {row['setting_key']: row['setting_value'] for row in cur.fetchall()}
    
    conn.close()
    return render_template('admin/settings.html', settings=settings)
