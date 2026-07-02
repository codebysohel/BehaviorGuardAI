# 🛡️ BehaviorGuard AI: Web App & Risk Scoring Engine

BehaviorGuard AI is a two-part system designed to analyze user behavior sessions and score them for risk using machine learning. 

This project consists of:
1. **The Risk Engine (Backend):** A Flask API running on port 8000 that hosts machine learning models (Isolation Forest and an Autoencoder) to evaluate keystroke, mouse, and session data.
2. **The Web Application (Frontend):** A Python-based application that interfaces with the user, collects data, interacts with a database, and queries the Risk Engine for decision-making.

---

## 📁 Recommended Directory Structure

Before starting, it is highly recommended to organize your downloaded files into a clean folder structure. Create a main project folder (e.g., `BehaviorGuard`) and organize the unzipped and loose files into two subdirectories exactly like this:

```text
BehaviorGuard/
├── behaviorguard_web/
│   ├── app.py
│   ├── database.py
│   ├── requirements.txt
│   ├── schema.sql
│   └── README.txt
└── risk_engine/
    ├── risk_engine (1).py
    ├── step3_retrain_from_csv.py
    ├── scaler_web (3).pkl
    ├── isolation_forest_web (3).pkl
    ├── autoencoder_web (3).keras
    ├── autoencoder_threshold_web (3).npy
    └── autoencoder_threshold_web (2).npy  <-- (Optional backup)

(Note: The risk_engine (1).py script explicitly looks for the model files with the (3) in their filenames. Keep the filenames exactly as downloaded unless you plan to edit the risk_engine (1).py code to match cleaner names).

🛠️ Prerequisites
Ensure you have the following installed on your system:

Python 3.8+ (Python 3.10 is recommended for TensorFlow compatibility)

pip (Python package installer)

SQLite (Usually comes pre-installed with Python, required for schema.sql)

🚀 Step-by-Step Setup Guide
Step 1: Set Up a Virtual Environment (Recommended)
To prevent conflicts with other Python projects on your machine, create a virtual environment in your main BehaviorGuard folder.

Open your terminal/command prompt and run:

Bash
# Navigate to your project folder
cd path/to/BehaviorGuard

# Create the virtual environment
python -m venv venv

# Activate the virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
Step 2: Install Dependencies
You need to install the required libraries for both the web app and the ML risk engine.

Bash
# Navigate to the web app folder to install its specific requirements
cd behaviorguard_web
pip install -r requirements.txt

# Return to the main folder, then install the Risk Engine dependencies
cd ..
pip install Flask Flask-Cors numpy pandas scikit-learn tensorflow
Step 3: Initialize the Database
The web application requires a database schema to be initialized before it can run properly.

Bash
cd behaviorguard_web

# Run the schema SQL file to initialize your SQLite database
sqlite3 behaviorguard.db < schema.sql

cd ..
(Note: If you do not have the sqlite3 command-line tool installed, you can often run a database initialization script directly from within database.py or use a free DB viewer like DB Browser for SQLite to execute schema.sql).

Step 4: Start the Risk Engine Server
The Risk Engine must be running for the Web App to get risk scores. It runs on http://localhost:8000.

Open a new terminal window, activate your virtual environment, and run:

Bash
cd path/to/BehaviorGuard/risk_engine

# Run the flask application
python "risk_engine (1).py"
You should see a console output indicating that the scaler, Isolation Forest, and Autoencoder models have successfully loaded, along with the message: BehaviorGuard AI — Risk Scoring Engine.

Step 5: Start the Web Application
With the Risk Engine running, you can now start the frontend web application.

Go back to your first terminal window (where the virtual environment is also active) and run:

Bash
cd path/to/BehaviorGuard/behaviorguard_web

# Run the web app
python app.py
Check the terminal output for the local URL (usually http://127.0.0.1:5000). Open this link in your web browser to interact with the application!

🧠 Advanced: Retraining the Models
If you need to retrain the Risk Engine models with new data in the future, a retraining script has been provided (step3_retrain_from_csv.py).

Place your updated raw feature dataset named sessions_converted.csv into the risk_engine folder.

Run the script:

Bash
cd risk_engine
python step3_retrain_from_csv.py
This script will train a new standard scaler, Isolation Forest, and Autoencoder. It will output a models/ directory containing scaler_web.pkl, isolation_forest_web.pkl, autoencoder_web.keras, and autoencoder_threshold_web.npy.

Important: If you use these newly generated files, you will need to open risk_engine (1).py and update the file paths at the top of the script (remove the (3) from the filenames) so the engine loads your new, updated models.
