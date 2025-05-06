import json
import os
import time
import asyncio
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
import websockets
import threading
import importlib.util

# === Flask Setup ===
app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
CORS(app, resources={
    r"/*": {
        "origins": ["http://localhost:*", "http://127.0.0.1:*"],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

# === Database Initialization ===
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            is_admin BOOLEAN DEFAULT FALSE,
            user_group TEXT DEFAULT 'default'
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# === WebSocket Server Setup ===
class NumberServer:
    def __init__(self, port=5001):
        self.port = port
        self.clients = {}
        self.server = None
        self.loop = None
        self.stop_event = asyncio.Event()

    async def handle_connection(self, websocket):
        """Handle WebSocket connections with both required parameters"""
        print(f"🟢 New WebSocket connection from {websocket.remote_address}, path: ")
        try:
            # Register client
            async for message in websocket:
                try:
                    data = json.loads(message)
                    if data.get('type') == 'client_ready':
                        user_group = data.get('user_group', 'default')
                        if user_group not in self.clients:
                            self.clients[user_group] = set()
                        self.clients[user_group].add(websocket)
                        print(f"📌 Added client to group: {user_group}")
                except json.JSONDecodeError:
                    print(f"❌ Invalid JSON received: {message}")
        except websockets.exceptions.ConnectionClosed:
            print("🔌 Connection closed by client")
        finally:
            # Clean up
            for group in list(self.clients.keys()):
                if websocket in self.clients[group]:
                    self.clients[group].remove(websocket)
                    if not self.clients[group]:
                        del self.clients[group]
            print("🔴 WebSocket disconnected")

    async def run_server(self):
        """Run the WebSocket server"""
        self.server = await websockets.serve(
            self.handle_connection,
            "0.0.0.0",
            self.port
        )
        
        print(f"🚀 WebSocket server started on ws://0.0.0.0:{self.port}")
        await self.stop_event.wait()
        await self.server.wait_closed()

    def start(self):
        """Start the server in a background thread"""
        def run():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.run_server())
        
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop the server gracefully"""
        if self.loop:
            self.loop.call_soon_threadsafe(self.stop_event.set)

    async def send_to_group(self, group_name, data):
        """Send data to all clients in a specific group"""
        if group_name not in self.clients:
            print(f"⚠️ Group '{group_name}' not found")
            return

        message = json.dumps(data)
        clients = self.clients[group_name].copy()
        
        # Send to all clients in the group
        tasks = [self._safe_send(client, message) for client in clients]
        await asyncio.gather(*tasks)

    async def _safe_send(self, websocket, message):
        """Helper method to send a message safely to a client"""
        try:
            await websocket.send(message)
        except websockets.exceptions.ConnectionClosed:
            print(f"⚠️ Connection closed for client, removing from groups")
            # Remove the disconnected client from all groups
            for group in list(self.clients.keys()):
                if websocket in self.clients[group]:
                    self.clients[group].remove(websocket)
                    if not self.clients[group]:
                        del self.clients[group]

# === Flask Routes ===
@app.route('/')
def home():
    if 'username' in session:
        return render_template('index.html',
                               username=session['username'],
                               is_admin=session.get('is_admin', False),
                               user_group=session.get('user_group', 'default'),
                               websocket_port=number_server.port)
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            session['username'] = user[1]
            session['is_admin'] = bool(user[3])
            session['user_group'] = user[4]
            return jsonify({"success": True, "message": "Login successful!"})
        return jsonify({"success": False, "message": "Invalid credentials!"})
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        special_password = request.form.get('special_password', '')

        is_admin = (special_password == 'admin123')
        user_group = 'admin' if is_admin else 'default'
        hashed_password = generate_password_hash(password)

        try:
            conn = sqlite3.connect('database.db')
            cursor = conn.cursor()
            cursor.execute('INSERT INTO users (username, password, is_admin, user_group) VALUES (?, ?, ?, ?)',
                           (username, hashed_password, is_admin, user_group))
            conn.commit()
            conn.close()

            session['username'] = username
            session['is_admin'] = is_admin
            session['user_group'] = user_group
            return jsonify({"success": True, "message": "Registration successful!"})
        except sqlite3.IntegrityError:
            return jsonify({"success": False, "message": "User already exists"})
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# === Bot Loading and Execution ===
BOTS_FOLDER = "bots"
imported_bots = {}

def load_bots():
    if not os.path.exists(BOTS_FOLDER):
        os.makedirs(BOTS_FOLDER)
        print(f"📁 Created bots directory at {BOTS_FOLDER}")
        return

    for filename in os.listdir(BOTS_FOLDER):
        if filename.endswith(".py") and not filename.startswith("__"):
            bot_name = filename[:-3]
            file_path = os.path.join(BOTS_FOLDER, filename)
            try:
                spec = importlib.util.spec_from_file_location(bot_name, file_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                imported_bots[bot_name] = module
                print(f"🤖 Loaded bot: {bot_name}")
            except Exception as e:
                print(f"❌ Failed to load bot {filename}: {str(e)}")

async def run_periodically(bot_name, mod, function_name="get_data"):
    if not hasattr(mod, "REFRESH_INTERVAL"):
        print(f"⚠️ {bot_name} is missing REFRESH_INTERVAL. Skipping.")
        return

    interval = getattr(mod, "REFRESH_INTERVAL")

    while True:
        try:
            print(f"\n⏰ Running {bot_name}.{function_name} at {datetime.now()}")
            if hasattr(mod, function_name):
                result = getattr(mod, function_name)()
                print(f"✅ {bot_name}.{function_name}() returned:\n{result}")

                if result is not None:
                    await number_server.send_to_group("asas", result)
                else:
                    print(f"⚠️ {bot_name}.{function_name}() returned None, skipping.")
            else:
                print(f"⚠️ {bot_name} does not have {function_name}")
        except Exception as e:
            print(f"❌ Error in {bot_name}.{function_name}: {str(e)}")
        await asyncio.sleep(interval)

async def main():
    load_bots()
    tasks = [run_periodically(name, mod) for name, mod in imported_bots.items()]
    await asyncio.gather(*tasks)

def start_asyncio_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())

if __name__ == '__main__':
    number_server = NumberServer()
    number_server.start()

    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=lambda: app.run(debug=True, port=5000, use_reloader=False))
    flask_thread.daemon = True
    flask_thread.start()

    try:
        start_asyncio_loop()
    except KeyboardInterrupt:
        number_server.stop()
        flask_thread.join()