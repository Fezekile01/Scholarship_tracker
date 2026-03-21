import os
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, session
from sqlalchemy import or_
from werkzeug.utils import secure_filename
from models import db, User, Student, Admin, Scholarship, Application, Notification, Document, ProfileDocument

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///scholarship_tracker.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'mysecretkey'
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
db.init_app(app)




@app.route("/")
def index():
    scholarships = Scholarship.query.filter_by(status='Open').all()
    return render_template('index.html', scholarships=scholarships)
# -----------------------------
# HOME ROUTE
# -----------------------------

@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if session.get('role') == 'admin':
        return redirect(url_for('admin_dashboard'))

    return redirect(url_for('student_dashboard'))


# -----------------------------
# REGISTER STUDENT
# -----------------------------

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form['full_name']
        email = request.form['email']
        password = request.form['password']
        # Catch the department from the dropdown
        selected_dept = request.form['course'] 

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return "Email already exists. Please use another email."

        # Create the base User
        new_user = User(
            full_name=full_name,
            email=email,
            password_hash=password, # Note: In a real app, use werkzeug.security to hash this!
            role='student'
        )

        db.session.add(new_user)
        db.session.commit()

        # Create the Student profile and link the department/course
        new_student = Student(
            user_id=new_user.id,
            course=selected_dept  # This maps to the 'department' column in your Student model
        )
        db.session.add(new_student)
        db.session.commit()

        return redirect(url_for('login'))

    return render_template('register.html')


# -----------------------------
# LOGIN
# -----------------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        consent = request.form['consent']

        user = User.query.filter_by(email=email).first()
      if not consent:
            error = "You must accept the Privacy Policy"
            return render_template('login.html', error=error)

        if user and user.password_hash == password:
            session['user_id'] = user.id
            session['user_name'] = user.full_name
            session['role'] = user.role

            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))

            return redirect(url_for('student_dashboard'))

        error = "Invalid email or password"

    return render_template('login.html', error=error)


# -----------------------------
# STUDENT DASHBOARD
# -----------------------------

@app.route('/student_dashboard')
def student_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if session.get('role') != 'student':
        return "Access denied"

    student = Student.query.filter_by(user_id=session['user_id']).first()

    return render_template(
        'student_dashboard.html',
        name=session.get('user_name'),
        student=student
    )


# -----------------------------
# STUDENT: VIEW & APPLY TO SCHOLARSHIPS
# -----------------------------

@app.route('/student/scholarships')
def student_scholarships():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    student = Student.query.filter_by(user_id=session['user_id']).first()
    student_dept = student.course 

   
    scholarships = Scholarship.query.filter(
        Scholarship.status != 'Closed',
        Scholarship.department == student_dept
    ).all()

    existing_applications = {app.scholarship_id for app in student.applications}

    return render_template(
        'student_scholarships.html',
        scholarships=scholarships,
        existing_applications=existing_applications,
        message=request.args.get('message')
    
    )


