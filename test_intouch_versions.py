"""Test different InTouch COM object names"""

import win32com.client
import sys

def test_com_objects():
    print("=" * 70)
    print("🔍 TESTING INTOUCH COM OBJECTS")
    print("=" * 70)
    
    # List of possible InTouch COM object names
    com_objects = [
        "WWClient.WWClient.1",
        "InTouch.WWClient.1",
        "Wonderware.WWClient.1",
        "WWClient.Application",
        "InTouch.Application",
        "Wonderware.Application",
        "Aveva.WWClient.1",
        "Aveva.Application"
    ]
    
    print("\n📡 Testing different COM object names...")
    print("   (Make sure InTouch View is running)")
    print("-" * 70)
    
    found_objects = []
    
    for obj_name in com_objects:
        try:
            test_obj = win32com.client.Dispatch(obj_name)
            print(f"   ✅ SUCCESS: {obj_name}")
            found_objects.append(obj_name)
            # Try to get a property to verify
            try:
                version = test_obj.Version if hasattr(test_obj, 'Version') else "Unknown"
                print(f"      Version: {version}")
            except:
                pass
        except Exception as e:
            print(f"   ❌ {obj_name}: {str(e)[:50]}...")
    
    print("-" * 70)
    
    if found_objects:
        print(f"\n✅ Found {len(found_objects)} working COM object(s):")
        for obj in found_objects:
            print(f"   - {obj}")
        print("\n📝 Use this in your server code:")
        print(f"   intouch = win32com.client.Dispatch('{found_objects[0]}')")
        return found_objects[0]
    else:
        print("\n❌ No InTouch COM objects found!")
        print("\n🔧 Troubleshooting:")
        print("   1. Make sure InTouch View is running")
        print("   2. Check if you're on the right machine (InTouch must be installed)")
        print("   3. Try running as Administrator")
        print("   4. Check if InTouch is in Runtime mode")
        print("   5. Verify InTouch is properly installed")
        return None

if __name__ == "__main__":
    test_com_objects()