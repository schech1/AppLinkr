from flask import Flask, request, redirect, url_for, send_file, render_template, g, session, flash
from functools import wraps
import qrcode
import io
import os
import sqlite3
import uuid  
import base64
from user_tracking import detect_browser_and_os, get_client_ip, get_location, detect_device
import validators

app = Flask(__name__)
app.secret_key = os.urandom(24) 

# Database setup
# Define the default database location inside the 'db' folder
DATABASE_FOLDER = "db"
DATABASE_PATH = f"{DATABASE_FOLDER}/database.db"

# Ensure the 'db' folder exists
if not os.path.exists(DATABASE_FOLDER):
    os.makedirs(DATABASE_FOLDER)

# GET ENVS
SERVER_URL = os.getenv("SERVER_URL")
PASSWORD = os.getenv("PASSWORD")

def is_valid_url(url):
    """Validate if the given content is a valid URL."""
    return validators.url(url)

def get_db():
    """Get a database connection."""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE_PATH)
        
        # Create qr_codes table with qr_image allowing NULL values
        g.db.execute('''CREATE TABLE IF NOT EXISTS qr_codes
                        (id TEXT PRIMARY KEY,
                         title TEXT NOT NULL,
                         content TEXT,                     
                         app_store_url TEXT NOT NULL,
                         play_store_url TEXT NOT NULL,
                         qr_image BLOB)''')  

        g.db.execute('''CREATE TABLE IF NOT EXISTS qr_code_tracking
                        (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         qr_code_id TEXT NOT NULL,
                         device_type TEXT NOT NULL,
                         ip_address TEXT NOT NULL,
                         access_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                         region TEXT,
                         browser TEXT,
                         os TEXT,
                         language TEXT,
                         referrer TEXT,
                         FOREIGN KEY (qr_code_id) REFERENCES qr_codes(id))''')
    return g.db