@app.route('/apply/<int:scholarship_id>', methods=['POST'])
def apply_scholarship(scholarship_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if session.get('role') != 'student':
        return "Access denied"

    student = Student.query.filter_by(user_id=session['user_id']).first_or_404()
    scholarship = Scholarship.query.get_or_404(scholarship_id)

    existing_application = Application.query.filter_by(
        student_id=student.id,
        scholarship_id=scholarship.id
    ).first()

    if existing_application:
        return redirect(url_for(
            'student_scholarships',
            message='You have already applied for this scholarship.'
        ))

    new_application = Application(
        student_id=student.id,
        scholarship_id=scholarship.id,
        status='Submitted'
    )
    db.session.add(new_application)
    db.session.commit()

    return redirect(url_for(
        'track_applications',
        message='Application submitted successfully.'
    ))

# -----------------------------
# STUDENT: TRACK APPLICATIONS
# -----------------------------

@app.route('/student/applications')
def track_applications():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if session.get('role') != 'student':
        return "Access denied"

    student = Student.query.filter_by(user_id=session['user_id']).first()
    applications = Application.query.filter_by(student_id=student.id).all()

    return render_template(
        'track_applications.html',
        applications=applications,
        message=request.args.get('message')
    )

# -----------------------------
# STUDENT: UPLOAD DOCUMENTS
# -----------------------------

def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {
        'pdf', 'png', 'jpg', 'jpeg', 'doc', 'docx'
    }


@app.route('/upload_documents', methods=['GET', 'POST'])
def upload_documents():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if session.get('role') != 'student':
        return "Access denied"

    student = Student.query.filter_by(user_id=session['user_id']).first()
    message = None

    if request.method == 'POST':
        file = request.files.get('document')

        if not file or file.filename == '':
            message = 'Please choose a file to upload.'
        elif not _allowed_file(file.filename):
            message = 'File type not supported. Use PDF, DOC/DOCX or images.'
        else:
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            safe_name = secure_filename(file.filename)
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_name)
            file.save(save_path)

            new_doc = Document(
                student_id=student.id,
                filename=safe_name,
                filepath=save_path
            )
            db.session.add(new_doc)
            db.session.commit()

            return redirect(url_for(
                'upload_documents',
                message='Document uploaded successfully.'
            ))

    documents = Document.query.filter_by(student_id=student.id).order_by(Document.uploaded_at.desc()).all()

    return render_template(
        'upload_documents.html',
        documents=documents,
        message=message or request.args.get('message')
    )

# -----------------------------
# STUDENT PROFILE
# -----------------------------

REQUIRED_DOC_TYPES = {
    'certified_id': 'Certified ID (under 3 months old)',
    'academic_record': 'Recent academic record / matric results',
    'income_proof': 'Proof of income (parents/guardians) or affidavit',
    'motivational_letter': 'Motivational letter'
}


def _save_profile_document(student, file, doc_type, certified_date=None):
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    base_name = secure_filename(file.filename)
    filename = f"{doc_type}_{student.id}_{base_name}"
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(save_path)

    # replace existing doc of same type
    existing = ProfileDocument.query.filter_by(student_id=student.id, doc_type=doc_type).first()
    if existing and os.path.exists(existing.filepath):
        try:
            os.remove(existing.filepath)
        except OSError:
            pass
        db.session.delete(existing)
        db.session.commit()

    new_doc = ProfileDocument(
        student_id=student.id,
        doc_type=doc_type,
        filename=filename,
        filepath=save_path,
        certified_date=certified_date
    )
    db.session.add(new_doc)
    db.session.commit()


@app.route('/student/profile', methods=['GET', 'POST'])
def student_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if session.get('role') != 'student':
        return "Access denied"

    student = Student.query.filter_by(user_id=session['user_id']).first_or_404()
    message = None
    error = None

    if request.method == 'POST':
        form_type = request.form.get('form_type')

        if form_type == 'info':
            student.student_number = request.form.get('student_number') or None
            student.course = request.form.get('course') or None
            student.year_level = request.form.get('year_level') or None
            db.session.commit()
            message = 'Profile information updated.'

        elif form_type == 'doc_upload':
            doc_type = request.form.get('doc_type')
            file = request.files.get('document')
            certified_date_val = request.form.get('certified_date')

            if doc_type not in REQUIRED_DOC_TYPES:
                error = 'Unsupported document type.'
            elif not file or file.filename == '':
                error = 'Please choose a file to upload.'
            elif not _allowed_file(file.filename):
                error = 'File type not supported. Use PDF, DOC/DOCX or images.'
            else:
                certified_date = None
                if doc_type == 'certified_id':
                    if not certified_date_val:
                        error = 'Please provide the certification date for your ID.'
                    else:
                        try:
                            certified_date = datetime.strptime(certified_date_val, '%Y-%m-%d').date()
                            age_days = (datetime.utcnow().date() - certified_date).days
                            if age_days > 90:
                                error = 'Certified ID must be no older than 3 months.'
                        except ValueError:
                            error = 'Invalid date format.'

                if not error:
                    _save_profile_document(student, file, doc_type, certified_date)
                    message = f"{REQUIRED_DOC_TYPES[doc_type]} uploaded."

    docs = {d.doc_type: d for d in ProfileDocument.query.filter_by(student_id=student.id).all()}

    return render_template(
        'student_profile.html',
        student=student,
        docs=docs,
        required_docs=REQUIRED_DOC_TYPES,
        message=message,
        error=error
    )


