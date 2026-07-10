To run this service:
- Download Python
- CD into CallMeRocki
- poetry install --no-root
- Configure the env file
- Start the server with poetry run python -m uvicorn main:app --app-dir src --host 0.0.0.0 --port 8787 --reload

Test published service:
- Invoke-RestMethod -Method Get -Uri "https://callmerocki.onrender.com/health"

- Create your bot:
try {
   $body = @{
     meeting_url = "<your-zoom-link>"
     bot_name    = "CallMeRocki"
   } | ConvertTo-Json
    Invoke-RestMethod -Method Post -Uri "https://callmerocki.onrender.com/recall/bot" -ContentType "application/json" -Body $body
} catch {
   $resp = $_.Exception.Response
   if ($resp -and $resp.GetResponseStream()) {
     $reader = New-Object System.IO.StreamReader($resp.GetResponseStream())
     $reader.ReadToEnd()
   } else {
     $_ | Out-String
   }
 }