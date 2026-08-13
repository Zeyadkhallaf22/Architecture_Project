"""
Data Center Dashboard Backend - SQL Express 2022 Version
Architecture: SQL Express 2022 Database → Python Backend → Web Dashboard
Run with: python server.py
Then open http://localhost:8000/index.html
"""

from __future__ import annotations

import json
import random
import threading
import time
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pyodbc

# ============================================================
# DATABASE CONFIGURATION - SQL EXPRESS 2022
# ============================================================

# Use localhost with SQLEXPRESS (from your SSMS history)
CONNECTION_STRING = (
    'DRIVER={ODBC Driver 17 for SQL Server};'
    'SERVER=localhost\\SQLEXPRESS;'
    'DATABASE=DataCenterKPI;'
    'Trusted_Connection=yes;'
)

# Alternative: Use MARIAM with SQLEXPRESS01
# CONNECTION_STRING = (
#     'DRIVER={ODBC Driver 17 for SQL Server};'
#     'SERVER=MARIAM\\SQLEXPRESS01;'
#     'DATABASE=DataCenterKPI;'
#     'Trusted_Connection=yes;'
# )

# Alternative: Use MARIAM with MSSQLSERVER03
# CONNECTION_STRING = (
#     'DRIVER={ODBC Driver 17 for SQL Server};'
#     'SERVER=MARIAM\\MSSQLSERVER03;'
#     'DATABASE=DataCenterKPI;'
#     'Trusted_Connection=yes;'
# )

ROOT = Path(__file__).resolve().parent
LOCK = threading.Lock()

# ============================================================
# STATE MANAGEMENT
# ============================================================

# Track previous alarm states
previous_alarm_state = {}

# Initial state
state = {
    "Simulation_On": True,
    "Server1_CPU_Percent": 35.2,
    "Server1_RAM_Percent": 45.6,
    "Server1_Disk_Percent": 52.3,
    "Server1_Temp_C": 48.7,
    "Server1_Status": True,
    "Server1_Network_Mbps": 110.0,
    "Server1_Latency_ms": 10.0,
    "Server1_CPU_Alarm": False,
    "Server1_Temp_Alarm": False,
    "Server1_Down_Alarm": False,
    "Server2_CPU_Percent": 58.1,
    "Server2_RAM_Percent": 62.4,
    "Server2_Disk_Percent": 60.7,
    "Server2_Temp_C": 52.3,
    "Server2_Status": True,
    "Server2_Network_Mbps": 125.0,
    "Server2_Latency_ms": 14.0,
    "Server2_CPU_Alarm": False,
    "Server2_Temp_Alarm": False,
    "Server2_Down_Alarm": False,
    "Server3_CPU_Percent": 22.4,
    "Server3_RAM_Percent": 35.2,
    "Server3_Disk_Percent": 41.6,
    "Server3_Temp_C": 40.2,
    "Server3_Status": True,
    "Server3_Network_Mbps": 85.0,
    "Server3_Latency_ms": 8.0,
    "Server3_CPU_Alarm": False,
    "Server3_Temp_Alarm": False,
    "Server3_Down_Alarm": False,
    "Server4_CPU_Percent": 44.7,
    "Server4_RAM_Percent": 50.4,
    "Server4_Disk_Percent": 47.8,
    "Server4_Temp_C": 48.4,
    "Server4_Status": True,
    "Server4_Network_Mbps": 90.0,
    "Server4_Latency_ms": 12.0,
    "Server4_CPU_Alarm": False,
    "Server4_Temp_Alarm": False,
    "Server4_Down_Alarm": False,
    "DC_Servers_Up": 4,
    "DC_Avg_CPU": 0,
    "DC_Max_Temp": 0,
    "DC_Total_Network": 0,
}

# Database connection status
db_connected = False

# ============================================================
# DATABASE FUNCTIONS
# ============================================================

def get_connection():
    """Create a connection to SQL Express 2022."""
    try:
        conn = pyodbc.connect(CONNECTION_STRING, timeout=30)
        return conn
    except pyodbc.Error as e:
        print(f"❌ Database connection error: {e}")
        return None

