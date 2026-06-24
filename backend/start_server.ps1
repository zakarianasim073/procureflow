$env:PYTHONUTF8="1"
$logFile = "server_stdout2.log"
$errFile = "server_stderr2.log"
$python = "C:\Program Files\Python310\python.exe"
$args = @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000")

$process = Start-Process -NoNewWindow -PassThru -FilePath $python -ArgumentList $args -WorkingDirectory "D:\A1\procurementflow_final_v3\procurementflow\backend" -RedirectStandardOutput $logFile -RedirectStandardError $errFile
Write-Output "Server PID: $($process.Id)"
