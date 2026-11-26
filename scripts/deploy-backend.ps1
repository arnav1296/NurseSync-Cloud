# Build the API image, push it to Amazon ECR, and roll the Auto Scaling Group onto it.
# Run from the repo root after `terraform apply`. Needs Docker Desktop and the AWS CLI.
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent

$region = terraform -chdir="$root\infra" output -raw region
$repo   = terraform -chdir="$root\infra" output -raw ecr_repository_url
$asg    = terraform -chdir="$root\infra" output -raw asg_name
$registry = $repo.Split("/")[0]

Write-Host "Logging in to $registry"
# piped through cmd: Windows PowerShell 5.1 re-encodes native-to-native pipes, which
# corrupts the token and makes ECR answer 400 Bad Request
cmd /c "aws ecr get-login-password --region $region | docker login --username AWS --password-stdin $registry"
if ($LASTEXITCODE -ne 0) { throw "ECR login failed" }

Write-Host "Building and pushing $repo`:latest"
docker build --platform linux/amd64 -t "$repo`:latest" "$root\backend"
if ($LASTEXITCODE -ne 0) { throw "docker build failed" }
docker push "$repo`:latest"
if ($LASTEXITCODE -ne 0) { throw "docker push failed" }

Write-Host "Replacing the running instances (takes ~5 minutes)"
aws autoscaling start-instance-refresh --region $region --auto-scaling-group-name $asg | Out-Null
Write-Host "Done. Watch it in EC2 > Auto Scaling Groups > $asg > Instance refresh."
