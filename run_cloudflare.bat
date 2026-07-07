@echo off
echo Starting Cloudflare Tunnel to expose local backend on port 8000...
echo Ensure you have cloudflared installed. If not, download from https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
echo.
cloudflared tunnel --url http://localhost:8000
pause