def test_database_connection():
    """Test the database connection and display status."""
    global db_connected
    
    print("\n" + "=" * 70)
    print("🧪 TESTING SQL EXPRESS 2022 CONNECTION")
    print("=" * 70)
    
    # Test 1: Check if ODBC Driver is installed
    try:
        drivers = [x for x in pyodbc.drivers() if 'SQL Server' in x]
        print(f"\n📋 Available ODBC Drivers:")
        for driver in drivers:
            print(f"   - {driver}")
        
        if 'ODBC Driver 17 for SQL Server' not in drivers:
            print("\n⚠️  Warning: ODBC Driver 17 for SQL Server not found!")
            print("   Please install it from: https://go.microsoft.com/fwlink/?linkid=2249006")
            db_connected = False
            return False
    except Exception as e:
        print(f"❌ Error checking drivers: {e}")
        db_connected = False
        return False
    
    # Test 2: Try to connect
    print("\n" + "-" * 70)
    print("🔌 Attempting to connect to SQL Express 2022...")
    print(f"   Server: localhost\\SQLEXPRESS")
    print(f"   Database: DataCenterKPI")
    print(f"   Authentication: Windows Authentication")
    print("-" * 70)
    
    try:
        conn = get_connection()
        if conn is None:
            print("\n❌ Connection test FAILED!")
            print("   Could not establish connection to SQL Server")
            print("\n   Troubleshooting tips:")
            print("   1. Make sure SQL Server Express 2022 is running")
            print("   2. Verify the server name is correct")
            print("   3. Check if Windows Authentication is enabled")
            print("   4. Verify the database 'DataCenterKPI' exists")
            print("   5. Make sure TCP/IP is enabled in SQL Server Configuration")
            db_connected = False
            return False
            
        with conn:
            cursor = conn.cursor()
            
            # Check if database exists
            cursor.execute("SELECT DB_NAME()")
            db_name = cursor.fetchone()[0]
            print(f"✅ Connected to database: {db_name}")
            
            # Check tables
            cursor.execute("""
                SELECT TABLE_NAME 
                FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_NAME
            """)
            tables = cursor.fetchall()
            
            print(f"\n📊 Tables in database:")
            if tables:
                for table in tables:
                    table_name = table[0]
                    try:
                        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                        count = cursor.fetchone()[0]
                        print(f"   - {table_name}: {count} rows")
                    except:
                        print(f"   - {table_name}: (count unavailable)")
            else:
                print("   (No tables found - database may need initialization)")
            
            db_connected = True
            print("\n✅ SQL Express 2022 connection test PASSED!")
            return True
            
    except Exception as e:
        print(f"\n❌ Connection test FAILED!")
        print(f"   Error: {e}")
        print("\n   Troubleshooting tips:")
        print("   1. Make sure SQL Server Express 2022 is running")
        print("   2. Verify the server name is correct")
        print("   3. Check if Windows Authentication is enabled")
        print("   4. Verify the database 'DataCenterKPI' exists")
        print("   5. Make sure TCP/IP is enabled in SQL Server Configuration")
        print("   6. Check if firewall is blocking the connection")
        db_connected = False
        return False

