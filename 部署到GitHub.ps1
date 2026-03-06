# 一键准备并推送到 GitHub（需先安装 Git 并创建好空仓库）
# 用法：在 PowerShell 中执行 .\部署到GitHub.ps1
# 然后按提示在 GitHub 创建仓库，再执行脚本里最后两行命令

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "未检测到 Git。请先安装：https://git-scm.com/download/win" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path .git)) {
    git init
    Write-Host "已初始化 Git 仓库。" -ForegroundColor Green
}

git add app.py requirements.txt DEPLOY.md .streamlit .gitignore
if (Test-Path "packages.txt") { git add packages.txt }
git add *.md 2>$null
git status

# 避免误加密钥（.gitignore 应已包含）
git reset -- client_secret.json google_token.json 2>$null

$msg = "MyAIPlanner: 准备云端部署"
git add -A
git status
$confirm = Read-Host "确认提交并准备推送？(y/n)"
if ($confirm -eq "y" -or $confirm -eq "Y") {
    git commit -m $msg
    Write-Host ""
    Write-Host "接下来请：" -ForegroundColor Cyan
    Write-Host "1. 打开 https://github.com/new 创建新仓库（如 MyAIPlanner），不要勾选 README" -ForegroundColor White
    Write-Host "2. 在本目录执行（把 你的用户名 换成你的 GitHub 用户名）：" -ForegroundColor White
    Write-Host "   git remote add origin https://github.com/你的用户名/MyAIPlanner.git" -ForegroundColor Yellow
    Write-Host "   git branch -M main" -ForegroundColor Yellow
    Write-Host "   git push -u origin main" -ForegroundColor Yellow
    Write-Host "3. 按提示输入 GitHub 用户名和密码（或 Personal Access Token）" -ForegroundColor White
}
