from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from datetime import datetime
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import os

# Import SMS helper
from utils.sms_helper import send_camp_registration_notification, check_sms_configured, send_sms

app = Flask(__name__)
app.config.from_object('config.Config')

# Import db from models
from models.models import db, Patient, Doctor, Appointment, MedicalCamp, Settings
db.init_app(app)

# Create database tables and handle migrations
with app.app_context():
    db.create_all()
    
    # Add 'time' column to medical_camp if it doesn't exist
    try:
        from sqlalchemy import text
        db.session.execute(text("SELECT time FROM medical_camp LIMIT 1"))
    except:
        try:
            db.session.execute(text("ALTER TABLE medical_camp ADD COLUMN time VARCHAR(20)"))
            db.session.commit()
        except:
            pass
    
    # Initialize default settings if not exist
    if not Settings.query.filter_by(key='theme').first():
        db.session.add(Settings(key='theme', value='light'))
        db.session.add(Settings(key='hospital_name', value='Medical Camp Center'))
        db.session.add(Settings(key='contact', value='+1 234 567 890'))
        db.session.commit()

# ============ Helper Functions ============
def get_setting(key, default=''):
    setting = Settings.query.filter_by(key=key).first()
    return setting.value if setting else default

# ============ Routes ============

@app.route('/')
def index():
    return render_template('index.html')

