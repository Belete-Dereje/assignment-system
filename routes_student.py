from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
import psycopg2
from config import Config
from datetime import datetime
import os

student_bp = Blueprint('student', __name__, url_prefix='/student')

def get_db():
    conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI.replace('cockroachdb://', 'postgresql://'))
    conn.autocommit = True
    return conn


@student_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role != 'student':
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT id, department, year FROM students WHERE user_id = %s", (current_user.id,))
    student = cur.fetchone()
    
    if not student:
        flash('Student profile not found! Please contact admin.', 'danger')
        return redirect(url_for('auth.logout'))
    
    student_id = student[0]
    department = student[1]
    year = student[2]
    
    # Get assignments matching student's department AND year
    cur.execute("""
        SELECT a.id, a.title, a.course_name, u.first_name, u.last_name, 
               a.deadline, a.late_submission, a.penalty_per_day, a.teacher_comment,
               a.department, a.year, a.files
        FROM assignments a
        JOIN teachers t ON a.teacher_id = t.id
        JOIN users u ON t.user_id = u.id
        WHERE a.department = %s AND a.year = %s
        ORDER BY a.deadline ASC
    """, (department.strip(), int(year)))
    assignments = cur.fetchall()
    
    cur.execute("""
        SELECT assignment_id, status, grade, feedback
        FROM submissions
        WHERE student_id = %s
    """, (student_id,))
    submissions = cur.fetchall()
    submission_dict = {s[0]: s for s in submissions}
    
    total = len(assignments)
    submitted = sum(1 for a in assignments if a[0] in submission_dict)
    unsubmitted = total - submitted
    overdue = sum(1 for a in assignments if a[5] < datetime.now() and a[0] not in submission_dict)
    
    cur.close()
    conn.close()
    
    return render_template('student/dashboard.html',
                         assignments=assignments,
                         submission_dict=submission_dict,
                         total=total,
                         submitted=submitted,
                         unsubmitted=unsubmitted,
                         overdue=overdue,
                         now=datetime.now(),
                         student_dept=department,
                         student_year=year)


@student_bp.route('/submit/<int:assignment_id>', methods=['GET', 'POST'])
@login_required
def submit(assignment_id):
    if current_user.role != 'student':
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT id FROM students WHERE user_id = %s", (current_user.id,))
    student = cur.fetchone()
    if not student:
        flash('Student profile not found!', 'danger')
        return redirect(url_for('student.dashboard'))
    student_id = student[0]
    
    cur.execute("""
        SELECT a.id, a.title, a.course_name, u.first_name, u.last_name,
               a.deadline, a.late_submission, a.penalty_per_day, a.teacher_comment, a.files,
               a.department, a.year
        FROM assignments a
        JOIN teachers t ON a.teacher_id = t.id
        JOIN users u ON t.user_id = u.id
        WHERE a.id = %s
    """, (assignment_id,))
    assignment = cur.fetchone()
    
    if not assignment:
        flash('Assignment not found!', 'danger')
        return redirect(url_for('student.dashboard'))
    
    cur.execute("SELECT id, status, files, student_comment FROM submissions WHERE assignment_id = %s AND student_id = %s", 
                (assignment_id, student_id))
    existing = cur.fetchone()
    
    if request.method == 'POST':
        uploaded_files = request.files.getlist('submission_files')
        file_paths = []
        for file in uploaded_files:
            if file.filename:
                filename = f"sub_{datetime.now().timestamp()}_{file.filename}"
                filepath = os.path.join(Config.UPLOAD_FOLDER, filename)
                file.save(filepath)
                file_paths.append(filename)
        
        files_str = ','.join(file_paths) if file_paths else (existing[2] if existing else '')
        comment = request.form.get('comment', '').strip()
        
        if existing:
            if existing[1] != 'evaluated' and assignment[5] > datetime.now():
                cur.execute("""
                    UPDATE submissions SET files = %s, student_comment = %s, updated_at = %s
                    WHERE id = %s
                """, (files_str, comment, datetime.now(), existing[0]))
                flash('Submission updated successfully!', 'success')
            elif existing[1] == 'evaluated':
                flash('Cannot update: submission already evaluated!', 'danger')
            else:
                flash('Cannot update: deadline has passed!', 'danger')
        else:
            # Check late permission
            cur.execute("SELECT id FROM allowed_late_submissions WHERE assignment_id = %s AND student_id = %s",
                       (assignment_id, student_id))
            has_late_permission = cur.fetchone()
            
            is_late = datetime.now() > assignment[5]
            if is_late and has_late_permission:
                status = 'submitted'
            elif is_late and not assignment[6]:
                flash('Deadline has passed and late submission is not allowed!', 'danger')
                cur.close()
                conn.close()
                return redirect(url_for('student.dashboard'))
            elif is_late and assignment[6]:
                status = 'late'
            else:
                status = 'submitted'
            
            cur.execute("""
                INSERT INTO submissions (assignment_id, student_id, files, student_comment, status)
                VALUES (%s, %s, %s, %s, %s)
            """, (assignment_id, student_id, files_str, comment, status))
            flash('Submission successful!', 'success')
        
        cur.close()
        conn.close()
        return redirect(url_for('student.dashboard'))
    
    cur.close()
    conn.close()
    
    return render_template('student/submit.html',
                         assignment=assignment,
                         existing=existing,
                         now=datetime.now())


@student_bp.route('/grades')
@login_required
def grades():
    if current_user.role != 'student':
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT id FROM students WHERE user_id = %s", (current_user.id,))
    student = cur.fetchone()
    if not student:
        return redirect(url_for('student.dashboard'))
    student_id = student[0]
    
    cur.execute("""
        SELECT a.title, a.course_name, u.first_name, u.last_name,
               s.grade, s.feedback, s.status, s.submitted_at, s.id as submission_id,
               s.complaint, s.complaint_status
        FROM submissions s
        JOIN assignments a ON s.assignment_id = a.id
        JOIN teachers t ON a.teacher_id = t.id
        JOIN users u ON t.user_id = u.id
        WHERE s.student_id = %s
        ORDER BY s.submitted_at DESC
    """, (student_id,))
    grades = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template('student/grades.html', grades=grades)


@student_bp.route('/complain/<int:submission_id>', methods=['POST'])
@login_required
def complain(submission_id):
    if current_user.role != 'student':
        return redirect(url_for('auth.login'))
    
    complaint = request.form.get('complaint', '').strip()
    
    if not complaint:
        flash('Please provide a reason for your complaint!', 'danger')
        return redirect(url_for('student.grades'))
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE submissions SET complaint = %s, complaint_status = 'pending'
        WHERE id = %s
    """, (complaint, submission_id))
    conn.commit()
    cur.close()
    conn.close()
    
    flash('Complaint submitted successfully!', 'success')
    return redirect(url_for('student.grades'))
