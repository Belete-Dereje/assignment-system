# Distributed Assignment Submission & Evaluation System

This is a distributed web application for assignment submission, evaluation, and user management. The system is designed to run on three computers connected through Zerotier, with each node keeping a local SQLite database and syncing data with another node every 5 seconds.

## What The System Does

- Students register, log in, view assignments, and submit files.
- Teachers create assignments, review submissions, grade work, and manage late submissions.
- Admins approve teachers, manage users, and control system settings.
- Each machine runs the same Flask application and keeps its own local copy of the database.
- The sync script exchanges data between nodes so the databases stay aligned.

## Distributed Setup

The intended deployment is:

- 3 computers acting as nodes in the same Zerotier network.
- One Flask app running on each computer.
- SQLite as the local database on each node.
- A sync process that pulls data from a peer node and updates the local node every 5 seconds.
- Optional reverse proxy or load balancer in front of the app if you want a shared public entry point.

Important note: the current sync script is a simple peer-to-peer copy process, not a conflict-resolution engine. If two nodes change the same record at the same time, the last synced data can overwrite earlier changes.

## Installation

### 1. Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. Install the Python packages

```bash
pip install Flask Flask-Login requests
```

Optional, only if you plan to work with the SQLAlchemy models in `models.py`:

```bash
pip install Flask-SQLAlchemy
```

### 3. Make sure the upload folder exists

The application uses `static/uploads/` to store uploaded assignment and submission files. The app creates it automatically when it starts, but you can also create it manually if needed.

### 4. Prepare the database

The first time you run the app, it creates `assignments.db` automatically and builds the required tables.

## Running The System

### Start the main web app

```bash
python app.py
```

The app runs on `0.0.0.0:5000` in debug mode with threaded requests enabled.

### Start synchronization

Run the sync script on each node and point it to another node that is reachable over Zerotier:

```bash
python sync.py <other-node-ip>:5000
```

Example:

```bash
python sync.py 10.49.210.216:5000
```

## Default Access

Default admin account:

- User ID: `ADMIN001`
- Email: `admin@system.com`
- Password: `admin123`

## Project Structure

### Root files

- `app.py` - Main Flask entry point. Creates the app, initializes the database, registers blueprints, and exposes the sync endpoints `/sync/data` and `/sync/update`.
- `auth.py` - Handles registration, login, logout, and Flask-Login user loading.
- `config.py` - Application configuration such as `SECRET_KEY`, SQLite database path, and upload folder path.
- `models.py` - SQLAlchemy model definitions for users, students, teachers, assignments, submissions, and late submission approvals. This is a model layer for ORM-based work.
- `routes_admin.py` - Admin dashboard and user-management routes.
- `routes_teacher.py` - Teacher dashboard, assignment creation/editing, submission review, grading, and late-submission management.
- `routes_student.py` - Student dashboard, reminders, assignment submission, and grade viewing.
- `sync.py` - Small synchronization client that copies data from a peer node to the local database every 5 seconds.
- `assignments.db` - Local SQLite database file created at runtime.
- `README.md` - Project documentation.

### `templates/`

Base layout and page templates for the web interface.

- `templates/landing.html` - Public landing page.
- `templates/login.html` - Login page.
- `templates/register.html` - Registration page.
- `templates/admin_base.html` - Base layout for admin pages.
- `templates/student_base.html` - Base layout for student pages.
- `templates/teacher_base.html` - Base layout for teacher pages.
- `templates/admin/` - Admin-specific pages.
- `templates/student/` - Student-specific pages.
- `templates/teacher/` - Teacher-specific pages.

### `templates/admin/`

- `dashboard.html` - Admin dashboard with counts, pending teachers, and settings.
- `edit_user.html` - Edit user details and profile data.
- `settings.html` - System settings page.
- `users.html` - User list and filters.

### `templates/student/`

- `dashboard.html` - Student dashboard with assignments, reminders, and submission status.
- `grades.html` - Student grade and feedback page.
- `submit.html` - Submission form for assignment uploads.

### `templates/teacher/`

- `create_assignment.html` - Form for creating new assignments.
- `dashboard.html` - Teacher dashboard with assignment and submission overview.
- `edit_assignment.html` - Edit assignment details.
- `evaluate.html` - Submission evaluation and grading page.
- `submissions.html` - Assignment submission list and late-submission management.

### `static/`

- `static/uploads/` - Stores uploaded assignment files and submitted files.

### Generated and environment folders

- `.git/` - Git version control metadata.
- `__pycache__/` - Python bytecode cache files.
- `venv/` - Local Python virtual environment.

## How The Sync Works

The app exposes these endpoints:

- `GET /sync/data` - Returns the current table data as JSON.
- `POST /sync/update` - Replaces local table data with the received JSON payload.

The sync client in `sync.py`:

1. Reads data from the peer node.
2. Sends that data to the local node.
3. Waits 5 seconds.
4. Repeats the process.

## Notes

- The application currently uses direct SQLite access in the route files.
- `models.py` is present for SQLAlchemy-based structure, but the running app does not depend on it for the main request flow.
- Uploaded files are saved in `static/uploads/` and are named with timestamps to reduce filename collisions.


