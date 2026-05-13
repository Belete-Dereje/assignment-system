from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, make_response
from flask_login import login_required, current_user
import sqlite3
from config import Config
from datetime import datetime
import os
from io import BytesIO

teacher_bp = Blueprint('teacher', __name__, url_prefix='/teacher')

def get_db():
    conn = sqlite3.connect('assignments.db')
    conn.row_factory = sqlite3.Row
    return conn


@teacher_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role != 'teacher':
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT id, departments, years, courses FROM teachers WHERE user_id = ?", (current_user.id,))
    teacher = cur.fetchone()
    teacher_id = teacher['id']
    
    cur.execute("SELECT COUNT(*) FROM assignments WHERE teacher_id = ?", (teacher_id,))
    total_assignments = cur.fetchone()[0]
    
    cur.execute("""
        SELECT COUNT(*) FROM submissions s
        JOIN assignments a ON s.assignment_id = a.id
        WHERE a.teacher_id = ?
    """, (teacher_id,))
    total_submissions = cur.fetchone()[0]
    
    cur.execute("""
        SELECT COUNT(*) FROM submissions s
        JOIN assignments a ON s.assignment_id = a.id
        WHERE a.teacher_id = ? AND s.status = 'submitted'
    """, (teacher_id,))
    unevaluated = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM assignments WHERE teacher_id = ? AND deadline < datetime('now')", (teacher_id,))
    overdue = cur.fetchone()[0]
    
    cur.execute("""
        SELECT id, title, course_name, department, year, deadline, 
               late_submission, penalty_per_day, created_at
        FROM assignments WHERE teacher_id = ?
        ORDER BY created_at DESC
    """, (teacher_id,))
    assignments = cur.fetchall()
    
    conn.close()
    
    return render_template('teacher/dashboard.html',
                         total_assignments=total_assignments,
                         total_submissions=total_submissions,
                         unevaluated=unevaluated,
                         overdue=overdue,
                         assignments=assignments)