@app.teardown_appcontext
def close_db(exception):
    """Close the database connection."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


@app.route('/')
def index():
    """Display the form for entering the App Store and Play Store URLs."""
    db = get_db()
    qr_codes = db.execute('SELECT * FROM qr_codes').fetchall()
    
    # Fetch tracking information for each QR code
    tracking_data = {}
    for code in qr_codes:
        tracking_data[code[0]] = db.execute('SELECT * FROM qr_code_tracking WHERE qr_code_id = ?', (code[0],)).fetchall()

    return render_template('index.html', qr_codes=[(code, tracking_data[code[0]]) for code in qr_codes])

@app.route('/create', methods=['POST'])
def create():
    """Generate a QR code with either custom URL content or app store links."""
    title = request.form['title']
    app_store_url = request.form.get('app_store_url')
    play_store_url = request.form.get('play_store_url')
    content = request.form.get('content')

    # Create a database connection and cursor
    db = get_db()
    cursor = db.cursor()

    # Generate a new UUID for the QR code
    qr_code_id = str(uuid.uuid4())

    if content:  # If content for standard QR code is provided
        if not is_valid_url(content):  # Validate the URL
            return "Invalid URL provided for standard QR", 400

        qr_url = f"{SERVER_URL}/redirect_standard?qr_code_id={qr_code_id}"  # Redirect for standard QR
        cursor.execute('INSERT INTO qr_codes (id, title, content, app_store_url, play_store_url) VALUES (?, ?, ?, ?, ?)', 
                       (qr_code_id, title, content, "", ""))  # App Store URLs are empty for standard QR codes
    else:  # If the App Store and Play Store URLs are provided
        if not (is_valid_url(app_store_url) and is_valid_url(play_store_url)):
            return "Invalid URLs for App Store or Play Store", 400

        qr_url = f"{SERVER_URL}/redirect?app_store_url={app_store_url}&play_store_url={play_store_url}&qr_code_id={qr_code_id}"
        cursor.execute('INSERT INTO qr_codes (id, title, content, app_store_url, play_store_url) VALUES (?, ?, ?, ?, ?)', 
                       (qr_code_id, title, "", app_store_url, play_store_url))

    db.commit()

    # Generate the QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_url)
    qr.make(fit=True)
    img = qr.make_image(fill='black', back_color='white')

    # Save the QR code image
    img_buf = io.BytesIO()
    img.save(img_buf, 'PNG')
    img_buf.seek(0)

    # Update the database with the QR code image
    cursor.execute('UPDATE qr_codes SET qr_image = ? WHERE id = ?', (img_buf.getvalue(), qr_code_id))
    db.commit()

    qr_code_url = f"{SERVER_URL}{url_for('show', code_id=qr_code_id)}"

    return render_template('index.html', qr_code_url=qr_code_url)


@app.route('/redirect_standard')
def redirect_standard():
    """Redirect to the standard URL content."""
    qr_code_id = request.args.get('qr_code_id')

    # Retrieve the URL content from the database
    db = get_db()
    qr_code_data = db.execute('SELECT content FROM qr_codes WHERE id = ?', (qr_code_id,)).fetchone()

    if qr_code_data is None or not is_valid_url(qr_code_data[0]):
        return "Invalid or missing URL", 400

    return redirect(qr_code_data[0])

@app.route('/show/<code_id>')
def show(code_id):
    """Serve the generated QR code image."""
    # Retrieve the QR code image from the database
    db = get_db()
    qr_code_data = db.execute('SELECT qr_image FROM qr_codes WHERE id = ?', (code_id,)).fetchone()

    if qr_code_data is None:
        return "QR Code not found", 404

    # Return the image as a file response
    buf = io.BytesIO(qr_code_data[0])
    return send_file(buf, mimetype='image/png')

@app.route('/redirect')
def redirect_to_store():
    """Redirect the user to the appropriate store based on their device."""
    # URLs und andere Parameter aus der Anfrage abrufen
    app_store_url = request.args.get('app_store_url')
    play_store_url = request.args.get('play_store_url')
    qr_code_id = request.args.get('qr_code_id')  
    
    # User-Agent und IP-Adresse abrufen
    user_agent = request.headers.get('User-Agent')
    ip_address = get_client_ip()

    # Gerätetyp und Sprache erkennen
    device = detect_device(user_agent)
    language = request.headers.get('Accept-Language', 'Unknown')

    # Referrer URL erfassen
    referrer = request.headers.get('Referer', 'Direct Access')

    # Standort über IP-Geolocation-API herausfinden
    region = get_location(ip_address)

    # Browser und Betriebssystem erkennen
    browser, os = detect_browser_and_os(user_agent)

    # Daten in der Datenbank speichern
    db = get_db()
    db.execute('''INSERT INTO qr_code_tracking (qr_code_id, device_type, ip_address, region, browser, os, language, referrer)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
               (qr_code_id, device, ip_address, region, browser, os, language, referrer))
    db.commit()

    # Weiterleiten zu den passenden URLs
    if device == "android" and play_store_url:
        return redirect(play_store_url)
    elif device == "ios" and app_store_url:
        return redirect(app_store_url)
    else:
        return "Device not recognized or no URL provided", 400


@app.template_filter('b64encode')
def b64encode_filter(data):
    """Encode binary data to Base64 for embedding in HTML."""
    if data:
        return base64.b64encode(data).decode('utf-8')
    return ''


### Admin Area

def require_authentication(f):
    @wraps(f)  # Preserve the original function's metadata
    def decorated_function(*args, **kwargs):
        if 'authenticated' not in session:
            flash('You must be logged in to access this page.', 'danger')
            return redirect(url_for('admin'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/admin', methods=['GET', 'POST'])
def admin():
    """Display QR code statistics (password protected)."""
    if request.method == 'POST':
        password = request.form.get('password')
        # Get password from docker-compose
        if password == PASSWORD:
            session['authenticated'] = True
            return redirect(url_for('admin'))
        else:
            return "Invalid password", 403

    # Check if user is authenticated
    if 'authenticated' not in session:
        return render_template('admin.html') 

    # Fetch QR code data
    db = get_db()
    qr_codes = db.execute('SELECT * FROM qr_codes').fetchall()

    tracking_data = {}
    for code in qr_codes:
        tracking_data[code[0]] = db.execute('SELECT * FROM qr_code_tracking WHERE qr_code_id = ?', (code[0],)).fetchall()

    # Create a list of QR codes with the serve URL
    qr_codes_with_url = [
        (code, f"{SERVER_URL}/show/{code[0]}", tracking_data[code[0]])
        for code in qr_codes
    ]

    return render_template('admin.html', qr_codes=qr_codes_with_url)


## Backup and Delete Database

@app.route('/delete/<qr_code_id>', methods=['GET'])
@require_authentication
def delete_qr_code(qr_code_id):
    """Delete a QR code entry from the database."""
    delete_qr_code_by_id(qr_code_id)
    flash('QR code deleted successfully!', 'success')
    return redirect(url_for('admin'))  

def delete_qr_code_by_id(qr_code_id):
    """Delete a QR code by its ID."""
    db = get_db()
    db.execute('DELETE FROM qr_codes WHERE id = ?', (qr_code_id,))
    db.execute('DELETE FROM qr_code_tracking WHERE qr_code_id = ?', (qr_code_id,))
    db.commit()


@app.route('/download_db', methods=['GET'])
@require_authentication
def download_db():
    if os.path.exists(DATABASE_PATH):
        return send_file(DATABASE_PATH, as_attachment=True)
    else:
        return "Database file not found.", 404


@app.route('/logout')
def logout():
    """Logout and clear session."""
    session.pop('authenticated', None)
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
