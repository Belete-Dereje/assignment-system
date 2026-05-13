from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
import sqlite3
from config import Config
from datetime import datetime
import os

student_bp = Blueprint('student', __name__, url_prefix='/student')

def get_db():
    conn = sqlite3.connect('assignments.db')
    conn.row_factory = sqlite3.Row
    return conn


# provide reminders for student pages (notifications)
@student_bp.context_processor
def student_notifications():
    from math import ceil
    reminders = []
    try:
        from flask_login import current_user
        if not current_user.is_authenticated or current_user.role != 'student':
            return dict(reminder_count=0, reminder_notifications=[])

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id, department, year FROM students WHERE user_id = ?", (current_user.id,))
        student = cur.fetchone()
        if not student:
            conn.close()
            return dict(reminder_count=0, reminder_notifications=[])

        student_id = student['id']
        dept = student['department']
        year = student['year']

        # assignments for this student's dept/year that the student hasn't submitted
        cur.execute("""
            SELECT a.id, a.title, a.course_name, a.deadline, a.late_submission, a.penalty_per_day, a.max_score
            FROM assignments a
            WHERE a.department = ? AND a.year = ?
            AND a.id NOT IN (SELECT assignment_id FROM submissions WHERE student_id = ?)
        """, (dept.strip(), int(year), student_id))
        assignments = cur.fetchall()

        now = datetime.now()
        for a in assignments:
            try:
                deadline_dt = datetime.strptime(a['deadline'], '%Y-%m-%d %H:%M:%S') if a['deadline'] else None
            except Exception:
                deadline_dt = None

            max_score = float(a['max_score']) if a['max_score'] is not None else 100.0

            if not deadline_dt:
                continue

            if now > deadline_dt:
                # past deadline - include only if late allowed
                if a['late_submission']:
                    seconds = (now - deadline_dt).total_seconds()
                    days_late = int(ceil(seconds / 86400.0))
                    penalty = float(a['penalty_per_day']) if a['penalty_per_day'] is not None else 0.0
                    current_value = max(0.0, max_score * max(0.0, 1 - (penalty/100.0) * days_late))
                    reminders.append({'id': a['id'], 'title': a['title'], 'type': 'late_allowed', 'days_late': days_late, 'penalty': penalty, 'current_value': current_value, 'max_score': max_score})
            else:
                seconds = (deadline_dt - now).total_seconds()
                days_left = int(ceil(seconds / 86400.0))
                if days_left <= 3:
                    reminders.append({'id': a['id'], 'title': a['title'], 'type': 'upcoming', 'days_left': days_left, 'deadline': a['deadline'], 'max_score': max_score})

        conn.close()
        # limit to 20
        reminders = sorted(reminders, key=lambda r: r.get('days_left', r.get('days_late', 0)))
        return dict(reminder_count=len(reminders), reminder_notifications=reminders)
    except Exception:
        return dict(reminder_count=0, reminder_notifications=[])


