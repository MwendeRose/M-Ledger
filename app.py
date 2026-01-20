from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime
from dotenv import load_dotenv
import json
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# MongoDB Connection
client = MongoClient(os.getenv('MONGODB_URI'))
db = client[os.getenv('DATABASE_NAME')]
users_collection = db['users']

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')

class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data['_id'])
        self.username = user_data.get('username')
        self.email = user_data.get('email')
        self.google_id = user_data.get('google_id')
        self.created_at = user_data.get('created_at')

@login_manager.user_loader
def load_user(user_id):
    user_data = users_collection.find_one({'_id': user_id})
    if user_data:
        return User(user_data)
    return None

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user_data = users_collection.find_one({'email': email})
        
        if user_data and check_password_hash(user_data['password'], password):
            user = User(user_data)
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'error')
    
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validation
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('signup.html')
        
        if users_collection.find_one({'email': email}):
            flash('Email already exists', 'error')
            return render_template('signup.html')
        
        if users_collection.find_one({'username': username}):
            flash('Username already exists', 'error')
            return render_template('signup.html')
        
        # Create new user
        hashed_password = generate_password_hash(password)
        user_data = {
            'username': username,
            'email': email,
            'password': hashed_password,
            'created_at': datetime.utcnow(),
            'google_id': None
        }
        
        result = users_collection.insert_one(user_data)
        user = User({'_id': result.inserted_id, **user_data})
        login_user(user)
        
        return redirect(url_for('dashboard'))
    
    return render_template('signup.html')

@app.route('/login/google', methods=['POST'])
def login_google():
    try:
        token = request.json.get('token')
        
        # Verify Google token
        idinfo = id_token.verify_oauth2_token(
            token, google_requests.Request(), GOOGLE_CLIENT_ID
        )
        
        if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            raise ValueError('Wrong issuer.')
        
        google_id = idinfo['sub']
        email = idinfo['email']
        name = idinfo.get('name', '').split()[0]  # Use first name as username
        
        # Check if user exists
        user_data = users_collection.find_one({'email': email})
        
        if not user_data:
            # Create new user
            user_data = {
                'username': name,
                'email': email,
                'password': None,
                'google_id': google_id,
                'created_at': datetime.utcnow()
            }
            result = users_collection.insert_one(user_data)
            user_data['_id'] = result.inserted_id
        else:
            # Update google_id if not present
            if not user_data.get('google_id'):
                users_collection.update_one(
                    {'_id': user_data['_id']},
                    {'$set': {'google_id': google_id}}
                )
                user_data['google_id'] = google_id
        
        user = User(user_data)
        login_user(user)
        
        return jsonify({'success': True, 'redirect': url_for('dashboard')})
    
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user=current_user)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/main')
@login_required
def main():
    # Import and run main.py
    import subprocess
    import sys
    
    try:
        # Run main.py as a separate process
        subprocess.run([sys.executable, 'main.py'])
        return redirect(url_for('dashboard'))
    except Exception as e:
        flash(f'Error starting main application: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)