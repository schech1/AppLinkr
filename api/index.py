import os
import sys

# Ensure the application package is on the Python path
APP_DIR = os.path.join(os.path.dirname(__file__), "..", "app")
if APP_DIR not in sys.path:
    sys.path.append(APP_DIR)

# Import the Flask application
from app import app as flask_app  # type: ignore

# Expose the Flask app for the Vercel Python runtime
app = flask_app
