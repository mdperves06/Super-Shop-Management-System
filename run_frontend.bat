@echo off
REM Starts the web app on http://localhost:3000
cd /d "%~dp0frontend"
if not exist .env.local copy .env.example .env.local
if not exist node_modules ( npm install )
npm run dev