# ============ Login Routes ============
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_type = request.form.get('login_type')
        
        if login_type == 'admin':
            admin_name = request.form.get('adminname')
            password = request.form.get('password')
            if admin_name == 'admin' and password == 'admin123':
                return redirect(url_for('admin_dashboard'))
            else:
                flash('Invalid Admin Credentials!', 'danger')
        
        elif login_type == 'user':
            username = request.form.get('username')
            password = request.form.get('password')
            if username == 'user' and password == '123':
                return redirect(url_for('user_dashboard'))
            else:
                flash('Invalid User Credentials!', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    return redirect(url_for('index'))

# ============ User Dashboard ============
@app.route('/user_dashboard')
def user_dashboard():
    doctors = Doctor.query.all()
    return render_template('user_dashboard.html', doctors=doctors)

# ============ Admin Dashboard ============
@app.route('/admin_dashboard')
def admin_dashboard():
    total_patients = Patient.query.count()
    total_doctors = Doctor.query.count()
    total_appointments = Appointment.query.count()
    total_camps = MedicalCamp.query.count()
    
    today = datetime.now().strftime('%Y-%m-%d')
    today_appointments = Appointment.query.filter_by(date=today).count()
    
    theme = get_setting('theme', 'light')
    hospital_name = get_setting('hospital_name', 'Medical Camp Center')
    contact = get_setting('contact', '+1 234 567 890')
    
    return render_template('admin_dashboard.html', 
                           total_patients=total_patients,
                           total_doctors=total_doctors,
                           total_appointments=total_appointments,
                           total_camps=total_camps,
                           today_appointments=today_appointments,
                           theme=theme,
                           hospital_name=hospital_name,
                           contact=contact)

# ============ Patient Management ============
@app.route('/patients', methods=['GET', 'POST'])
def patients():
    # Get all upcoming camps for registration
    camps = MedicalCamp.query.filter_by(status='Upcoming').all()
    
    if request.method == 'POST':
        search = request.form.get('search')
        if search:
            patients_list = Patient.query.filter(Patient.name.contains(search)).all()
        else:
            patients_list = Patient.query.all()
    else:
        patients_list = Patient.query.all()
    
    theme = get_setting('theme', 'light')
    return render_template('patients.html', patients=patients_list, theme=theme, camps=camps)

@app.route('/register_patient')
def register_patient():
    """Display patient registration form with available camps"""
    camps = MedicalCamp.query.filter_by(status='Upcoming').all()
    theme = get_setting('theme', 'light')
    return render_template('register_patient.html', camps=camps, theme=theme)

@app.route('/add_patient', methods=['POST'])
def add_patient():
    if request.method == 'POST':
        patient = Patient(
            name=request.form.get('name'),
            age=request.form.get('age'),
            gender=request.form.get('gender'),
            phone=request.form.get('phone'),
            disease=request.form.get('disease'),
            doctor=request.form.get('doctor'),
            appointment_date=request.form.get('appointment_date'),
            created_at=datetime.now().strftime('%Y-%m-%d %H:%M')
        )
        db.session.add(patient)
        db.session.commit()
        
        # Send SMS notification if medical camp is selected
        medical_camp_id = request.form.get('medical_camp')
        if medical_camp_id:
            camp = MedicalCamp.query.get(medical_camp_id)
            if camp:
                # Get SMS credentials from settings
                account_sid = get_setting('sms_account_sid', '')
                auth_token = get_setting('sms_auth_token', '')
                from_number = get_setting('sms_from_number', '')
                
                # Send SMS notification
                if account_sid and auth_token and from_number:
                    success, message = send_camp_registration_notification(
                        patient_name=patient.name,
                        patient_phone=patient.phone,
                        camp_name=camp.name,
                        camp_location=camp.location,
                        camp_date=camp.date,
                        camp_time=camp.time or 'Not specified',
                        account_sid=account_sid,
                        auth_token=auth_token,
                        from_number=from_number
                    )
                    if success:
                        flash(f'Patient registered and SMS notification sent!', 'success')
                    else:
                        flash(f'Patient registered but SMS failed: {message}', 'warning')
                else:
                    flash('Patient registered! SMS not configured - please configure Twilio credentials in settings.', 'info')
        else:
            flash('Patient added successfully!', 'success')
    
    return redirect(url_for('patients'))

@app.route('/edit_patient/<int:id>', methods=['GET', 'POST'])
def edit_patient(id):
    patient = Patient.query.get_or_404(id)
    if request.method == 'POST':
        patient.name = request.form.get('name')
        patient.age = request.form.get('age')
        patient.gender = request.form.get('gender')
        patient.phone = request.form.get('phone')
        patient.disease = request.form.get('disease')
        patient.doctor = request.form.get('doctor')
        patient.appointment_date = request.form.get('appointment_date')
        db.session.commit()
        flash('Patient updated successfully!', 'success')
        return redirect(url_for('patients'))
    return render_template('edit_patient.html', patient=patient)

@app.route('/delete_patient/<int:id>')
def delete_patient(id):
    patient = Patient.query.get_or_404(id)
    db.session.delete(patient)
    db.session.commit()
    flash('Patient deleted successfully!', 'success')
    return redirect(url_for('patients'))

# ============ Doctor Management ============
@app.route('/doctors', methods=['GET', 'POST'])
def doctors():
    if request.method == 'POST':
        doctor = Doctor(
            name=request.form.get('name'),
            specialization=request.form.get('specialization'),
            experience=request.form.get('experience'),
            contact=request.form.get('contact'),
            created_at=datetime.now().strftime('%Y-%m-%d %H:%M')
        )
        db.session.add(doctor)
        db.session.commit()
        flash('Doctor added successfully!', 'success')
    
    doctors_list = Doctor.query.all()
    theme = get_setting('theme', 'light')
    return render_template('doctors.html', doctors=doctors_list, theme=theme)

@app.route('/delete_doctor/<int:id>')
def delete_doctor(id):
    doctor = Doctor.query.get_or_404(id)
    db.session.delete(doctor)
    db.session.commit()
    flash('Doctor deleted successfully!', 'success')
    return redirect(url_for('doctors'))

# ============ Appointment Management ============
@app.route('/appointments', methods=['GET', 'POST'])
def appointments():
    if request.method == 'POST':
        patient_phone = request.form.get('patient_phone', '').strip()
        
        appointment = Appointment(
            patient_name=request.form.get('patient_name'),
            patient_phone=patient_phone,
            doctor_name=request.form.get('doctor_name'),
            date=request.form.get('date'),
            time=request.form.get('time'),
            status='Pending',
            created_at=datetime.now().strftime('%Y-%m-%d %H:%M')
        )
        db.session.add(appointment)
        db.session.commit()
        
        # Send Twilio SMS notification
        if patient_phone:
            # Simple +91 validation (starts with 6-9 or has +91)
            if len(patient_phone) >= 10 and (patient_phone.startswith('9') or patient_phone.startswith('8') or patient_phone.startswith('7') or patient_phone.startswith('6') or '+91' in patient_phone):
                account_sid = get_setting('sms_account_sid', '')
                auth_token = get_setting('sms_auth_token', '')
                from_number = get_setting('sms_from_number', '')
                
                if account_sid and auth_token and from_number:
                    message = f"Hello {request.form.get('patient_name')}, your appointment with {request.form.get('doctor_name')} is confirmed on {request.form.get('date')}. Thank you."
                    success, sms_msg = send_sms(patient_phone, message, account_sid, auth_token, from_number)
                    if success:
                        flash('Appointment booked and SMS notification sent successfully!', 'success')
                    else:
                        flash(f'Appointment booked but SMS failed: {sms_msg}', 'warning')
                else:
                    flash('Appointment booked! Configure Twilio in Settings to enable SMS.', 'info')
            else:
                flash('Appointment booked! Please use valid Indian mobile (+91xxxxxxxxxx) for SMS next time.', 'warning')
        else:
            flash('Appointment booked successfully!', 'success')
    
    appointments_list = Appointment.query.order_by(Appointment.date.desc()).all()
    doctors = Doctor.query.all()
    theme = get_setting('theme', 'light')
    return render_template('appointments.html', appointments=appointments_list, doctors=doctors, theme=theme)

@app.route('/today_appointments')
def today_appointments():
    today = datetime.now().strftime('%Y-%m-%d')
    appointments_list = Appointment.query.filter_by(date=today).all()
    theme = get_setting('theme', 'light')
    return render_template('today_appointments.html', appointments=appointments_list, theme=theme)

@app.route('/delete_appointment/<int:id>')
def delete_appointment(id):
    appointment = Appointment.query.get_or_404(id)
    db.session.delete(appointment)
    db.session.commit()
    flash('Appointment deleted successfully!', 'success')
    return redirect(url_for('appointments'))

@app.route('/update_appointment_status/<int:id>/<status>')
def update_appointment_status(id, status):
    appointment = Appointment.query.get_or_404(id)
    appointment.status = status
    db.session.commit()
    flash(f'Appointment {status}!', 'success')
    return redirect(url_for('appointments'))

# ============ Medical Camp Management ============
@app.route('/medical_camps', methods=['GET', 'POST'])
def medical_camps():
    if request.method == 'POST':
        camp = MedicalCamp(
            name=request.form.get('name'),
            location=request.form.get('location'),
            date=request.form.get('date'),
            time=request.form.get('time'),
            doctor_in_charge=request.form.get('doctor_in_charge'),
            description=request.form.get('description'),
            status=request.form.get('status'),
            created_at=datetime.now().strftime('%Y-%m-%d %H:%M')
        )
        db.session.add(camp)
        db.session.commit()
        flash('Medical camp added successfully!', 'success')
    
    camps = MedicalCamp.query.order_by(MedicalCamp.date.desc()).all()
    doctors = Doctor.query.all()
    theme = get_setting('theme', 'light')
    return render_template('medical_camps.html', camps=camps, doctors=doctors, theme=theme)

@app.route('/delete_camp/<int:id>')
def delete_camp(id):
    camp = MedicalCamp.query.get_or_404(id)
    db.session.delete(camp)
    db.session.commit()
    flash('Medical camp deleted successfully!', 'success')
    return redirect(url_for('medical_camps'))

# ============ Settings ============
@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        theme = request.form.get('theme')
        hospital_name = request.form.get('hospital_name')
        contact = request.form.get('contact')
        
        # SMS Settings
        sms_account_sid = request.form.get('sms_account_sid', '')
        sms_auth_token = request.form.get('sms_auth_token', '')
        sms_from_number = request.form.get('sms_from_number', '')
        
        # Update or create settings
        settings_to_update = [
            ('theme', theme),
            ('hospital_name', hospital_name),
            ('contact', contact),
            ('sms_account_sid', sms_account_sid),
            ('sms_auth_token', sms_auth_token),
            ('sms_from_number', sms_from_number)
        ]
        
        for key, value in settings_to_update:
            setting = Settings.query.filter_by(key=key).first()
            if setting:
                setting.value = value
            else:
                db.session.add(Settings(key=key, value=value))
        
        db.session.commit()
        flash('Settings updated successfully!', 'success')
    
    current_theme = get_setting('theme', 'light')
    hospital_name = get_setting('hospital_name', 'Medical Camp Center')
    contact = get_setting('contact', '+1 234 567 890')
    
    # Get SMS settings
    sms_account_sid = get_setting('sms_account_sid', '')
    sms_auth_token = get_setting('sms_auth_token', '')
    sms_from_number = get_setting('sms_from_number', '')
    sms_configured = bool(sms_account_sid and sms_auth_token and sms_from_number)
    
    return render_template('settings.html', 
                           theme=current_theme,
                           hospital_name=hospital_name,
                           contact=contact,
                           sms_account_sid=sms_account_sid,
                           sms_auth_token=sms_auth_token,
                           sms_from_number=sms_from_number,
                           sms_configured=sms_configured)

# ============ PDF Report Generation ============
@app.route('/generate_report')
def generate_report():
    patients = Patient.query.all()
    
    # Create PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    # Title
    hospital_name = get_setting('hospital_name', 'Medical Camp Center')
    elements.append(Paragraph(f"<b>{hospital_name}</b>", styles['Title']))
    elements.append(Paragraph("Patient Report", styles['Heading2']))
    elements.append(Spacer(1, 20))
    
    # Table Data
    data = [['ID', 'Name', 'Age', 'Gender', 'Disease', 'Doctor', 'Date']]
    for p in patients:
        data.append([p.id, p.name, p.age, p.gender, p.disease or 'N/A', 
                    p.doctor or 'N/A', p.appointment_date or 'N/A'])
    
    # Create Table
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5364')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(table)
    doc.build(elements)
    
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name='patient_report.pdf', mimetype='application/pdf')

if __name__ == '__main__':
    app.run(debug=True)