@teacher_bp.route('/create-assignment', methods=['GET', 'POST'])
@login_required
def create_assignment():
    if current_user.role != 'teacher':
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, departments, years, courses FROM teachers WHERE user_id = ?", (current_user.id,))
    teacher = cur.fetchone()
    teacher_id = teacher['id']
    teacher_departments = [d.strip() for d in teacher['departments'].split(',') if d.strip()]
    teacher_years = [y.strip() for y in teacher['years'].split(',') if y.strip()]
    teacher_courses = [c.strip() for c in teacher['courses'].split(',') if c.strip()]
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        course_name = request.form.get('course_name', '').strip()
        department = request.form.get('department', '').strip()
        year = request.form.get('year', '').strip()
        deadline = request.form.get('deadline', '').strip()
        late_submission = 1 if request.form.get('late_submission') == 'yes' else 0
        penalty_per_day = float(request.form.get('penalty_per_day', '0') or 0)
        max_score = float(request.form.get('max_score', '100') or 100)
        is_group = 1 if request.form.get('is_group') == 'yes' else 0
        max_group_size = int(request.form.get('max_group_size', '1') or 1)
        teacher_comment = request.form.get('teacher_comment', '').strip()
        
        if not all([title, course_name, department, year, deadline]):
            flash('All required fields must be filled!', 'danger')
            return render_template('teacher/create_assignment.html',
                                 departments=teacher_departments, years=teacher_years, courses=teacher_courses)
        
        try:
            deadline_date = datetime.strptime(deadline, '%Y-%m-%dT%H:%M')
            if deadline_date < datetime.now():
                flash('Deadline cannot be in the past!', 'danger')
                return render_template('teacher/create_assignment.html',
                                     departments=teacher_departments, years=teacher_years, courses=teacher_courses)
        except ValueError:
            flash('Invalid deadline format!', 'danger')
            return render_template('teacher/create_assignment.html',
                                 departments=teacher_departments, years=teacher_years, courses=teacher_courses)
        
        files = ''
        if 'assignment_files' in request.files:
            uploaded_files = request.files.getlist('assignment_files')
            file_paths = []
            for file in uploaded_files:
                if file.filename:
                    filename = f"{datetime.now().timestamp()}_{file.filename}"
                    filepath = os.path.join(Config.UPLOAD_FOLDER, filename)
                    file.save(filepath)
                    file_paths.append(filename)
            files = ','.join(file_paths)
        
        cur.execute("""
            INSERT INTO assignments (title, description, teacher_id, course_name, department, year, deadline, late_submission, penalty_per_day, max_score, is_group, max_group_size, teacher_comment, files)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (title, description, teacher_id, course_name, department, int(year), deadline_date, late_submission, penalty_per_day, max_score, is_group, max_group_size, teacher_comment, files))
        
        conn.commit()
        conn.close()
        flash('Assignment created!', 'success')
        return redirect(url_for('teacher.dashboard'))
    
    conn.close()
    return render_template('teacher/create_assignment.html',
                         departments=teacher_departments, years=teacher_years, courses=teacher_courses)


@teacher_bp.route('/edit-assignment/<int:assignment_id>', methods=['GET', 'POST'])
@login_required
def edit_assignment(assignment_id):
    if current_user.role != 'teacher':
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT id, departments, years, courses FROM teachers WHERE user_id = ?", (current_user.id,))
    teacher = cur.fetchone()
    teacher_id = teacher['id']
    teacher_departments = [d.strip() for d in teacher['departments'].split(',') if d.strip()]
    teacher_years = [y.strip() for y in teacher['years'].split(',') if y.strip()]
    teacher_courses = [c.strip() for c in teacher['courses'].split(',') if c.strip()]
    
    cur.execute("SELECT * FROM assignments WHERE id = ? AND teacher_id = ?", (assignment_id, teacher_id))
    assignment = cur.fetchone()
    
    if not assignment:
        flash('Assignment not found!', 'danger')
        return redirect(url_for('teacher.dashboard'))
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        course_name = request.form.get('course_name', '').strip()
        department = request.form.get('department', '').strip()
        year = request.form.get('year', '').strip()
        deadline = request.form.get('deadline', '').strip()
        late_submission = 1 if request.form.get('late_submission') == 'yes' else 0
        penalty_per_day = float(request.form.get('penalty_per_day', '0') or 0)
        teacher_comment = request.form.get('teacher_comment', '').strip()
        replace_files = request.form.get('replace_files') == 'yes'
        
        try:
            deadline_date = datetime.strptime(deadline, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('Invalid deadline format!', 'danger')
            return render_template('teacher/edit_assignment.html', assignment=assignment,
                                 departments=teacher_departments, years=teacher_years, courses=teacher_courses)
        
        files = assignment['files']
        if replace_files and 'assignment_files' in request.files:
            new_paths = []
            for f in request.files.getlist('assignment_files'):
                if f.filename:
                    fname = f"{datetime.now().timestamp()}_{f.filename}"
                    f.save(os.path.join(Config.UPLOAD_FOLDER, fname))
                    new_paths.append(fname)
            files = ','.join(new_paths) if new_paths else ''
        
        max_score = float(request.form.get('max_score', assignment['max_score'] if assignment['max_score'] else 100) or 100)
        is_group = 1 if request.form.get('is_group') == 'yes' else 0
        max_group_size = int(request.form.get('max_group_size', assignment['max_group_size'] if assignment['max_group_size'] else 1) or 1)
        cur.execute("""
            UPDATE assignments SET title=?, description=?, course_name=?, department=?, year=?, 
            deadline=?, late_submission=?, penalty_per_day=?, max_score=?, is_group=?, max_group_size=?, teacher_comment=?, files=?
            WHERE id=?
        """, (title, description, course_name, department, int(year), deadline_date,
              late_submission, penalty_per_day, max_score, is_group, max_group_size, teacher_comment, files, assignment_id))
        
        conn.commit()
        conn.close()
        flash('Assignment updated!', 'success')
        return redirect(url_for('teacher.dashboard'))
    
    conn.close()
    return render_template('teacher/edit_assignment.html', assignment=assignment,
                         departments=teacher_departments, years=teacher_years, courses=teacher_courses)


@teacher_bp.route('/submissions/<int:assignment_id>')
@login_required
def view_submissions(assignment_id):
    if current_user.role != 'teacher':
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT a.id as id, a.title as title, a.course_name as course_name, a.department as department, a.year as year,
               a.deadline as deadline, a.late_submission as late_submission, a.penalty_per_day as penalty_per_day, a.max_score as max_score
        FROM assignments a WHERE a.id = ?
    """, (assignment_id,))
    assignment = cur.fetchone()
    
    if not assignment:
        flash('Assignment not found!', 'danger')
        return redirect(url_for('teacher.dashboard'))
    
    cur.execute("""
        SELECT s.id, s.student_id, u.first_name, u.last_name, u.user_id, 
               s.status, s.grade, s.feedback, s.submitted_at, s.files, s.student_comment, s.complaint, s.complaint_status, s.group_id
        FROM submissions s
        JOIN students st ON s.student_id = st.id
        JOIN users u ON st.user_id = u.id
        WHERE s.assignment_id = ?
        ORDER BY s.submitted_at DESC
    """, (assignment_id,))
    raw_submissions = cur.fetchall()

    grouped_submissions = []
    group_map = {}
    for submission in raw_submissions:
        group_id = submission['group_id']
        if group_id:
            if group_id not in group_map:
                group_map[group_id] = {
                    'submission_id': submission['id'],
                    'group_id': group_id,
                    'is_group': True,
                    'status': submission['status'],
                    'grade': submission['grade'],
                    'feedback': submission['feedback'],
                    'submitted_at': submission['submitted_at'],
                    'files': submission['files'],
                    'student_comment': submission['student_comment'],
                    'complaint': submission['complaint'],
                    'complaint_status': submission['complaint_status'],
                    'members': []
                }
                grouped_submissions.append(group_map[group_id])
            group_map[group_id]['members'].append({
                'student_id': submission['student_id'],
                'first_name': submission['first_name'],
                'last_name': submission['last_name'],
                'user_id': submission['user_id']
            })
        else:
            grouped_submissions.append({
                'submission_id': submission['id'],
                'group_id': None,
                'is_group': False,
                'status': submission['status'],
                'grade': submission['grade'],
                'feedback': submission['feedback'],
                'submitted_at': submission['submitted_at'],
                'files': submission['files'],
                'student_comment': submission['student_comment'],
                'complaint': submission['complaint'],
                'complaint_status': submission['complaint_status'],
                'members': [{
                    'student_id': submission['student_id'],
                    'first_name': submission['first_name'],
                    'last_name': submission['last_name'],
                    'user_id': submission['user_id']
                }]
            })
    
    cur.execute("""
        SELECT st.id, u.first_name, u.last_name, u.user_id
        FROM students st
        JOIN users u ON st.user_id = u.id
        WHERE st.department = ? AND st.year = ?
        AND st.id NOT IN (SELECT student_id FROM submissions WHERE assignment_id = ?)
    """, (assignment['department'], assignment['year'], assignment_id))
    not_submitted = cur.fetchall()
    
    cur.execute("""
        SELECT als.student_id, als.reason, u.first_name, u.last_name
        FROM allowed_late_submissions als
        JOIN students st ON als.student_id = st.id
        JOIN users u ON st.user_id = u.id
        WHERE als.assignment_id = ?
    """, (assignment_id,))
    allowed_late = cur.fetchall()
    allowed_late_dict = {a[0]: a for a in allowed_late}
    
    conn.close()
    
    return render_template('teacher/submissions.html',
                         assignment=assignment, submissions=grouped_submissions,
                         not_submitted=not_submitted, allowed_late_dict=allowed_late_dict)


