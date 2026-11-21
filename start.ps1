# Start the prototype on this PC. Three windows: dashboard, face camera, chatbot.
# If Gemini wording is wanted, set GEMINI_API_KEY in this window before running.
# The key is not written to a file.

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$vision = "D:\AVEVA\backend2\SCADAPROJECT"

Start-Process powershell -WorkingDirectory $root -ArgumentList "-NoExit", "-Command", "python -u server2.py"
Start-Process powershell -WorkingDirectory $vision -ArgumentList "-NoExit", "-Command", ".\.venv\Scripts\python.exe -u vision_web.py"
Start-Process powershell -WorkingDirectory $root -ArgumentList "-NoExit", "-Command", "python -u chatbot_server.py"

Write-Output "Dashboard: http://127.0.0.1:8000/"
Write-Output "Face camera: http://127.0.0.1:8002/status"
Write-Output "Chatbot: http://127.0.0.1:8001/"