@student_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role != 'student':
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT id, department, year FROM students WHERE user_id = ?", (current_user.id,))
    student = cur.fetchone()
    
    if not student:
        flash('Student profile not found!', 'danger')
        return redirect(url_for('auth.logout'))
    
    student_id = student['id']
    department = student['department']
    year = student['year']
    
    cur.execute("""
        SELECT a.id, a.title, a.course_name, u.first_name, u.last_name, 
               a.deadline, a.late_submission, a.penalty_per_day, a.teacher_comment,
               a.department, a.year, a.files, a.max_score
        FROM assignments a
        JOIN teachers t ON a.teacher_id = t.id
        JOIN users u ON t.user_id = u.id
        WHERE a.department = ? AND a.year = ?
        ORDER BY a.deadline ASC
    """, (department.strip(), int(year)))
    assignments = cur.fetchall()
    
    cur.execute("""
        SELECT assignment_id, status, grade, feedback
        FROM submissions WHERE student_id = ?
    """, (student_id,))
    submissions = cur.fetchall()
    submission_dict = {s[0]: s for s in submissions}
    
    total = len(assignments)
    submitted = sum(1 for a in assignments if a[0] in submission_dict)
    unsubmitted = total - submitted
    overdue = sum(1 for a in assignments if a['deadline'] and datetime.strptime(a['deadline'], '%Y-%m-%d %H:%M:%S') < datetime.now() and a[0] not in submission_dict)
    
    conn.close()
    # compute current weight (effective max value) per assignment for this student
    from math import ceil
    weights = {}
    reminders = []
    now = datetime.now()
    conn = get_db()
    cur = conn.cursor()
    for a in assignments:
        try:
            max_score = float(a['max_score']) if a['max_score'] is not None else 100.0
        except Exception:
            max_score = 100.0
        current_value = max_score
        try:
            deadline_dt = datetime.strptime(a['deadline'], '%Y-%m-%d %H:%M:%S') if a['deadline'] else None
        except Exception:
            deadline_dt = None

        if deadline_dt:
            if now > deadline_dt:
                # check allowed late for this student
                cur.execute("SELECT id FROM allowed_late_submissions WHERE assignment_id = ? AND student_id = ?", (a['id'], student_id))
                allowed = cur.fetchone() is not None
                if not allowed and a['late_submission']:
                    seconds = (now - deadline_dt).total_seconds()
                    days_late = int(ceil(seconds / 86400.0))
                    penalty = float(a['penalty_per_day']) if a['penalty_per_day'] is not None else 0.0
                    current_value = max(0.0, max_score * max(0.0, 1 - (penalty/100.0) * days_late))
                    # reminder for passed deadline but late allowed
                    reminders.append({
                        'id': a['id'],
                        'title': a['title'],
                        'deadline': deadline_dt,
                        'days_left': -days_late,
                        'late_allowed': True,
                        'penalty_per_day': penalty,
                        'current_value': current_value,
                        'max_score': max_score
                    })
                elif not allowed and not a['late_submission']:
                    current_value = 0.0
                    # passed and late not allowed => reminder as overdue
                    reminders.append({
                        'id': a['id'],
                        'title': a['title'],
                        'deadline': deadline_dt,
                        'days_left': -1,
                        'late_allowed': False,
                        'penalty_per_day': 0.0,
                        'current_value': current_value,
                        'max_score': max_score
                    })
            else:
                # deadline in future: check if <= 3 days
                seconds = (deadline_dt - now).total_seconds()
                days_left = int(ceil(seconds / 86400.0))
                if days_left <= 3:
                    reminders.append({
                        'id': a['id'],
                        'title': a['title'],
                        'deadline': deadline_dt,
                        'days_left': days_left,
                        'late_allowed': bool(a['late_submission']),
                        'penalty_per_day': float(a['penalty_per_day']) if a['penalty_per_day'] is not None else 0.0,
                        'current_value': current_value,
                        'max_score': max_score
                    })

        weights[a['id']] = current_value

    conn.close()

    return render_template('student/dashboard.html',
                         assignments=assignments,
                         submission_dict=submission_dict,
                         weights=weights,
                         reminders=reminders,
                         total=total,
                         submitted=submitted,
                         unsubmitted=unsubmitted,
                         overdue=overdue,
                         now=now)