# -----------------------------
# STUDENT: NOTIFICATIONS
# -----------------------------

@app.route('/student_notifications')
def student_notifications():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if session.get('role') != 'student':
        return "Access denied"

    student = Student.query.filter_by(user_id=session['user_id']).first()
    targeted_role = f"student:{student.id}" if student else None
    notifications = Notification.query.filter(
        or_(
            Notification.recipient_role == 'student',
            Notification.recipient_role == targeted_role
        )
    ).all()
    return render_template(
        'student_notifications.html',
        notifications=notifications
    )
# -----------------------------
# ADMIN DASHBOARD
# -----------------------------

@app.route('/admin_dashboard')
def admin_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if session.get('role') != 'admin':
        return "Access denied"

    admin = Admin.query.filter_by(user_id=session['user_id']).first()

    return render_template(
        'admin_dashboard.html',
        name=session.get('user_name'),
        admin=admin
    )


# -----------------------------
# CREATE SCHOLARSHIP (ADMIN)
# -----------------------------

@app.route('/create_scholarship', methods=['GET', 'POST'])
def create_scholarship():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if session.get('role') != 'admin':
        return "Access denied"

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        requirements = request.form['requirements']
        deadline = request.form['deadline']
        status = request.form['status']

        new_scholarship = Scholarship(
            title=title,
            description=description,
            requirements=requirements,
            deadline=deadline,
            status=status
        )

        db.session.add(new_scholarship)
        db.session.commit()

        return redirect(url_for('admin_scholarships'))

    return render_template('create_scholarship.html')


# -----------------------------
# VIEW SCHOLARSHIPS
# -----------------------------
# -----------------------------
# EDIT SCHOLARSHIP (ADMIN)
# -----------------------------

