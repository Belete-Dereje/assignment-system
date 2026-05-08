from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
import psycopg2
from config import Config
from datetime import datetime

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def get_db():
    conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI.replace('cockroachdb://', 'postgresql://'))
    conn.autocommit = True
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
    cur.execute("SELECT COUNT(*) FROM users WHERE role = 'teacher' AND is_approved = TRUE")
    teacher_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users WHERE role = 'teacher' AND is_approved = FALSE")
    pending_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
    admin_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM assignments")
    assignment_count = cur.fetchone()[0]
    
    cur.execute("SELECT DISTINCT department FROM students")
    depts1 = [d[0] for d in cur.fetchall() if d[0]]
    cur.execute("SELECT DISTINCT unnest(string_to_array(departments, ',')) FROM teachers")
    depts2 = [d[0].strip() for d in cur.fetchall() if d[0]]
    all_depts = list(set(depts1 + depts2))
    
    years_list = []
    cur.execute("SELECT DISTINCT year::text FROM students")
    for y in cur.fetchall():
        if y[0]: years_list.append(str(y[0]))
    cur.execute("SELECT DISTINCT unnest(string_to_array(years, ',')) FROM teachers")
    for y in cur.fetchall():
        if y[0]: years_list.append(y[0].strip())
    years_list = sorted(list(set(years_list)))
    
    cur.execute("""
        SELECT u.id, u.user_id, u.first_name, u.last_name, u.email, t.departments, t.years, t.courses
        FROM users u JOIN teachers t ON u.id = t.user_id
        WHERE u.role = 'teacher' AND u.is_approved = FALSE
    """)
    pending_teachers = cur.fetchall()
    
    cur.execute("""
        SELECT u.id, u.user_id, u.first_name, u.last_name, u.email, t.departments, t.years
        FROM users u JOIN teachers t ON u.id = t.user_id
        WHERE u.role = 'teacher' AND u.is_approved = TRUE
    """)
    approved_teachers = cur.fetchall()
    
    # System settings
    cur.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            setting_key VARCHAR(50) PRIMARY KEY,
            setting_value VARCHAR(20) NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    
    cur.execute("SELECT setting_key, setting_value FROM system_settings WHERE setting_key IN ('reg_student', 'reg_teacher')")
    settings = {s[0]: s[1] for s in cur.fetchall()}
    if 'reg_student' not in settings:
        settings['reg_student'] = 'on'
    if 'reg_teacher' not in settings:
        settings['reg_teacher'] = 'on'
    
    cur.close()
    conn.close()
    
    return render_template('admin/dashboard.html',
                         student_count=student_count,
                         teacher_count=teacher_count,
                         pending_count=pending_count,
                         admin_count=admin_count,
                         assignment_count=assignment_count,
                         departments=all_depts,
                         years=years_list,
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
    cur.execute("UPDATE users SET is_approved = TRUE WHERE id = %s AND role = 'teacher'", (user_id,))
    conn.commit()
    cur.close()
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
    cur.execute("DELETE FROM teachers WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM users WHERE id = %s AND role = 'teacher'", (user_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash('Teacher rejected!', 'danger')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/users', methods=['GET', 'POST'])
@login_required
def users():
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    cur = conn.cursor()
    
    role_filter = request.args.get('role', '').strip()
    year_filter = request.args.get('year', '').strip()
    dept_filter = request.args.get('department', '').strip()
    
    query = "SELECT u.id, u.user_id, u.first_name, u.last_name, u.email, u.role, u.is_approved, u.created_at FROM users u WHERE 1=1"
    params = []
    
    if role_filter:
        query += " AND u.role = %s"
        params.append(role_filter)
    
    if year_filter and role_filter in ('student', ''):
        if role_filter == 'student' or not role_filter:
            query += " AND (u.id IN (SELECT user_id FROM students WHERE year::text = %s)"
            params.append(year_filter)
            query += " OR u.id IN (SELECT user_id FROM teachers WHERE years LIKE %s))"
            params.append(f'%{year_filter}%')
    
    if dept_filter and role_filter in ('student', ''):
        if role_filter == 'student' or not role_filter:
            query += " AND (u.id IN (SELECT user_id FROM students WHERE department = %s)"
            params.append(dept_filter)
            query += " OR u.id IN (SELECT user_id FROM teachers WHERE departments LIKE %s))"
            params.append(f'%{dept_filter}%')
    
    if year_filter and role_filter == 'student':
        query = "SELECT u.id, u.user_id, u.first_name, u.last_name, u.email, u.role, u.is_approved, u.created_at FROM users u WHERE u.role = 'student' AND u.id IN (SELECT user_id FROM students WHERE year::text = %s)"
        params = [year_filter]
    elif year_filter and role_filter == 'teacher':
        query = "SELECT u.id, u.user_id, u.first_name, u.last_name, u.email, u.role, u.is_approved, u.created_at FROM users u WHERE u.role = 'teacher' AND u.id IN (SELECT user_id FROM teachers WHERE years LIKE %s)"
        params = [f'%{year_filter}%']
    elif dept_filter and role_filter == 'student':
        query = "SELECT u.id, u.user_id, u.first_name, u.last_name, u.email, u.role, u.is_approved, u.created_at FROM users u WHERE u.role = 'student' AND u.id IN (SELECT user_id FROM students WHERE department = %s)"
        params = [dept_filter]
    elif dept_filter and role_filter == 'teacher':
        query = "SELECT u.id, u.user_id, u.first_name, u.last_name, u.email, u.role, u.is_approved, u.created_at FROM users u WHERE u.role = 'teacher' AND u.id IN (SELECT user_id FROM teachers WHERE departments LIKE %s)"
        params = [f'%{dept_filter}%']
    
    query += " ORDER BY u.created_at DESC"
    
    cur.execute(query, params)
    users = cur.fetchall()
    
    # Get departments and years for filter dropdowns
    cur.execute("SELECT DISTINCT department FROM students")
    depts1 = [d[0] for d in cur.fetchall() if d[0]]
    cur.execute("SELECT DISTINCT unnest(string_to_array(departments, ',')) FROM teachers")
    depts2 = [d[0].strip() for d in cur.fetchall() if d[0]]
    departments = sorted(list(set(depts1 + depts2)))
    
    years_list = []
    cur.execute("SELECT DISTINCT year::text FROM students")
    for y in cur.fetchall():
        if y[0]: years_list.append(str(y[0]))
    cur.execute("SELECT DISTINCT unnest(string_to_array(years, ',')) FROM teachers")
    for y in cur.fetchall():
        if y[0]: years_list.append(y[0].strip())
    years = sorted(list(set(years_list)))
    
    cur.close()
    conn.close()
    
    return render_template('admin/users.html', users=users, departments=departments, years=years,
                         role_filter=role_filter, year_filter=year_filter, dept_filter=dept_filter)


@admin_bp.route('/edit-user/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT id, user_id, first_name, last_name, email, role, is_approved FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    
    if not user:
        flash('User not found!', 'danger')
        return redirect(url_for('admin.users'))
    
    student_data = None
    teacher_data = None
    if user[5] == 'student':
        cur.execute("SELECT department, year FROM students WHERE user_id = %s", (user_id,))
        student_data = cur.fetchone()
    elif user[5] == 'teacher':
        cur.execute("SELECT departments, years, courses FROM teachers WHERE user_id = %s", (user_id,))
        teacher_data = cur.fetchone()
    
    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip()
        new_password = request.form.get('password', '').strip()
        is_active = request.form.get('is_active') == 'on'
        
        cur.execute("UPDATE users SET first_name=%s, last_name=%s, email=%s, is_approved=%s WHERE id=%s",
                   (first_name, last_name, email, is_active, user_id))
        
        if new_password:
            from werkzeug.security import generate_password_hash
            cur.execute("UPDATE users SET password_hash=%s WHERE id=%s",
                       (generate_password_hash(new_password), user_id))
        
        if user[5] == 'student':
            dept = request.form.get('department', '').strip()
            year = request.form.get('year', '').strip()
            if dept and year:
                cur.execute("UPDATE students SET department=%s, year=%s WHERE user_id=%s", (dept, int(year), user_id))
        elif user[5] == 'teacher':
            depts = request.form.get('departments', '').strip()
            years = request.form.get('years', '').strip()
            courses = request.form.get('courses', '').strip()
            cur.execute("UPDATE teachers SET departments=%s, years=%s, courses=%s WHERE user_id=%s",
                       (depts, years, courses, user_id))
        
        conn.commit()
        cur.close()
        conn.close()
        flash('User updated successfully!', 'success')
        return redirect(url_for('admin.users'))
    
    cur.close()
    conn.close()
    return render_template('admin/edit_user.html', user=user, student_data=student_data, teacher_data=teacher_data)


@admin_bp.route('/toggle-user/<int:user_id>')
@login_required
def toggle_user(user_id):
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT is_approved FROM users WHERE id = %s", (user_id,))
    row = cur.fetchone()
    if row:
        new_status = not row[0]
        cur.execute("UPDATE users SET is_approved = %s WHERE id = %s", (new_status, user_id))
        conn.commit()
        flash('User status updated!', 'success' if new_status else 'warning')
    cur.close()
    conn.close()
    return redirect(url_for('admin.users'))


@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            setting_key VARCHAR(50) PRIMARY KEY,
            setting_value VARCHAR(20) NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    
    if request.method == 'POST':
        reg_student = request.form.get('reg_student', 'off')
        reg_teacher = request.form.get('reg_teacher', 'off')
        reg_start = request.form.get('reg_start', '').strip()
        reg_end = request.form.get('reg_end', '').strip()
        
        cur.execute("UPSERT INTO system_settings (setting_key, setting_value) VALUES ('reg_student', %s)", (reg_student,))
        cur.execute("UPSERT INTO system_settings (setting_key, setting_value) VALUES ('reg_teacher', %s)", (reg_teacher,))
        if reg_start:
            cur.execute("UPSERT INTO system_settings (setting_key, setting_value) VALUES ('reg_start', %s)", (reg_start,))
        if reg_end:
            cur.execute("UPSERT INTO system_settings (setting_key, setting_value) VALUES ('reg_end', %s)", (reg_end,))
        
        conn.commit()
        flash('Settings saved!', 'success')
    
    cur.execute("SELECT setting_key, setting_value FROM system_settings")
    settings = {s[0]: s[1] for s in cur.fetchall()}
    
    cur.close()
    conn.close()
    
    return render_template('admin/settings.html', settings=settings)