@teacher_bp.route('/manage-late/<int:assignment_id>', methods=['POST'])
@login_required
def manage_late(assignment_id):
    if current_user.role != 'teacher':
        return redirect(url_for('auth.login'))
    
    action = request.form.get('action', '').strip()
    student_ids = request.form.getlist('student_ids')
    
    if not student_ids:
        flash('Select at least one student!', 'warning')
        return redirect(url_for('teacher.view_submissions', assignment_id=assignment_id))
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM teachers WHERE user_id = ?", (current_user.id,))
    teacher_id = cur.fetchone()['id']
    
    if action == 'allow':
        reason = request.form.get('reason', '').strip()
        if not reason:
            flash('Provide a reason!', 'danger')
            return redirect(url_for('teacher.view_submissions', assignment_id=assignment_id))
        for sid in student_ids:
            cur.execute("SELECT id FROM allowed_late_submissions WHERE assignment_id=? AND student_id=?", (assignment_id, sid))
            if not cur.fetchone():
                cur.execute("INSERT INTO allowed_late_submissions (assignment_id, student_id, reason, allowed_by) VALUES (?,?,?,?)", 
                           (assignment_id, sid, reason, teacher_id))
        flash(f'Allowed {len(student_ids)} student(s)!', 'success')
    elif action == 'revoke':
        for sid in student_ids:
            cur.execute("DELETE FROM allowed_late_submissions WHERE assignment_id=? AND student_id=?", (assignment_id, sid))
        flash(f'Revoked {len(student_ids)} student(s)!', 'warning')
    
    conn.commit()
    conn.close()
    return redirect(url_for('teacher.view_submissions', assignment_id=assignment_id))


