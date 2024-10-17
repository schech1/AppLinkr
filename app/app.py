from flask import Flask
import os
from db import close_db
from routes import setup_routes

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

# Register the database teardown function
@app.teardown_appcontext
def teardown(exception):
    close_db(exception)

# Set up routes
setup_routes(app, SERVER_URL, PASSWORD)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
