@echo off
start "Super Shop API" cmd /k "%~dp0run_backend.bat"
start "Super Shop Web" cmd /k "%~dp0run_frontend.bat"
echo API: http://localhost:8000/docs   Web: http://localhost:3000