@teacher_bp.route('/stats/<int:assignment_id>')
@login_required
def get_stats(assignment_id):
    if current_user.role != 'teacher':
        return {'error': 'Unauthorized'}, 403
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT department, year FROM assignments WHERE id = ?", (assignment_id,))
    assignment = cur.fetchone()
    
    if not assignment:
        return {'error': 'Not found'}, 404
    
    cur.execute("""
        SELECT st.id, u.first_name, u.last_name, u.user_id
        FROM students st JOIN users u ON st.user_id = u.id
        WHERE st.department = ? AND st.year = ?
    """, (assignment['department'], assignment['year']))
    all_students = cur.fetchall()
    
    cur.execute("SELECT student_id, status, grade, feedback, complaint FROM submissions WHERE assignment_id = ?", (assignment_id,))
    submissions = cur.fetchall()
    submission_dict = {s[0]: (s[1], s[2], s[3], s[4]) for s in submissions}
    
    total = len(all_students)
    submitted_count = len(submissions)
    not_submitted_count = total - submitted_count
    evaluated_count = sum(1 for s in submissions if s[1] == 'evaluated')
    late_count = sum(1 for s in submissions if s[1] == 'late')
    
    grades = [s[2] for s in submissions if s[2] is not None]
    avg_grade = round(sum(grades) / len(grades), 1) if grades else None
    
    students_data = []
    for student in all_students:
        sid = student[0]
        sub = submission_dict.get(sid)
        students_data.append({'complaint': sub[3] if sub and sub[3] else None,
            'name': f"{student[1]} {student[2]}",
            'user_id': student[3],
            'status': sub[0] if sub else 'not_submitted',
            'grade': sub[1] if sub else None,
            'feedback': sub[2] if sub else None
        })
    
    conn.close()
    
    return {
        'total_students': total,
        'submitted_count': submitted_count,
        'not_submitted_count': not_submitted_count,
        'evaluated_count': evaluated_count,
        'late_count': late_count,
        'avg_grade': avg_grade,
        'students': students_data
    }


