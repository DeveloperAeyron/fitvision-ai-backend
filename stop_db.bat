@echo off
echo Stopping Portable PostgreSQL...
postgres-portable\pgsql\bin\pg_ctl.exe stop -D postgres-data
pause
