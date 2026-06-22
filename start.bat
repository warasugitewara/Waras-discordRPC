@echo off
setlocal
cd /d "%~dp0"

if not exist ".env" (
    if exist ".env.example" (
        copy /y ".env.example" ".env" >nul
        echo .env を作成しました。DISCORD_CLIENT_ID と BRIDGE_TOKEN を編集してから再度このファイルを実行してください。
        pause
        exit /b 0
    ) else (
        echo [ERROR] .env も .env.example も見つかりません。配布物が不完全です。
        pause
        exit /b 1
    )
)

start "" "WarasDiscordRPC.exe"
endlocal