@teacher_bp.route('/evaluate/<int:submission_id>', methods=['GET', 'POST'])
@login_required
def evaluate(submission_id):
    if current_user.role != 'teacher':
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
         SELECT s.id, s.student_id, s.submitted_at, s.grade, s.feedback, s.status, s.group_id, s.files, s.student_comment,
             s.complaint, s.complaint_status,
               u.first_name, u.last_name, u.user_id, a.title, a.id as assignment_id, a.deadline, a.penalty_per_day, a.max_score
        FROM submissions s
        JOIN students st ON s.student_id = st.id
        JOIN users u ON st.user_id = u.id
        JOIN assignments a ON s.assignment_id = a.id
        WHERE s.id = ?
    """, (submission_id,))
    submission = cur.fetchone()
    
    # compute current effective max value considering late penalty and allowed_late
    from math import ceil
    current_value = None
    max_score = float(submission['max_score']) if submission['max_score'] is not None else 100.0
    try:
        submitted_at = datetime.strptime(submission['submitted_at'], '%Y-%m-%d %H:%M:%S') if submission['submitted_at'] else None
        deadline_dt = datetime.strptime(submission['deadline'], '%Y-%m-%d %H:%M:%S') if submission['deadline'] else None
    except Exception:
        submitted_at = None
        deadline_dt = None

    days_late = 0
    if submitted_at and deadline_dt and submitted_at > deadline_dt:
        seconds = (submitted_at - deadline_dt).total_seconds()
        days_late = int(ceil(seconds / 86400.0))

    # check allowed late
    if days_late > 0:
        cur.execute("SELECT id FROM allowed_late_submissions WHERE assignment_id=? AND student_id=?", (submission['assignment_id'], submission['student_id']))
        if cur.fetchone():
            days_late = 0

    penalty = float(submission['penalty_per_day']) if submission['penalty_per_day'] is not None else 0.0
    current_value = max(0.0, max_score * max(0.0, 1 - (penalty/100.0) * days_late))

    if request.method == 'POST':
        grade = float(request.form.get('grade', '0'))
        feedback = request.form.get('feedback', '').strip()
        # enforce boundaries
        if grade < 0:
            grade = 0.0
        if grade > current_value:
            flash(f'Grade cannot exceed current maximum ({current_value}).', 'danger')
            conn.close()
            return redirect(url_for('teacher.evaluate', submission_id=submission_id))

        # if this is a group submission, apply grade to all members in the same group
        if submission['group_id']:
            cur.execute("""
                UPDATE submissions SET grade = ?, feedback = ?, status = 'evaluated', complaint_status = 'responded', evaluated_at = ? WHERE group_id = ?
            """, (grade, feedback, datetime.now(), submission['group_id']))
        else:
            cur.execute("""
                UPDATE submissions SET grade = ?, feedback = ?, status = 'evaluated', complaint_status = 'responded', evaluated_at = ? WHERE id = ?
            """, (grade, feedback, datetime.now(), submission_id))

        conn.commit()
        conn.close()
        flash('Submission evaluated!', 'success')
        return redirect(url_for('teacher.view_submissions', assignment_id=submission['assignment_id']))
    
    # if group, fetch group members to display
    group_members = []
    if submission['group_id']:
        cur2 = conn.cursor()
        cur2.execute("""
            SELECT st.id, u.first_name, u.last_name, u.user_id
            FROM submissions s
            JOIN students st ON s.student_id = st.id
            JOIN users u ON st.user_id = u.id
            WHERE s.group_id = ?
        """, (submission['group_id'],))
        group_members = cur2.fetchall()

    conn.close()
    return render_template('teacher/evaluate.html', submission=submission, current_value=current_value, group_members=group_members)


@teacher_bp.route('/export-pdf/<int:assignment_id>')
@login_required
def export_pdf(assignment_id):
    if current_user.role != 'teacher':
        return redirect(url_for('auth.login'))
    
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT title, course_name, department, year, deadline FROM assignments WHERE id=?", (assignment_id,))
    a = cur.fetchone()
    cur.execute("""
        SELECT u.user_id, u.first_name, u.last_name, s.status, s.grade, s.feedback, s.submitted_at 
        FROM submissions s JOIN students st ON s.student_id=st.id JOIN users u ON st.user_id=u.id 
        WHERE s.assignment_id=? ORDER BY s.submitted_at DESC
    """, (assignment_id,))
    subs = cur.fetchall()
    conn.close()
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()
    elements.append(Paragraph(f"<b>{a[0]}</b>", styles['Title']))
    elements.append(Paragraph(f"Course: {a[1]} | Dept: {a[2]} | Year: {a[3]} | Deadline: {a[4]}", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    data = [['Student ID', 'Name', 'Status', 'Grade', 'Feedback', 'Submitted']]
    for s in subs:
        data.append([s[0], f"{s[1]} {s[2]}", s[3], f"{s[4]}%" if s[4] else '-', s[5][:80] if s[5] else '-', s[6] if s[6] else '-'])
    
    table = Table(data)
    table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.HexColor('#3498db')), ('TEXTCOLOR', (0,0), (-1,0), colors.white), ('GRID', (0,0), (-1,-1), 1, colors.black), ('FONTSIZE', (0,0), (-1,-1), 9), ('PADDING', (0,0), (-1,-1), 5)]))
    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    resp = make_response(buffer.getvalue())
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = f'attachment; filename=submissions_{assignment_id}.pdf'
    return resp


@teacher_bp.route('/download/<path:filename>')
@login_required
def download_file(filename):
    filepath = os.path.join(Config.UPLOAD_FOLDER, filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    flash('File not found!', 'danger')
    return redirect(request.referrer or url_for('teacher.dashboard'))
