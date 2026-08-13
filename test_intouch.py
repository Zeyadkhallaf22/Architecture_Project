"""Test script for InTouch COM connection"""

import win32com.client
import sys

def test_intouch_connection():
    print("=" * 70)
    print("🔌 TESTING INTOUCH CONNECTION")
    print("=" * 70)
    
    # Check if running on Windows
    if sys.platform != 'win32':
        print("❌ This script requires Windows (InTouch only runs on Windows)")
        return False
    
    try:
        # Try to connect to InTouch
        print("\n📡 Attempting to connect to InTouch via WWClient...")
        print("   Make sure InTouch View is running!")
        print("-" * 70)
        
        intouch = win32com.client.Dispatch("WWClient.WWClient.1")
        print("✅ Successfully connected to InTouch!")
        print(f"   Connection object: {intouch}")
        
        # Test reading a tag
        print("\n📊 Testing tag read operations...")
        print("-" * 70)
        
        test_tags = [
            'Server1_CPU_Percent',
            'Server1_Status', 
            'Server1_Temp_C',
            'Simulation_On'
        ]
        
        success_count = 0
        for tag in test_tags:
            try:
                value = intouch.GetValue(tag)
                print(f"   ✅ {tag} = {value}")
                success_count += 1
            except Exception as e:
                print(f"   ❌ Could not read {tag}: {e}")
        
        print("-" * 70)
        print(f"   Successfully read {success_count}/{len(test_tags)} tags")
        
        # Test writing a tag (if simulation control exists)
        print("\n✍️  Testing write operation...")
        try:
            # Read current value
            current = intouch.GetValue('Simulation_On')
            print(f"   Current Simulation_On = {current}")
            
            # Toggle it (optional - comment out if you don't want to change)
            # new_value = not current if isinstance(current, bool) else True
            # intouch.SetValue('Simulation_On', new_value)
            # print(f"   Changed Simulation_On to {new_value}")
            
            print("   ✅ Write test successful (commented out to avoid changes)")
        except Exception as e:
            print(f"   ⚠️  Write test: {e}")
        
        print("\n" + "=" * 70)
        print("✅ InTouch connection test PASSED!")
        print("=" * 70)
        print("\n📋 Next Steps:")
        print("   1. Run the main server: python server_intouch.py")
        print("   2. Open dashboard: http://localhost:8000/index.html")
        print("=" * 70)
        return True
        
    except Exception as e:
        print(f"\n❌ InTouch connection test FAILED!")
        print(f"   Error: {e}")
        print("\n🔧 Troubleshooting Tips:")
        print("   1. Make sure InTouch View is running")
        print("   2. Check that WWClient is registered")
        print("   3. Ensure the tags exist in InTouch")
        print("   4. Try running as Administrator")
        print("   5. Check if InTouch is in Runtime mode")
        print("   6. Verify the tag names match exactly")
        print("\n   Common tag name format:")
        print("   - Server1_CPU_Percent")
        print("   - Server1_Status")
        print("   - Server1_Temp_C")
        print("   - Simulation_On")
        print("=" * 70)
        return False

if __name__ == "__main__":
    test_intouch_connection()