from flask import request, redirect, render_template, send_file, session, flash, url_for, jsonify
import uuid
import qrcode
import io
import base64
from db import get_db
from db import DATABASE_PATH
from db import delete_qr_code_by_id
from utils import is_valid_url, process_metrics
from metrics import  get_client_ip
import os



def setup_routes(app, SERVER_URL, PASSWORD):

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

        # Check if either content or app store URLs are provided
        if not content and not (app_store_url and play_store_url):
            flash('You must provide either a standard URL or both App Store and Play Store URLs.', 'danger')
            return render_template('index.html')

        # Check for invalid URL in the standard content
        if content and not is_valid_url(content):
            flash('Invalid URL provided for standard QR.', 'danger')
            return render_template('index.html')

        # Check for invalid URLs in the app store fields
        if not content:
            if not (is_valid_url(app_store_url) and is_valid_url(play_store_url)):
                flash('Invalid URLs for App Store or Play Store.', 'danger')
                return render_template('index.html')

        # Create a database connection and cursor
        db = get_db()
        cursor = db.cursor()

        # Generate a new UUID for the QR code
        qr_code_id = str(uuid.uuid4())

        # Generate the appropriate QR code URL
        if content:  # If content for a standard QR code is provided
            qr_url = f"{SERVER_URL}/redirect_standard?qr_code_id={qr_code_id}"  # Redirect for standard QR
            cursor.execute('INSERT INTO qr_codes (id, title, content, app_store_url, play_store_url) VALUES (?, ?, ?, ?, ?)',
                        (qr_code_id, title, content, "", ""))  # App Store URLs are empty for standard QR codes
        else:  # For app store links
            qr_url = f"{SERVER_URL}/redirect/{qr_code_id}"
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

        # Generate QR code URL to show in the template
        qr_code_url = f"{SERVER_URL}{url_for('show', code_id=qr_code_id)}"

        return render_template('index.html', qr_code_url=qr_code_url)

    @app.route('/redirect_standard')
    def redirect_standard():
        """Redirect to the standard URL content."""
        qr_code_id = request.args.get('qr_code_id')    
        user_agent = request.headers.get('User-Agent')
        process_metrics(qr_code_id, user_agent)

        # Retrieve the URL content from the database
        db = get_db()
        qr_code_data = db.execute('SELECT content FROM qr_codes WHERE id = ?', (qr_code_id,)).fetchone()

        if qr_code_data is None or not is_valid_url(qr_code_data[0]):
            return "Invalid or missing URL", 400

        return redirect(qr_code_data[0])

  
    @app.route('/show/<code_id>')
    def show(code_id):
        """Serve the generated QR code image."""
        db = get_db()
        qr_code_data = db.execute('SELECT qr_image FROM qr_codes WHERE id = ?', (code_id,)).fetchone()

        if qr_code_data is None:
            return "QR Code not found", 404

        buf = io.BytesIO(qr_code_data[0])
        return send_file(buf, mimetype='image/png')

    @app.route('/redirect/<qr_code_id>')
    def redirect_to_store(qr_code_id):
        """Redirect the user to the appropriate store based on their device."""
        db = get_db()
        
        # Fetch the app store and play store URLs from the database
        qr_code_data = db.execute('SELECT app_store_url, play_store_url FROM qr_codes WHERE id = ?', (qr_code_id,)).fetchone()

        if not qr_code_data:
            return "QR Code not found", 404

        app_store_url, play_store_url = qr_code_data

        # Get user agent and determine device type
        user_agent = request.headers.get('User-Agent')
        device = process_metrics(qr_code_id, user_agent)

        # Redirect based on device type
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

    ## Admin Area
    from functools import wraps

    def require_authentication(f):
        @wraps(f)
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
            if password == PASSWORD:
                session['authenticated'] = True
                return redirect(url_for('admin'))
            else:
                return "Invalid password", 403

        if 'authenticated' not in session:
            return render_template('admin.html') 

        db = get_db()
        qr_codes = db.execute('SELECT * FROM qr_codes').fetchall()

        tracking_data = {}
        for code in qr_codes:
            tracking_data[code[0]] = db.execute('SELECT * FROM qr_code_tracking WHERE qr_code_id = ?', (code[0],)).fetchall()

        qr_codes_with_url = [
            (code, f"{SERVER_URL}/redirect/{code[0]}", tracking_data[code[0]])
            for code in qr_codes
        ]


        return render_template('admin.html', qr_codes=qr_codes_with_url)

    @app.route('/delete/<qr_code_id>', methods=['GET'])
    @require_authentication
    def delete_qr_code(qr_code_id):
        """Delete a QR code entry from the database."""
        delete_qr_code_by_id(qr_code_id)
        flash('QR code deleted successfully!', 'success')
        return redirect(url_for('admin'))  

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
