
EXACT FLOW
-----------
  User enters username + password
         ↓
  Check user exists in MySQL database (phpMyAdmin)
         ↓
  Password correct?
  ├── No  → Deny (wrong credentials flash message)
  └── Yes
         ↓
  Behavioral events collected silently by JS in browser
         ↓
  POST to Risk API → GET risk score 0–100
         ↓
  0–30   → ALLOW  → Home screen (shows score + factors)
  31–60  → OTP    → OTP screen (demo OTP: 123456)
  61+    → BLOCK  → Access Denied screen (shows score)

FILES
------
  app.py          Main Flask server
  database.py     MySQL database layer (phpMyAdmin compatible)
  schema.sql      SQL to paste into phpMyAdmin to create tables
  requirements.txt
  templates/
    login.html    Login page — JS SDK collects signals silently
    home.html     Home — live risk gauge + factor breakdown + history
    otp.html      OTP verification screen
    blocked.html  Access denied screen with risk score
    register.html New user registration
    dashboard.html Live session dashboard (auto-refreshes every 5s)

SETUP — DO THIS FIRST
-----------------------
1. Start MySQL + phpMyAdmin (usually via XAMPP or WAMP)
   Open: http://localhost/phpmyadmin

2. Create the database:
   - Click "New" in the left panel
   - Database name: behaviorguard
   - Click Create

3. Import the schema:
   - Select the "behaviorguard" database
   - Click the "SQL" tab at the top
   - Paste the contents of schema.sql
   - Click Go

   This creates the users and login_sessions tables
   and adds demo users alice and bob (password: Test@1234)

4. Edit database.py — change DB_CONFIG to match your MySQL:
   DB_CONFIG = {
       "host":     "localhost",
       "user":     "root",      ← your phpMyAdmin username
       "password": "",          ← your phpMyAdmin password
       "database": "behaviorguard"
   }
   (On XAMPP the default is user=root, password=blank)

HOW TO RUN
-----------
Terminal 1 — Risk API (from behaviorguard_risk_api folder):
  python app.py
  (runs on port 8000)

Terminal 2 — This web app:
  pip install flask flask-cors requests mysql-connector-python
  python app.py
  (runs on port 5000)

Open browser: http://localhost:5000

DEMO ACCOUNTS
--------------
  ganesh / Qwertyuiopas12@
  pratik   / Test@1234
  (created automatically by schema.sql)

Add more users via http://localhost:5000/register
or directly in phpMyAdmin → users table → Insert

PHPPADMIN — WHAT YOU CAN SEE
------------------------------
  users table:
    id | username | password_hash | created_at
    Every registered user appears here.
    You can add/edit/delete users directly.

  login_sessions table:
    id | user_id | timestamp | event_count | risk_score | decision | ip_address | latency_ms
    Every login attempt is logged here in real time.
    Watch it update as you log in from the browser.

DEMO FLOW FOR JUDGES
---------------------
  Screen 1 (browser): http://localhost:5000
  Screen 2 (browser): http://localhost:5000/dashboard
  Screen 3 (phpMyAdmin): login_sessions table — Browse

  1. Log in as alice normally
     → Score appears on home screen (low, green)
     → Row added to login_sessions in phpMyAdmin

  2. Open a different browser, log in as alice with wrong rhythm
     → Score is higher (orange/red)
     → OTP or Block screen shown
     → Row in phpMyAdmin shows the higher score

  3. Dashboard auto-updates every 5 seconds — judges see
     all sessions appear in real time with color-coded risk scores

TROUBLESHOOTING
----------------
  "mysql.connector.errors.DatabaseError: Access denied"
    → Edit DB_CONFIG in database.py — wrong username or password

  "mysql.connector.errors.DatabaseError: Unknown database"
    → Run schema.sql in phpMyAdmin first

  "Risk API offline — defaulting to allow"
    → Start the risk API: cd behaviorguard_risk_api && python app.py
    → App still works but shows no score

  "ModuleNotFoundError: No module named 'mysql'"
    → pip install mysql-connector-python
