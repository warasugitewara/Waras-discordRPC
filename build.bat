@echo off
setlocal

where pyinstaller >nul 2>nul
if errorlevel 1 (
    echo [ERROR] pyinstaller が見つかりません。venv を有効化してから実行してください。
    exit /b 1
)

pyinstaller build.spec --noconfirm --clean
if errorlevel 1 (
    echo [ERROR] PyInstaller のビルドに失敗しました。
    exit /b 1
)

copy /y config.example.json dist\WarasDiscordRPC\config.example.json >nul
copy /y .env.example dist\WarasDiscordRPC\.env.example >nul
copy /y start.bat dist\WarasDiscordRPC\start.bat >nul

echo.
echo ビルド完了: dist\WarasDiscordRPC\
echo 配布前に .env.example / config.example.json が同梱されていることを確認してください。
endlocal
