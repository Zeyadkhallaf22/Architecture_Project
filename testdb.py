"""Test script for SQL Express 2022 connection"""

import pyodbc

# Connection string for Windows Authentication
CONNECTION_STRING = (
    'DRIVER={ODBC Driver 17 for SQL Server};'
    'SERVER=MARIAM\\SQLEXPRESS01;'
    'DATABASE=DataCenter;'
    'Trusted_Connection=yes;'
)

def test_connection():
    print("=" * 60)
    print("🧪 SQL EXPRESS 2022 CONNECTION TEST")
    print("=" * 60)
    
    # Check available drivers
    print("\n📋 Available ODBC Drivers:")
    try:
        drivers = pyodbc.drivers()
        for driver in drivers:
            if 'SQL Server' in driver:
                print(f"   ✓ {driver}")
    except Exception as e:
        print(f"   ❌ Error listing drivers: {e}")
    
    print("\n" + "-" * 60)
    print("🔌 Attempting to connect...")
    print(f"   Server: MARIAM\\SQLEXPRESS01")
    print(f"   Database: DataCenter")
    print(f"   Authentication: Windows")
    print("-" * 60)
    
    try:
        conn = pyodbc.connect(CONNECTION_STRING, timeout=10)
        cursor = conn.cursor()
        
        # Get database name
        cursor.execute("SELECT DB_NAME()")
        db_name = cursor.fetchone()[0]
        print(f"✅ Connected to: {db_name}")
        
        # Get SQL Server version
        cursor.execute("SELECT @@VERSION")
        version = cursor.fetchone()[0]
        print(f"✅ SQL Server Version: {version[:50]}...")
        
        # List tables
        cursor.execute("""
            SELECT TABLE_NAME, 
                   (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES t2 WHERE t2.TABLE_NAME = t.TABLE_NAME) as row_count
            FROM INFORMATION_SCHEMA.TABLES t
            WHERE TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME
        """)
        tables = cursor.fetchall()
        
        if tables:
            print(f"\n📊 Tables in database ({len(tables)}):")
            for table in tables:
                # Get row count for each table
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table[0]}")
                    count = cursor.fetchone()[0]
                    print(f"   - {table[0]}: {count} rows")
                except:
                    print(f"   - {table[0]}: (unable to count)")
        else:
            print("\nℹ️  No tables found in database")
            
        conn.close()
        print("\n" + "=" * 60)
        print("✅ TEST PASSED - Connection successful!")
        print("=" * 60)
        return True
        
    except pyodbc.Error as e:
        print(f"\n❌ CONNECTION FAILED!")
        print(f"   Error: {e}")
        print("\n🔧 Troubleshooting Tips:")
        print("   1. Make sure SQL Server Express 2022 is running")
        print("      - Press Win+R, type 'services.msc'")
        print("      - Find 'SQL Server (SQLEXPRESS)'")
        print("      - Make sure it's started")
        print("\n   2. Verify server name:")
        print("      - Default: .\\SQLEXPRESS")
        print("      - Or: (local)\\SQLEXPRESS")
        print("      - Or: your_computer_name\\SQLEXPRESS01")
        print("\n   3. Check if Windows Authentication is enabled")
        print("   4. Verify the database 'DataCenter' exists")
        print("   5. Check firewall settings")
        print("   6. Ensure TCP/IP is enabled in SQL Server Configuration Manager")
        print("=" * 60)
        return False
    
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    test_connection()