@student_bp.route('/submit/<int:assignment_id>', methods=['GET', 'POST'])
@login_required
def submit(assignment_id):
    if current_user.role != 'student':
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT id FROM students WHERE user_id = ?", (current_user.id,))
    student = cur.fetchone()
    if not student:
        flash('Student profile not found!', 'danger')
        return redirect(url_for('student.dashboard'))
    student_id = student['id']
    
    cur.execute("""
         SELECT a.id, a.title, a.course_name, u.first_name, u.last_name,
             a.deadline, a.late_submission, a.penalty_per_day, a.teacher_comment, a.files,
             a.department, a.year, a.max_score, a.is_group, a.max_group_size
        FROM assignments a
        JOIN teachers t ON a.teacher_id = t.id
        JOIN users u ON t.user_id = u.id
        WHERE a.id = ?
    """, (assignment_id,))
    assignment = cur.fetchone()
    
    if not assignment:
        flash('Assignment not found!', 'danger')
        return redirect(url_for('student.dashboard'))

    # compute max_score and current_value early so POST error branches can render safely
    try:
        max_score = float(assignment['max_score']) if assignment['max_score'] is not None else 100.0
    except Exception:
        max_score = 100.0
    current_value = max_score
    try:
        deadline_dt = datetime.strptime(assignment['deadline'], '%Y-%m-%d %H:%M:%S') if assignment['deadline'] else None
    except Exception:
        deadline_dt = None
    if deadline_dt and datetime.now() > deadline_dt:
        # check allowed late for this student
        cur.execute("SELECT id FROM allowed_late_submissions WHERE assignment_id = ? AND student_id = ?", (assignment_id, student_id))
        allowed = cur.fetchone() is not None
        if not allowed and assignment['late_submission']:
            from math import ceil
            seconds = (datetime.now() - deadline_dt).total_seconds()
            days_late = int(ceil(seconds / 86400.0))
            penalty = float(assignment['penalty_per_day']) if assignment['penalty_per_day'] is not None else 0.0
            current_value = max(0.0, max_score * max(0.0, 1 - (penalty/100.0) * days_late))
    
    cur.execute("SELECT id, status, files, student_comment, group_id FROM submissions WHERE assignment_id = ? AND student_id = ?", 
                (assignment_id, student_id))
    existing = cur.fetchone()
    
    # prepare teammates list and selected ids for group view (also used on POST error returns)
    teammates_list = []
    current_student = None
    selected_ids = []
    if assignment and assignment['is_group']:
        cur2 = get_db().cursor()
        # fetch current student full info
        cur2.execute("SELECT st.id, u.first_name, u.last_name, u.user_id, st.year FROM students st JOIN users u ON st.user_id = u.id WHERE st.id = ?", (student_id,))
        current_student = cur2.fetchone()
        # if the student already has a submission and belongs to a group, fetch group members and mark them selected
        if existing and existing['group_id']:
            cur2.execute("SELECT s.student_id FROM submissions s WHERE s.assignment_id = ? AND s.group_id = ?", (assignment_id, existing['group_id']))
            selected_ids = [r[0] for r in cur2.fetchall()]
        # fetch other students in same dept/year who haven't submitted yet and are not the current student and not in selected_ids
        params = [assignment['department'].strip(), assignment['year'], student_id, assignment_id]
        query = """
            SELECT st.id, u.first_name, u.last_name, u.user_id, st.year
            FROM students st
            JOIN users u ON st.user_id = u.id
            WHERE st.department = ? AND st.year = ? AND st.id != ?
            AND st.id NOT IN (SELECT student_id FROM submissions WHERE assignment_id = ?)
        """
        cur2.execute(query, params)
        # combine selected members (if any) + available students
        available = cur2.fetchall()
        # ensure selected members appear first (fetch their full info)
        full_selected = []
        if selected_ids:
            placeholders = ','.join(['?'] * len(selected_ids))
            cur2.execute(f"SELECT st.id, u.first_name, u.last_name, u.user_id, st.year FROM students st JOIN users u ON st.user_id = u.id WHERE st.id IN ({placeholders})", tuple(selected_ids))
            full_selected = cur2.fetchall()
        # filter available to remove any that are in selected_ids
        if selected_ids:
            available = [r for r in available if r[0] not in selected_ids]
        teammates_list = (full_selected if full_selected else []) + available
        cur2.connection.close()

    if request.method == 'POST':
        uploaded_files = request.files.getlist('submission_files')
        file_paths = []
        for file in uploaded_files:
            if file.filename:
                filename = f"sub_{datetime.now().timestamp()}_{file.filename}"
                filepath = os.path.join(Config.UPLOAD_FOLDER, filename)
                file.save(filepath)
                file_paths.append(filename)
                uploaded_files = request.files.getlist('submission_files')
        file_paths = []
        for file in uploaded_files:
            if file.filename:
                filename = f"sub_{datetime.now().timestamp()}_{file.filename}"
                filepath = os.path.join(Config.UPLOAD_FOLDER, filename)
                file.save(filepath)
                file_paths.append(filename)
        
        files_str = ','.join(file_paths) if file_paths else (existing['files'] if existing else '')
        comment = request.form.get('comment', '').strip()
        # handle group submission
        if assignment and assignment['is_group']:
            # teammates are passed as student ids
            teammates = request.form.getlist('teammates')
            try:
                teammates = [int(t) for t in teammates if t]
            except Exception:
                teammates = []
            # ensure submitter included
            if student_id not in teammates:
                teammates.append(student_id)
            max_group = int(assignment['max_group_size']) if assignment['max_group_size'] else 2
            if len(teammates) < 2:
                flash('Group submissions require at least 2 members.', 'danger')
                conn.close()
                return render_template('student/submit.html', assignment=assignment, existing=existing, now=datetime.now(), current_value=current_value, max_score=max_score, teammates_list=teammates_list, current_student=current_student, selected_ids=selected_ids)
            if len(teammates) > max_group:
                flash(f'Group size cannot exceed {max_group}.', 'danger')
                conn.close()
                return render_template('student/submit.html', assignment=assignment, existing=existing, now=datetime.now(), current_value=current_value, max_score=max_score, teammates_list=teammates_list, current_student=current_student, selected_ids=selected_ids)
            # verify none of selected already submitted for this assignment
            placeholders = ','.join(['?'] * len(teammates))
            cur.execute(f"SELECT student_id FROM submissions WHERE assignment_id = ? AND student_id IN ({placeholders})", (assignment_id, *teammates))
            taken = [r[0] for r in cur.fetchall()]
            if taken:
                flash('One or more selected students already have a submission for this assignment.', 'danger')
                conn.close()
                return redirect(url_for('student.dashboard'))
            # determine status (same logic as individual)
            deadline = datetime.strptime(assignment['deadline'], '%Y-%m-%d %H:%M:%S') if assignment['deadline'] else datetime.now()
            has_late_permission = False
            if datetime.now() > deadline:
                cur.execute("SELECT id FROM allowed_late_submissions WHERE assignment_id = ? AND student_id = ?",
                           (assignment_id, student_id))
                has_late_permission = cur.fetchone() is not None
            if datetime.now() > deadline and has_late_permission:
                status = 'submitted'
            elif datetime.now() > deadline and not assignment['late_submission']:
                flash('Deadline passed and late submission not allowed!', 'danger')
                conn.close()
                return redirect(url_for('student.dashboard'))
            elif datetime.now() > deadline and assignment['late_submission']:
                status = 'late'
            else:
                status = 'submitted'
            # create a group token id
            group_token = int(datetime.now().timestamp() * 1000)
            now_ts = datetime.now()
            for sid in teammates:
                cur.execute("INSERT INTO submissions (assignment_id, student_id, files, student_comment, status, submitted_at, group_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (assignment_id, sid, files_str, comment, status, now_ts, group_token))
            flash('Group submission successful!', 'success')
            conn.commit()
            conn.close()
            return redirect(url_for('student.dashboard'))
        
        # NEW: Require file upload
        if not files_str and not comment:
            flash('You must upload a file or write a comment!', 'danger')
            conn.close()
            return render_template('student/submit.html', assignment=assignment, existing=existing, now=datetime.now(), current_value=current_value, max_score=max_score, teammates_list=teammates_list, current_student=current_student, selected_ids=selected_ids)
        files_str = ','.join(file_paths) if file_paths else (existing['files'] if existing else '')
        comment = request.form.get('comment', '').strip()
        deadline = datetime.strptime(assignment['deadline'], '%Y-%m-%d %H:%M:%S') if assignment['deadline'] else datetime.now()
        
        if existing:
            if existing['status'] == 'evaluated':
                flash('Cannot update: already evaluated!', 'danger')
            else:
                # allow update before evaluation; if group submission update all group members
                if assignment and assignment['is_group'] and existing['group_id']:
                    # check deadline for group
                    if deadline > datetime.now():
                        cur.execute("""
                            UPDATE submissions SET files = ?, student_comment = ?, updated_at = ? WHERE group_id = ?
                        """, (files_str, comment, datetime.now(), existing['group_id']))
                        flash('Group submission updated!', 'success')
                    else:
                        flash('Cannot update: deadline passed!', 'danger')
                else:
                    if deadline > datetime.now():
                        cur.execute("""
                            UPDATE submissions SET files = ?, student_comment = ?, updated_at = ?
                            WHERE id = ?
                        """, (files_str, comment, datetime.now(), existing['id']))
                        flash('Submission updated!', 'success')
                    else:
                        flash('Cannot update: deadline passed!', 'danger')
        else:
            has_late_permission = False
            if datetime.now() > deadline:
                cur.execute("SELECT id FROM allowed_late_submissions WHERE assignment_id = ? AND student_id = ?",
                           (assignment_id, student_id))
                has_late_permission = cur.fetchone() is not None
            
            if datetime.now() > deadline and has_late_permission:
                status = 'submitted'
            elif datetime.now() > deadline and not assignment['late_submission']:
                flash('Deadline passed and late submission not allowed!', 'danger')
                conn.close()
                return redirect(url_for('student.dashboard'))
            elif datetime.now() > deadline and assignment['late_submission']:
                status = 'late'
            else:
                status = 'submitted'
            
            cur.execute("""
                INSERT INTO submissions (assignment_id, student_id, files, student_comment, status)
                VALUES (?, ?, ?, ?, ?)
            """, (assignment_id, student_id, files_str, comment, status))
            flash('Submission successful!', 'success')
        
        conn.commit()
        conn.close()
        return redirect(url_for('student.dashboard'))
    
    conn.close()
    # compute current effective max value for display
    max_score = float(assignment['max_score']) if assignment['max_score'] is not None else 100.0
    current_value = max_score
    try:
        deadline_dt = datetime.strptime(assignment['deadline'], '%Y-%m-%d %H:%M:%S') if assignment['deadline'] else None
    except Exception:
        deadline_dt = None

    if datetime.now() > deadline_dt:
        # check allowed late
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id FROM allowed_late_submissions WHERE assignment_id = ? AND student_id = ?", (assignment_id, student_id))
        allowed = cur.fetchone() is not None
        conn.close()
        if not allowed and assignment['late_submission']:
            from math import ceil
            seconds = (datetime.now() - deadline_dt).total_seconds()
            days_late = int(ceil(seconds / 86400.0))
            penalty = float(assignment['penalty_per_day']) if assignment['penalty_per_day'] is not None else 0.0
            current_value = max(0.0, max_score * max(0.0, 1 - (penalty/100.0) * days_late))

    return render_template('student/submit.html',
                         assignment=assignment,
                         existing=existing,
                         now=datetime.now(),
                         current_value=current_value,
                         max_score=max_score,
                         teammates_list=teammates_list,
                         current_student=current_student,
                         selected_ids=selected_ids)



@student_bp.route('/grades')
@login_required
def grades():
    if current_user.role != 'student':
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT id FROM students WHERE user_id = ?", (current_user.id,))
    student = cur.fetchone()
    if not student:
        return redirect(url_for('student.dashboard'))
    student_id = student['id']
    
    cur.execute("""
        SELECT a.title, a.course_name, u.first_name, u.last_name,
               s.grade, s.feedback, s.status, s.submitted_at, s.id as submission_id,
               s.complaint, s.complaint_status, a.max_score, a.penalty_per_day, a.deadline
        FROM submissions s
        JOIN assignments a ON s.assignment_id = a.id
        JOIN teachers t ON a.teacher_id = t.id
        JOIN users u ON t.user_id = u.id
        WHERE s.student_id = ?
        ORDER BY s.submitted_at DESC
    """, (student_id,))
    grades = cur.fetchall()
    # compute effective max for each grade entry
    processed = []
    from math import ceil
    for g in grades:
        max_score = float(g['max_score']) if g['max_score'] is not None else 100.0
        eff = max_score
        try:
            submitted_at = datetime.strptime(g['submitted_at'], '%Y-%m-%d %H:%M:%S') if g['submitted_at'] else None
            deadline_dt = datetime.strptime(g['deadline'], '%Y-%m-%d %H:%M:%S') if g['deadline'] else None
        except Exception:
            submitted_at = None
            deadline_dt = None
        if submitted_at and deadline_dt and submitted_at > deadline_dt:
            seconds = (submitted_at - deadline_dt).total_seconds()
            days_late = int(ceil(seconds / 86400.0))
            # check allowed late
            cur2 = conn.cursor()
            cur2.execute("SELECT id FROM allowed_late_submissions WHERE assignment_id = (SELECT id FROM assignments WHERE title = ? AND course_name = ?) LIMIT 1", (g['title'], g['course_name']))
            allowed = cur2.fetchone() is not None
            if not allowed:
                penalty = float(g['penalty_per_day']) if g['penalty_per_day'] is not None else 0.0
                eff = max(0.0, max_score * max(0.0, 1 - (penalty/100.0) * days_late))
        # append effective max as extra field (index 11)
        processed.append((g[0], g[1], g[2], g[3], g[4], g[5], g[6], g[7], g[8], g[9], g[10], eff))

    conn.close()

    return render_template('student/grades.html', grades=processed)


@student_bp.route('/complain/<int:submission_id>', methods=['POST'])
@login_required
def complain(submission_id):
    if current_user.role != 'student':
        return redirect(url_for('auth.login'))
    
    complaint = request.form.get('complaint', '').strip()
    
    if not complaint:
        flash('Please provide a reason!', 'danger')
        return redirect(url_for('student.grades'))
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE submissions SET complaint = ?, complaint_status = 'pending'
        WHERE id = ?
    """, (complaint, submission_id))
    conn.commit()
    conn.close()
    
    flash('Complaint submitted!', 'success')
    return redirect(url_for('student.grades'))
