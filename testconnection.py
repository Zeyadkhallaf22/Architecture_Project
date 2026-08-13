import pyodbc

print("=" * 70)
print("🔍 TESTING SQL SERVER CONNECTIONS")
print("=" * 70)
print()

# First, check what drivers are available
print("📋 Available ODBC Drivers:")
drivers = pyodbc.drivers()
for driver in drivers:
    if 'SQL Server' in driver:
        print(f"   - {driver}")
print()

# List all possible connection strings to test
connection_strings = [
    # Based on your SSMS history
    (
        'localhost\\SQLEXPRESS',
        'DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost\\SQLEXPRESS;DATABASE=DataCenterKPI;Trusted_Connection=yes;'
    ),
    (
        'MARIAM\\SQLEXPRESS01',
        'DRIVER={ODBC Driver 17 for SQL Server};SERVER=MARIAM\\SQLEXPRESS01;DATABASE=DataCenterKPI;Trusted_Connection=yes;'
    ),
    (
        'MARIAM\\MSSQLSERVER03',
        'DRIVER={ODBC Driver 17 for SQL Server};SERVER=MARIAM\\MSSQLSERVER03;DATABASE=DataCenterKPI;Trusted_Connection=yes;'
    ),
    # Try without instance name
    (
        'localhost',
        'DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost;DATABASE=DataCenterKPI;Trusted_Connection=yes;'
    ),
    (
        'MARIAM',
        'DRIVER={ODBC Driver 17 for SQL Server};SERVER=MARIAM;DATABASE=DataCenterKPI;Trusted_Connection=yes;'
    ),
    # Try with different drivers
    (
        'localhost\\SQLEXPRESS (Driver 18)',
        'DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost\\SQLEXPRESS;DATABASE=DataCenterKPI;Trusted_Connection=yes;Encrypt=no;'
    ),
    (
        'localhost\\SQLEXPRESS (Driver 13)',
        'DRIVER={ODBC Driver 13 for SQL Server};SERVER=localhost\\SQLEXPRESS;DATABASE=DataCenterKPI;Trusted_Connection=yes;'
    ),
    # Try with SQL Authentication (if you have credentials)
    # (
    #     'localhost\\SQLEXPRESS (SQL Auth)',
    #     'DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost\\SQLEXPRESS;DATABASE=DataCenterKPI;UID=sa;PWD=your_password;'
    # ),
]

print("Testing each connection...")
print("-" * 70)

working_connection = None

for name, conn_str in connection_strings:
    print(f"\n🔌 Testing: {name}")
    try:
        conn = pyodbc.connect(conn_str, timeout=5)
        print(f"   ✅ SUCCESS! Connected to {name}")
        
        # Test if we can query
        cursor = conn.cursor()
        cursor.execute("SELECT DB_NAME()")
        db_name = cursor.fetchone()[0]
        print(f"   📊 Database: {db_name}")
        
        cursor.execute("SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES")
        table_count = cursor.fetchone()[0]
        print(f"   📊 Tables: {table_count}")
        
        conn.close()
        working_connection = conn_str
        print(f"\n🎯 WORKING CONNECTION STRING FOUND!")
        print(f"   {conn_str}")
        break
    except pyodbc.Error as e:
        error_code = e.args[0] if e.args else "Unknown"
        error_msg = e.args[1] if len(e.args) > 1 else "No message"
        print(f"   ❌ Failed: {error_code}")
        if "Cannot open database" in error_msg:
            print(f"      Database 'DataCenterKPI' might not exist")
        elif "Login timeout" in error_msg:
            print(f"      Connection timeout - check if SQL Server is running")
        elif "Named Pipes" in error_msg or "TCP/IP" in error_msg:
            print(f"      Network issue - check TCP/IP is enabled")
    except Exception as e:
        print(f"   ❌ Failed: {str(e)[:100]}")

print("\n" + "=" * 70)
if working_connection:
    print("✅ Found a working connection!")
    print(f"\nUse this in your server.py:")
    print(f"CONNECTION_STRING = '{working_connection}'")
else:
    print("❌ No working connection found. Try these fixes:")
    print("\n1. Check if SQL Server is running:")
    print("   - Open Services (Win + R, type 'services.msc')")
    print("   - Find 'SQL Server (SQLEXPRESS)' and ensure it's running")
    print("\n2. Enable TCP/IP in SQL Server Configuration Manager:")
    print("   - Open SQL Server Configuration Manager")
    print("   - SQL Server Network Configuration → Protocols for SQLEXPRESS")
    print("   - Enable TCP/IP")
    print("   - Restart SQL Server service")
    print("\n3. Check SQL Server Browser service:")
    print("   - In Services, find 'SQL Server Browser'")
    print("   - Start it if it's stopped")
    print("\n4. Verify the database exists:")
    print("   - Open SSMS and check if 'DataCenterKPI' database exists")
print("=" * 70)