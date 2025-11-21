# Windows PowerShell 脚本 - 快速更新服务器代码

Write-Host "正在上传最新代码到服务器..." -ForegroundColor Green

# 请修改为你的服务器 IP
$serverIp = "your-server-ip"
$serverUser = "ubuntu"
$serverPath = "~/Documents/projects/mcp_mysql/mcp_mysql/"

# 上传 server.py
scp mcp_mysql/server.py "${serverUser}@${serverIp}:${serverPath}"

Write-Host ""
Write-Host "代码已上传！" -ForegroundColor Green
Write-Host ""
Write-Host "现在请在服务器上运行以下命令来清除缓存并重启：" -ForegroundColor Yellow
Write-Host ""
Write-Host "cd ~/Documents/projects/mcp_mysql" -ForegroundColor Cyan
Write-Host "find . -name '*.pyc' -delete" -ForegroundColor Cyan
Write-Host "find . -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true" -ForegroundColor Cyan
Write-Host "python -m mcp_mysql.server" -ForegroundColor Cyan
