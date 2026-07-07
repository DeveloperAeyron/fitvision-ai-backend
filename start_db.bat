@echo off
echo Starting Portable PostgreSQL...
postgres-portable\pgsql\bin\pg_ctl.exe start -D postgres-data -l pg_server.log
pause