@app.route('/edit_scholarship/<int:id>', methods=['GET', 'POST'])
def edit_scholarship(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if session.get('role') != 'admin':
        return "Access denied"

    scholarship = Scholarship.query.get_or_404(id)

    if request.method == 'POST':
        scholarship.title = request.form['title']
        scholarship.description = request.form['description']
        scholarship.requirements = request.form['requirements']
        scholarship.deadline = request.form['deadline']
        scholarship.status = request.form['status']

        db.session.commit()

        return redirect(url_for('admin_scholarships'))

    return render_template('edit_scholarship.html', scholarship=scholarship)
@app.route('/view_scholarships')
def view_scholarships():
    return redirect(url_for('admin_scholarships'))


# -----------------------------
# ADMIN: COMBINED SCHOLARSHIPS PAGE
# -----------------------------

"""
Auto-close deadlines and manage/create scholarships in one page.
"""


def _refresh_scholarship_statuses():
    today = datetime.utcnow().date()
    changed = False
    for s in Scholarship.query.all():
        try:
            deadline_date = datetime.strptime(s.deadline, '%Y-%m-%d').date()
            if deadline_date < today and s.status != 'Closed':
                s.status = 'Closed'
                changed = True
        except ValueError:
            continue
    if changed:
        db.session.commit()


@app.route('/admin/scholarships', methods=['GET', 'POST'])
def admin_scholarships():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if session.get('role') != 'admin':
        return "Access denied"

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        requirements = request.form['requirements']
        deadline = request.form['deadline']
        status = request.form['status']
        dept_code = request.form.get('department')

       

        new_scholarship = Scholarship(
            title=title,
            description=description,
            requirements=requirements,
            deadline=deadline,
            status=status,
            department=dept_code
            
        )
        db.session.add(new_scholarship)
        db.session.commit()
        return redirect(url_for('admin_scholarships'))

    _refresh_scholarship_statuses()
    scholarships = Scholarship.query.all()
    return render_template('admin_scholarships.html', scholarships=scholarships)


# -----------------------------
# VIEW APPLICATIONS (ADMIN)
# -----------------------------

@app.route('/view_applications')
def view_applications():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if session.get('role') != 'admin':
        return "Access denied"

    applications = Application.query.filter_by(status='Submitted').all()
    return render_template('view_applications.html', applications=applications)


@app.route('/applications/<int:app_id>/under_review', methods=['POST'])
def mark_under_review(app_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if session.get('role') != 'admin':
        return "Access denied"

    application = Application.query.get_or_404(app_id)
    application.status = 'Under Review'
    db.session.commit()
    return redirect(url_for('view_applications'))
@app.route('/admin/applications/review')
def approve_reject():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if session.get('role') != 'admin':
        return "Access denied"

    applications = Application.query.filter_by(status='Under Review').all()
    return render_template('approve_reject.html', applications=applications)


@app.route('/applications/<int:app_id>/decision', methods=['POST'])
def application_decision(app_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if session.get('role') != 'admin':
        return "Access denied"

    application = Application.query.get_or_404(app_id)
    decision = request.form.get('decision')
    if decision == 'approve':
        application.status = 'Approved'
    elif decision == 'reject':
        application.status = 'Rejected'
    db.session.commit()
    return redirect(url_for('approve_reject'))

# -----------------------------
# ADMIN: REQUEST MISSING DOCUMENTS
# -----------------------------

def _missing_profile_docs(student):
    docs = {d.doc_type: d for d in ProfileDocument.query.filter_by(student_id=student.id).all()}
    missing = []
    for key, label in REQUIRED_DOC_TYPES.items():
        doc = docs.get(key)
        if not doc:
            missing.append(f"Missing: {label}")
        elif key == 'certified_id':
            if doc.certified_date:
                age_days = (datetime.utcnow().date() - doc.certified_date).days
                if age_days > 90:
                    missing.append("Certified ID expired (older than 3 months)")
            else:
                missing.append("Certified ID certification date not provided")
    return missing


@app.route('/admin/missing_documents', methods=['GET', 'POST'])
def admin_missing_documents():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if session.get('role') != 'admin':
        return "Access denied"

    message = None
    if request.method == 'POST':
        student_id = request.form.get('student_id')
        note = (request.form.get('note') or "").strip()
        student = Student.query.get(student_id)
        if student:
            text = note or "Please upload or update your required documents."
            text = f"{student.user.full_name}: {text}"
            targeted_role = f"student:{student.id}"
            notif = Notification(message=text, recipient_role=targeted_role)
            db.session.add(notif)
            db.session.commit()
            message = "Student notified."

    students = Student.query.all()
    flagged = []
    for s in students:
        missing = _missing_profile_docs(s)
        if missing:
            flagged.append({'student': s, 'user': s.user, 'missing': missing})

    return render_template('admin_missing_documents.html', flagged=flagged, message=message)

# -----------------------------
# ADMIN: MANAGE STUDENTS
# -----------------------------

@app.route('/admin/students')
def manage_students():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if session.get('role') != 'admin':
        return "Access denied"

    students = Student.query.all()
    profile_docs = {d.student_id: d for d in ProfileDocument.query.all()}
    return render_template('admin_manage_students.html', students=students, profile_docs=profile_docs)
# -----------------------------
# ADMIN NOTIFICATIONS
# -----------------------------

@app.route('/admin_notifications')
def admin_notifications():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if session.get('role') != 'admin':
        return "Access denied"

    notifications = Notification.query.filter_by(recipient_role='admin').all()
    return render_template('admin_notifications.html', notifications=notifications)


# -----------------------------
# LOGOUT
# -----------------------------

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# -----------------------------
# RUN APPLICATION
# -----------------------------

if __name__ == '__main__':
    with app.app_context():
        db.create_all()

        # Create default admin if not existing
        admin_user = User.query.filter_by(email='admin@example.com').first()
        if not admin_user:
            admin_user = User(
                full_name='Admin User',
                email='admin@example.com',
                password_hash='admin123',
                role='admin'
            )
            db.session.add(admin_user)
            db.session.commit()

            admin_profile = Admin(
                user_id=admin_user.id,
                staff_number='ADM001',
                department='Financial Aid'
            )
            db.session.add(admin_profile)
            db.session.commit()

    app.run(debug=True)


















