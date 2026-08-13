# check_python_arch.py
import struct
import sys

print("=" * 60)
print("🐍 PYTHON ARCHITECTURE CHECK")
print("=" * 60)
print(f"Python Version: {sys.version}")
print(f"Architecture: {struct.calcsize('P') * 8}-bit")
print(f"Platform: {sys.platform}")
print("=" * 60)

if struct.calcsize('P') * 8 == 64:
    print("\n⚠️  You are using 64-bit Python")
    print("   InTouch COM components are typically 32-bit")
    print("   You may need to install 32-bit Python")
    print("\n📥 Download 32-bit Python from:")
    print("   https://www.python.org/downloads/windows/")
    print("   (Look for 'Windows x86 executable installer')")
else:
    print("\n✅ You are using 32-bit Python (correct for InTouch COM)")