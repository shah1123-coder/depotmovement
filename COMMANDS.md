# Depot Movement Deployment Commands

## Local Docker Start

```powershell
cd C:\Users\Archeet.Shah\Documents\depotmovement
docker compose up --build -d redis worker beat
docker compose ps
docker compose logs --tail=40 worker beat
```

## Remote Deploy To Azure Server

```powershell
cd C:\Users\Archeet.Shah
Set-PSRepository -Name PSGallery -InstallationPolicy Trusted
Install-Module -Name Posh-SSH -Scope CurrentUser -Force -AllowClobber
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
Import-Module Posh-SSH
```

```powershell
$project = 'C:\Users\Archeet.Shah\Documents\depotmovement'
$zip = Join-Path $env:TEMP 'depotmovement-deploy.zip'
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
Compress-Archive -Path (Join-Path $project '*') -DestinationPath $zip -Force
```

```powershell
$sec = ConvertTo-SecureString 'your-ssh-password' -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential('your-ssh-user', $sec)
$session = New-SSHSession -ComputerName 'your-server-ip' -Credential $cred -AcceptKey -ConnectionTimeout 20
Invoke-SSHCommand -SessionId $session.SessionId -Command "set -e; cd /home/your-ssh-user; rm -rf depotmovement depot_movement depotmovement-deploy.zip; mkdir -p depotmovement"
Set-SCPItem -ComputerName 'your-server-ip' -Credential $cred -AcceptKey -Path $zip -Destination '/home/your-ssh-user/'
Invoke-SSHCommand -SessionId $session.SessionId -Command "set -e; cd /home/your-ssh-user/depotmovement; unzip -q ../depotmovement-deploy.zip"
```

```powershell
$cmd = @'
set -e
cd /home/your-ssh-user/depotmovement
PORT=1254
if ss -ltn | awk '{print $4}' | grep -q ":$PORT$"; then
  for p in $(seq 1255 1300); do
    if ! ss -ltn | awk '{print $4}' | grep -q ":$p$"; then PORT=$p; break; fi
  done
fi
cat > docker-compose.override.yml <<EOF
services:
  redis:
    ports:
      - "${PORT}:6379"
EOF
echo "PORT=$PORT"
docker compose up --build -d redis worker beat
docker compose ps
'@
Invoke-SSHCommand -SessionId $session.SessionId -Command $cmd -TimeOut 300
```

```powershell
Invoke-SSHCommand -SessionId $session.SessionId -Command "set -e; cd /home/your-ssh-user/depotmovement; sleep 8; docker compose ps; docker compose logs --tail=40 worker beat" -TimeOut 120
Remove-SSHSession -SessionId $session.SessionId
```

## Dry Run Pipeline

```bash
cd /home/your-ssh-user/depotmovement
docker compose up -d redis worker beat
docker compose run --rm app depot --enqueue --dry-run
docker compose logs --tail=200 worker beat
```

## Live Pipeline

```bash
cd /home/your-ssh-user/depotmovement
docker compose up -d redis worker beat
docker compose run --rm app depot --enqueue --insert
docker compose logs --tail=200 worker beat
```

