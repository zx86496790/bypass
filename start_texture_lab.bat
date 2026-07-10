@echo off
cd /d "%~dp0"
title Texture Lab Local Server
echo.
echo Texture Lab is starting...
echo.
echo Open this URL in your browser:
echo http://127.0.0.1:8765/
echo.
echo Keep this window open while using the app.
echo Press Ctrl+C to stop the server.
echo.
D:\python\python.exe server.py
echo.
echo Server stopped. Press any key to close this window.
pause >nul