def init_database():
    """Initialize database tables if they don't exist."""
    global db_connected
    
    try:
        conn = get_connection()
        if conn is None:
            db_connected = False
            return False
            
        with conn:
            cursor = conn.cursor()
            
            # Create ServerHistory table
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='ServerHistory' AND xtype='U')
                CREATE TABLE ServerHistory (
                    Id INT IDENTITY(1,1) PRIMARY KEY,
                    ServerNumber INT NOT NULL,
                    CPU_Percent FLOAT NULL,
                    RAM_Percent FLOAT NULL,
                    Disk_Percent FLOAT NULL,
                    Temperature_C FLOAT NULL,
                    Network_Mbps FLOAT NULL,
                    Latency_ms FLOAT NULL,
                    Status BIT NULL,
                    RecordedAt DATETIME NULL DEFAULT GETDATE()
                )
            """)
            
            # Create ServerMetrics table
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='ServerMetrics' AND xtype='U')
                CREATE TABLE ServerMetrics (
                    Id INT IDENTITY(1,1) PRIMARY KEY,
                    ServerNumber INT NOT NULL,
                    CPU_Percent FLOAT NULL,
                    RAM_Percent FLOAT NULL,
                    Disk_Percent FLOAT NULL,
                    Temperature_C FLOAT NULL,
                    Network_Mbps FLOAT NULL,
                    Latency_ms FLOAT NULL,
                    Status BIT NULL,
                    CPU_Alarm BIT NULL,
                    Temp_Alarm BIT NULL,
                    Down_Alarm BIT NULL,
                    RecordedAt DATETIME NULL DEFAULT GETDATE()
                )
            """)
            
            # Create AlarmEvents table
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='AlarmEvents' AND xtype='U')
                CREATE TABLE AlarmEvents (
                    Id INT IDENTITY(1,1) PRIMARY KEY,
                    ServerNumber INT NULL,
                    EventName VARCHAR(150) NULL,
                    Severity VARCHAR(20) NULL,
                    EventTime DATETIME NULL DEFAULT GETDATE()
                )
            """)
            
            # Create LatestTagValues table
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='LatestTagValues' AND xtype='U')
                CREATE TABLE LatestTagValues (
                    TagName NVARCHAR(100) NOT NULL PRIMARY KEY,
                    Value NVARCHAR(100) NOT NULL,
                    UpdatedAt DATETIME NOT NULL DEFAULT GETDATE()
                )
            """)
            
            # Create ServerCPUWorkbench table
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='ServerCPUWorkbench' AND xtype='U')
                CREATE TABLE ServerCPUWorkbench (
                    ServerNumber INT NOT NULL PRIMARY KEY,
                    CPU_Percent FLOAT NOT NULL,
                    UpdatedAt DATETIME NOT NULL DEFAULT GETDATE()
                )
            """)
            
            # Create CurrentServerState table
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='CurrentServerState' AND xtype='U')
                CREATE TABLE CurrentServerState (
                    ServerNumber INT NOT NULL PRIMARY KEY,
                    CPU_Percent FLOAT NULL,
                    RAM_Percent FLOAT NULL,
                    Disk_Percent FLOAT NULL,
                    Temperature_C FLOAT NULL,
                    Network_Mbps FLOAT NULL,
                    Latency_ms FLOAT NULL,
                    Status BIT NULL
                )
            """)
            
            # Create indexes
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='IX_ServerHistory_ServerTime')
                CREATE INDEX IX_ServerHistory_ServerTime ON ServerHistory (ServerNumber, RecordedAt DESC)
            """)
            
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='IX_ServerMetrics_ServerTime')
                CREATE INDEX IX_ServerMetrics_ServerTime ON ServerMetrics (ServerNumber, RecordedAt DESC)
            """)
            
            conn.commit()
            db_connected = True
            print("✅ Database tables initialized successfully.")
            return True
            
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        db_connected = False
        return False

