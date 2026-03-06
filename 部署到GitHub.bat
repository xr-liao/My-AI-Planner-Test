@echo off
chcp 65001 >nul
cd /d "%~dp0"

where git >nul 2>nul
if errorlevel 1 (
    echo 未检测到 Git，请先安装：https://git-scm.com/download/win
    pause
    exit /b 1
)

if not exist .git (
    git init
    echo 已初始化 Git 仓库。
)

git add app.py requirements.txt DEPLOY.md .streamlit .gitignore
git add *.md 2>nul
git reset -- client_secret.json google_token.json 2>nul
git add -A
git status
echo.
set /p confirm=确认提交？(y/n): 
if /i "%confirm%"=="y" (
    git commit -m "MyAIPlanner: 准备云端部署"
    echo.
    echo 接下来请：
    echo 1. 打开 https://github.com/new 创建新仓库（如 MyAIPlanner），不要勾选 README
    echo 2. 若已添加过 origin，先改地址：git remote set-url origin https://github.com/你的用户名/仓库名.git
    echo    未添加过则：git remote add origin https://github.com/你的用户名/仓库名.git
    echo    git branch -M main
    echo    git push -u origin main
    echo 3. 按提示输入 GitHub 用户名和密码（或 Token）
)
pause
