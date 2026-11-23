# Start the prototype on this PC. RabbitMQ, then dashboard, face camera, and chatbot.
# If Gemini wording is wanted, set GEMINI_API_KEY in this window before running.
# The key is not written to a file.

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$vision = "D:\AVEVA\backend2\SCADAPROJECT"

$rabbit = Get-Service -Name "RabbitMQ" -ErrorAction SilentlyContinue
if ($rabbit) {
    if ($rabbit.Status -ne "Running") { Start-Service RabbitMQ }
    Write-Output "RabbitMQ: http://127.0.0.1:5672/"
} else {
    Write-Output "RabbitMQ service was not found. Events use the broker when it is running on 127.0.0.1:5672."
    Write-Output "Install Erlang first: winget install --id Erlang.ErlangOTP -e --version 28.5"
    Write-Output "Then run the RabbitMQ 4.4.1 Windows installer from https://github.com/rabbitmq/rabbitmq-server/releases/download/v4.4.1/rabbitmq-server-4.4.1.exe"
}

Start-Process powershell -WorkingDirectory $root -ArgumentList "-NoExit", "-Command", "python -u server2.py"
Start-Process powershell -WorkingDirectory $vision -ArgumentList "-NoExit", "-Command", ".\.venv\Scripts\python.exe -u vision_web.py"
Start-Process powershell -WorkingDirectory $root -ArgumentList "-NoExit", "-Command", "python -u chatbot_server.py"

Write-Output "Dashboard: http://127.0.0.1:8000/"
Write-Output "Face camera: http://127.0.0.1:8002/status"
Write-Output "Chatbot: http://127.0.0.1:8001/"