def load_state_from_database():
    """Load the latest state from the database."""
    global state, db_connected
    
    if not db_connected:
        print("⚠️  Database not connected, skipping load")
        return False
    
    try:
        conn = get_connection()
        if conn is None:
            return False
            
        with conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT TagName, Value
                FROM LatestTagValues
            """)
            rows = cursor.fetchall()
            
            if rows:
                loaded_count = 0
                for row in rows:
                    tagname = row[0]
                    value_str = row[1]
                    
                    # Parse the value based on type
                    try:
                        if value_str.lower() in ('true', 'false'):
                            value = value_str.lower() == 'true'
                        else:
                            value = json.loads(value_str)
                    except:
                        value = value_str
                    
                    if tagname in state:
                        state[tagname] = value
                        loaded_count += 1
                
                print(f"✅ Loaded {loaded_count} tags from database")
                
                # Calculate summary after loading
                calculate_summary()
                return True
            
            return False
            
    except Exception as e:
        print(f"⚠️  Could not load state from database: {e}")
        return False

def save_to_database():
    """Save current state to SQL Express 2022."""
    global db_connected
    
    if not db_connected:
        return False
    
    now = datetime.now()
    
    try:
        conn = get_connection()
        if conn is None:
            db_connected = False
            return False
            
        with conn:
            cursor = conn.cursor()
            
            # Save latest values for ALL tags
            for tagname, tagvalue in state.items():
                # Convert value to string for storage
                if isinstance(tagvalue, bool):
                    value_str = 'true' if tagvalue else 'false'
                else:
                    value_str = json.dumps(tagvalue)
                
                cursor.execute("""
                    MERGE LatestTagValues AS target
                    USING (SELECT ? AS TagName, ? AS Value, ? AS UpdatedAt) AS source
                    ON target.TagName = source.TagName
                    WHEN MATCHED THEN
                        UPDATE SET Value = source.Value, UpdatedAt = source.UpdatedAt
                    WHEN NOT MATCHED THEN
                        INSERT (TagName, Value, UpdatedAt)
                        VALUES (source.TagName, source.Value, source.UpdatedAt);
                """, (tagname, value_str, now))
            
            # Save ServerHistory for each server
            for server in range(1, 5):
                status = 1 if state.get(f"Server{server}_Status", False) else 0
                
                cursor.execute("""
                    INSERT INTO ServerHistory 
                    (ServerNumber, CPU_Percent, RAM_Percent, Disk_Percent, 
                     Temperature_C, Network_Mbps, Latency_ms, Status, RecordedAt)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    server,
                    state.get(f"Server{server}_CPU_Percent", 0),
                    state.get(f"Server{server}_RAM_Percent", 0),
                    state.get(f"Server{server}_Disk_Percent", 0),
                    state.get(f"Server{server}_Temp_C", 0),
                    state.get(f"Server{server}_Network_Mbps", 0),
                    state.get(f"Server{server}_Latency_ms", 0),
                    status,
                    now
                ))
            
            # Save ServerMetrics with alarm states
            for server in range(1, 5):
                status = 1 if state.get(f"Server{server}_Status", False) else 0
                cpu_alarm = 1 if state.get(f"Server{server}_CPU_Alarm", False) else 0
                temp_alarm = 1 if state.get(f"Server{server}_Temp_Alarm", False) else 0
                down_alarm = 1 if state.get(f"Server{server}_Down_Alarm", False) else 0
                
                cursor.execute("""
                    INSERT INTO ServerMetrics 
                    (ServerNumber, CPU_Percent, RAM_Percent, Disk_Percent, 
                     Temperature_C, Network_Mbps, Latency_ms, Status,
                     CPU_Alarm, Temp_Alarm, Down_Alarm, RecordedAt)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    server,
                    state.get(f"Server{server}_CPU_Percent", 0),
                    state.get(f"Server{server}_RAM_Percent", 0),
                    state.get(f"Server{server}_Disk_Percent", 0),
                    state.get(f"Server{server}_Temp_C", 0),
                    state.get(f"Server{server}_Network_Mbps", 0),
                    state.get(f"Server{server}_Latency_ms", 0),
                    status,
                    cpu_alarm,
                    temp_alarm,
                    down_alarm,
                    now
                ))
                
                # Log alarm events
                alarm_mapping = {
                    "CPU_Alarm": ("CPU HIGH", "Critical"),
                    "Temp_Alarm": ("TEMP HIGH", "Warning"),
                    "Down_Alarm": ("SERVER DOWN", "Critical")
                }
                
                for alarm_name, (event_name, severity) in alarm_mapping.items():
                    tag = f"Server{server}_{alarm_name}"
                    current = state.get(tag, False)
                    previous = previous_alarm_state.get(tag, False)
                    
                    # Log when alarm turns ON
                    if current and not previous:
                        cursor.execute("""
                            INSERT INTO AlarmEvents 
                            (ServerNumber, EventName, Severity, EventTime)
                            VALUES (?, ?, ?, ?)
                        """, (server, event_name, severity, now))
                    
                    previous_alarm_state[tag] = current
            
            # Update CurrentServerState
            for server in range(1, 5):
                status = 1 if state.get(f"Server{server}_Status", False) else 0
                
                cursor.execute("""
                    MERGE CurrentServerState AS target
                    USING (
                        SELECT 
                            ? AS ServerNumber,
                            ? AS CPU_Percent,
                            ? AS RAM_Percent,
                            ? AS Disk_Percent,
                            ? AS Temperature_C,
                            ? AS Network_Mbps,
                            ? AS Latency_ms,
                            ? AS Status
                    ) AS source
                    ON target.ServerNumber = source.ServerNumber
                    WHEN MATCHED THEN
                        UPDATE SET
                            CPU_Percent = source.CPU_Percent,
                            RAM_Percent = source.RAM_Percent,
                            Disk_Percent = source.Disk_Percent,
                            Temperature_C = source.Temperature_C,
                            Network_Mbps = source.Network_Mbps,
                            Latency_ms = source.Latency_ms,
                            Status = source.Status
                    WHEN NOT MATCHED THEN
                        INSERT (ServerNumber, CPU_Percent, RAM_Percent, Disk_Percent, 
                                Temperature_C, Network_Mbps, Latency_ms, Status)
                        VALUES (source.ServerNumber, source.CPU_Percent, source.RAM_Percent, 
                                source.Disk_Percent, source.Temperature_C, source.Network_Mbps, 
                                source.Latency_ms, source.Status);
                """, (
                    server,
                    state.get(f"Server{server}_CPU_Percent", 0),
                    state.get(f"Server{server}_RAM_Percent", 0),
                    state.get(f"Server{server}_Disk_Percent", 0),
                    state.get(f"Server{server}_Temp_C", 0),
                    state.get(f"Server{server}_Network_Mbps", 0),
                    state.get(f"Server{server}_Latency_ms", 0),
                    status
                ))
            
            # Update ServerCPUWorkbench
            for server in range(1, 5):
                cursor.execute("""
                    MERGE ServerCPUWorkbench AS target
                    USING (
                        SELECT 
                            ? AS ServerNumber,
                            ? AS CPU_Percent,
                            ? AS UpdatedAt
                    ) AS source
                    ON target.ServerNumber = source.ServerNumber
                    WHEN MATCHED THEN
                        UPDATE SET
                            CPU_Percent = source.CPU_Percent,
                            UpdatedAt = source.UpdatedAt
                    WHEN NOT MATCHED THEN
                        INSERT (ServerNumber, CPU_Percent, UpdatedAt)
                        VALUES (source.ServerNumber, source.CPU_Percent, source.UpdatedAt);
                """, (
                    server,
                    state.get(f"Server{server}_CPU_Percent", 0),
                    now
                ))
            
            conn.commit()
            return True
            
    except Exception as e:
        print(f"❌ Error saving to database: {e}")
        db_connected = False
        return False

# ============================================================
# DATA PROCESSING FUNCTIONS
# ============================================================

def calculate_summary():
    """Calculate summary statistics from current state."""
    with LOCK:
        # Count active servers
        servers_up = sum(1 for i in range(1, 5) if state.get(f"Server{i}_Status", False))
        state["DC_Servers_Up"] = servers_up
        
        # Calculate average CPU (only for online servers)
        cpu_values = [state.get(f"Server{i}_CPU_Percent", 0) for i in range(1, 5) 
                     if state.get(f"Server{i}_Status", False)]
        state["DC_Avg_CPU"] = round(sum(cpu_values) / max(1, len(cpu_values)), 1) if cpu_values else 0
        
        # Calculate max temperature (only for online servers)
        temp_values = [state.get(f"Server{i}_Temp_C", 0) for i in range(1, 5)
                      if state.get(f"Server{i}_Status", False)]
        state["DC_Max_Temp"] = round(max(temp_values), 1) if temp_values else 0
        
        # Calculate total network traffic
        network_values = [state.get(f"Server{i}_Network_Mbps", 0) for i in range(1, 5)]
        state["DC_Total_Network"] = round(sum(network_values), 1)

def update_fake_data():
    """Generate fake data for simulation mode."""
    with LOCK:
        if state["Simulation_On"]:
            for server in range(1, 5):
                if state[f"Server{server}_Status"]:
                    # Update metrics with random walk
                    for metric, maximum in (
                        ("CPU_Percent", 100),
                        ("RAM_Percent", 100),
                        ("Disk_Percent", 100),
                        ("Temp_C", 100),
                        ("Network_Mbps", 300),
                        ("Latency_ms", 100)
                    ):
                        tag = f"Server{server}_{metric}"
                        change = random.uniform(-3.0, 3.0)
                        new_value = state[tag] + change
                        state[tag] = round(max(1, min(maximum, new_value)), 1)
                    
                    # Update alarms based on thresholds
                    state[f"Server{server}_CPU_Alarm"] = state[f"Server{server}_CPU_Percent"] >= 90
                    state[f"Server{server}_Temp_Alarm"] = state[f"Server{server}_Temp_C"] >= 75
                    state[f"Server{server}_Down_Alarm"] = not state[f"Server{server}_Status"]
        
        calculate_summary()
        save_to_database()

def simulator():
    """Background thread for data simulation."""
    while True:
        update_fake_data()
        time.sleep(2)

# ============================================================
# SERVER CONTROL FUNCTIONS
# ============================================================

def toggle_server(server):
    """Toggle server on/off."""
    with LOCK:
        tag = f"Server{server}_Status"
        state[tag] = not state[tag]

        if not state[tag]:
            # Server OFF - set all metrics to 0 or ambient
            state[f"Server{server}_CPU_Percent"] = 0
            state[f"Server{server}_RAM_Percent"] = 0
            state[f"Server{server}_Disk_Percent"] = 0
            state[f"Server{server}_Temp_C"] = 25
            state[f"Server{server}_Network_Mbps"] = 0
            state[f"Server{server}_Latency_ms"] = 0
            state[f"Server{server}_Down_Alarm"] = True
        else:
            # Server ON - restore to normal values
            state[f"Server{server}_CPU_Percent"] = random.uniform(20, 40)
            state[f"Server{server}_RAM_Percent"] = random.uniform(30, 50)
            state[f"Server{server}_Disk_Percent"] = random.uniform(40, 60)
            state[f"Server{server}_Temp_C"] = random.uniform(35, 45)
            state[f"Server{server}_Network_Mbps"] = random.uniform(70, 120)
            state[f"Server{server}_Latency_ms"] = random.uniform(6, 15)
            state[f"Server{server}_Down_Alarm"] = False
            state[f"Server{server}_CPU_Alarm"] = False
            state[f"Server{server}_Temp_Alarm"] = False

        calculate_summary()
        save_to_database()

def stress_server(server):
    """Apply stress to a server."""
    with LOCK:
        if not state.get(f"Server{server}_Status", False):
            return False

        state[f"Server{server}_CPU_Percent"] = min(
            100,
            state[f"Server{server}_CPU_Percent"] + random.uniform(20, 40)
        )

        state[f"Server{server}_RAM_Percent"] = min(
            100,
            state[f"Server{server}_RAM_Percent"] + random.uniform(10, 20)
        )

        state[f"Server{server}_Temp_C"] = min(
            100,
            state[f"Server{server}_Temp_C"] + random.uniform(8, 15)
        )

        calculate_summary()
        save_to_database()
        return True

def reset_server(server):
    """Reset server to normal state."""
    with LOCK:
        state[f"Server{server}_CPU_Percent"] = random.uniform(20, 40)
        state[f"Server{server}_RAM_Percent"] = random.uniform(30, 50)
        state[f"Server{server}_Disk_Percent"] = random.uniform(40, 60)
        state[f"Server{server}_Temp_C"] = random.uniform(35, 45)
        state[f"Server{server}_Network_Mbps"] = random.uniform(70, 120)
        state[f"Server{server}_Latency_ms"] = random.uniform(6, 15)

        state[f"Server{server}_CPU_Alarm"] = False
        state[f"Server{server}_Temp_Alarm"] = False
        state[f"Server{server}_Down_Alarm"] = False
        state[f"Server{server}_Status"] = True

        calculate_summary()
        save_to_database()
        return True

def toggle_simulation():
    """Toggle simulation on/off."""
    with LOCK:
        state["Simulation_On"] = not state["Simulation_On"]
        save_to_database()
        return state["Simulation_On"]

# ============================================================
# HTTP SERVER HANDLER
# ============================================================

class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_json(self, payload):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(HTTPStatus.OK)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_dashboard_html(self, requested_path):
        if requested_path in ('/', ''):
            page = ROOT / 'index.html'
        else:
            page = ROOT / requested_path.lstrip('/')
        
        if not page.is_file() or page.suffix.lower() != '.html':
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        
        content = page.read_text(encoding='utf-8')
        if '</body>' in content and 'dashboard-client.js' not in content:
            content = content.replace('</body>', '<script src="/dashboard-client.js"></script></body>')
        
        body = content.encode('utf-8')
        self.send_response(HTTPStatus.OK)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        request = urlparse(self.path)
        
        # API ENDPOINTS
        if request.path == '/api/toggle':
            try:
                server = int(parse_qs(request.query)['server'][0])
                success = toggle_server(server)
                self.send_json({'success': success})
            except (KeyError, ValueError, IndexError):
                self.send_json({'success': False, 'error': 'Invalid server parameter'})
            return

        if request.path == '/api/stress':
            try:
                server = int(parse_qs(request.query)['server'][0])
                success = stress_server(server)
                self.send_json({'success': success})
            except (KeyError, ValueError, IndexError):
                self.send_json({'success': False, 'error': 'Invalid server parameter'})
            return

        if request.path == '/api/reset':
            try:
                server = int(parse_qs(request.query)['server'][0])
                success = reset_server(server)
                self.send_json({'success': success})
            except (KeyError, ValueError, IndexError):
                self.send_json({'success': False, 'error': 'Invalid server parameter'})
            return

        if request.path == '/api/toggle_simulation':
            try:
                sim_status = toggle_simulation()
                self.send_json({'success': True, 'simulation_on': sim_status})
            except Exception as e:
                self.send_json({'success': False, 'error': str(e)})
            return

        if request.path == '/api/refresh':
            update_fake_data()
            self.send_json({'success': True})
            return

        if request.path == '/api/state':
            with LOCK:
                self.send_json({
                    'timestamp': datetime.now().isoformat(),
                    'tags': state.copy()
                })
            return

        if request.path == '/api/history':
            try:
                server = int(parse_qs(request.query).get('server', [1])[0])
                if db_connected:
                    conn = get_connection()
                    if conn:
                        with conn:
                            cursor = conn.cursor()
                            cursor.execute("""
                                SELECT TOP 60 
                                    RecordedAt, CPU_Percent, RAM_Percent, Disk_Percent, 
                                    Temperature_C, Network_Mbps, Latency_ms
                                FROM ServerHistory 
                                WHERE ServerNumber = ? 
                                ORDER BY Id DESC
                            """, (server,))
                            rows = cursor.fetchall()
                            
                        result = []
                        for row in reversed(rows):
                            result.append({
                                'timestamp': row[0].isoformat() if row[0] else None,
                                'cpu': row[1],
                                'ram': row[2],
                                'disk': row[3],
                                'temperature': row[4],
                                'network': row[5],
                                'latency': row[6]
                            })
                        self.send_json(result)
                    else:
                        self.send_json([])
                else:
                    self.send_json([])
            except Exception as e:
                self.send_json({'error': str(e)})
            return

        if request.path == '/api/events':
            try:
                if db_connected:
                    conn = get_connection()
                    if conn:
                        with conn:
                            cursor = conn.cursor()
                            cursor.execute("""
                                SELECT TOP 25 
                                    EventTime, ServerNumber, EventName, Severity
                                FROM AlarmEvents 
                                ORDER BY Id DESC
                            """)
                            rows = cursor.fetchall()
                        
                        result = []
                        for row in rows:
                            result.append({
                                'timestamp': row[0].isoformat() if row[0] else None,
                                'server': row[1],
                                'event': row[2],
                                'status': row[3]
                            })
                        self.send_json(result)
                    else:
                        self.send_json([])
                else:
                    self.send_json([])
            except Exception as e:
                self.send_json({'error': str(e)})
            return

        if request.path == '/api/info':
            """Get system information"""
            tag_count = 0
            event_count = 0
            if db_connected:
                try:
                    conn = get_connection()
                    if conn:
                        with conn:
                            cursor = conn.cursor()
                            cursor.execute("SELECT COUNT(*) FROM LatestTagValues")
                            tag_count = cursor.fetchone()[0]
                            
                            cursor.execute("SELECT COUNT(*) FROM AlarmEvents")
                            event_count = cursor.fetchone()[0]
                except:
                    pass
            
            self.send_json({
                'simulation_mode': state.get('Simulation_On', True),
                'database_connected': db_connected,
                'database_type': 'SQL Express 2022',
                'timestamp': datetime.now().isoformat(),
                'total_tags': len(state),
                'tags_in_db': tag_count,
                'events_in_db': event_count
            })
            return

        # Serve HTML pages
        if request.path in ('/', '') or request.path.endswith('.html'):
            self.send_dashboard_html(request.path)
            return

        # Serve static files
        super().do_GET()

# ============================================================
# DATABASE TEST FUNCTION
# ============================================================

def test_sql_express():
    """Test function to verify SQL Express 2022 connection."""
    global db_connected
    
    print("\n" + "=" * 70)
    print("🧪 TESTING SQL EXPRESS 2022 CONNECTION")
    print("=" * 70)
    
    # Test 1: Check if ODBC Driver is installed
    try:
        drivers = [x for x in pyodbc.drivers() if 'SQL Server' in x]
        print(f"\n📋 Available ODBC Drivers:")
        for driver in drivers:
            print(f"   - {driver}")
        
        if 'ODBC Driver 17 for SQL Server' not in drivers:
            print("\n⚠️  Warning: ODBC Driver 17 for SQL Server not found!")
            print("   Please install it from: https://go.microsoft.com/fwlink/?linkid=2249006")
            db_connected = False
            return False
    except Exception as e:
        print(f"❌ Error checking drivers: {e}")
        db_connected = False
        return False
    
    # Test 2: Try to connect
    print("\n" + "-" * 70)
    print("🔌 Attempting to connect to SQL Express 2022...")
    print(f"   Server: localhost\\SQLEXPRESS")
    print(f"   Database: DataCenterKPI")
    print(f"   Authentication: Windows Authentication")
    print("-" * 70)
    
    try:
        conn = get_connection()
        if conn is None:
            print("\n❌ Connection test FAILED!")
            print("   Could not establish connection to SQL Server")
            print("\n   Troubleshooting tips:")
            print("   1. Make sure SQL Server Express 2022 is running")
            print("   2. Verify the server name is correct")
            print("   3. Check if Windows Authentication is enabled")
            print("   4. Verify the database 'DataCenterKPI' exists")
            print("   5. Make sure TCP/IP is enabled in SQL Server Configuration")
            db_connected = False
            return False
            
        with conn:
            cursor = conn.cursor()
            
            # Check if database exists
            cursor.execute("SELECT DB_NAME()")
            db_name = cursor.fetchone()[0]
            print(f"✅ Connected to database: {db_name}")
            
            # Check tables
            cursor.execute("""
                SELECT TABLE_NAME 
                FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_NAME
            """)
            tables = cursor.fetchall()
            
            print(f"\n📊 Tables in database:")
            if tables:
                for table in tables:
                    table_name = table[0]
                    try:
                        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                        count = cursor.fetchone()[0]
                        print(f"   - {table_name}: {count} rows")
                    except:
                        print(f"   - {table_name}: (count unavailable)")
            else:
                print("   (No tables found - database may need initialization)")
            
            db_connected = True
            print("\n✅ SQL Express 2022 connection test PASSED!")
            return True
            
    except Exception as e:
        print(f"\n❌ Connection test FAILED!")
        print(f"   Error: {e}")
        print("\n   Troubleshooting tips:")
        print("   1. Make sure SQL Server Express 2022 is running")
        print("   2. Verify the server name is correct")
        print("   3. Check if Windows Authentication is enabled")
        print("   4. Verify the database 'DataCenterKPI' exists")
        print("   5. Make sure TCP/IP is enabled in SQL Server Configuration")
        print("   6. Check if firewall is blocking the connection")
        db_connected = False
        return False

# ============================================================
# MAIN ENTRY POINT
# ============================================================

if __name__ == '__main__':
    print("=" * 70)
    print("🏢 DATA CENTER DASHBOARD BACKEND")
    print("   SQL Express 2022 Version")
    print("=" * 70)
    
    # First, test the connection
    test_sql_express()
    
    print("\n" + "=" * 70)
    print("⚙️  INITIALIZING APPLICATION")
    print("=" * 70)
    
    # Initialize database tables if connected
    if db_connected:
        print("\n📦 Creating database tables if needed...")
        if init_database():
            print("✅ Database tables ready")
            # Load existing data
            print("\n📥 Loading existing data from database...")
            if load_state_from_database():
                print("✅ Data loaded successfully")
            else:
                print("ℹ️  No existing data found. Starting with fresh state.")
        else:
            print("⚠️  Database initialization failed. Running in memory-only mode.")
    else:
        print("\n⚠️  Database not connected. Running in memory-only mode.")
        print("   (Data will not be persisted across restarts)")
    
    # Start simulator thread
    threading.Thread(target=simulator, daemon=True).start()
    print("✅ Simulator thread started (updates every 2 seconds)")
    
    # Start HTTP server
    print("\n" + "=" * 70)
    print("🌐 HTTP SERVER STARTING")
    print("=" * 70)
    print("   URL: http://localhost:8000/index.html")
    print("   Dashboard will auto-refresh every 2 seconds")
    print("=" * 70)
    print("\n📋 Available API Endpoints:")
    print("   GET  /api/state              - Get all tag values")
    print("   GET  /api/history            - Get server history")
    print("   GET  /api/events             - Get alarm events")
    print("   GET  /api/toggle             - Toggle server (server=1-4)")
    print("   GET  /api/stress             - Stress server (server=1-4)")
    print("   GET  /api/reset              - Reset server (server=1-4)")
    print("   GET  /api/toggle_simulation  - Start/Stop simulation")
    print("   GET  /api/info               - System information")
    print("   GET  /api/refresh            - Force data refresh")
    print("=" * 70)
    print("\n💡 Press Ctrl+C to stop the server")
    print("=" * 70)
    
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 8000), DashboardHandler)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped by user")
    except Exception as e:
        print(f"\n❌ Server error: {e}")