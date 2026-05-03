Get-Process python* -ErrorAction SilentlyContinue | Stop-Process -Force
Remove-Item ".tonmindbot.lock" -Force -ErrorAction SilentlyContinue
Write-Host "Bot stopped."
