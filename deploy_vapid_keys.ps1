# ===================================================================
# PowerShell Script: Deploy VAPID Keys to Cloud Run
# ===================================================================
#
# Usage: 
#   1. Generate VAPID keys: python generate_vapid_keys.py
#   2. Copy keys from NEW_VAPID_KEYS.txt
#   3. Edit this script and paste the keys below
#   4. Run: .\deploy_vapid_keys.ps1
#
# ===================================================================

# 🔔 PASTE YOUR VAPID KEYS HERE (from NEW_VAPID_KEYS.txt)
$VAPID_PUBLIC_KEY = "YOUR_PUBLIC_KEY_HERE"
$VAPID_PRIVATE_KEY = "YOUR_PRIVATE_KEY_HERE"
$VAPID_CLAIMS_SUB = "mailto:admin@clinic.com"

# Configuration
$SERVICE_NAME = "mini-hrm"
$REGION = "asia-southeast1"

Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "🔔 Deploying VAPID Keys to Cloud Run" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host ""

# Validation
if ($VAPID_PUBLIC_KEY -eq "YOUR_PUBLIC_KEY_HERE") {
    Write-Host "❌ ERROR: Please edit this script and paste your VAPID keys!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Steps:" -ForegroundColor Yellow
    Write-Host "  1. Run: python generate_vapid_keys.py" -ForegroundColor Yellow
    Write-Host "  2. Copy keys from NEW_VAPID_KEYS.txt" -ForegroundColor Yellow
    Write-Host "  3. Edit this script (lines 15-17) and paste the keys" -ForegroundColor Yellow
    Write-Host "  4. Run this script again" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

Write-Host "Service: $SERVICE_NAME" -ForegroundColor Green
Write-Host "Region: $REGION" -ForegroundColor Green
Write-Host "Public Key Length: $($VAPID_PUBLIC_KEY.Length) characters" -ForegroundColor Green
Write-Host "Private Key Length: $($VAPID_PRIVATE_KEY.Length) characters" -ForegroundColor Green
Write-Host ""

# Confirm before proceeding
$confirm = Read-Host "Deploy VAPID keys? (yes/no)"
if ($confirm -ne "yes") {
    Write-Host "❌ Deployment cancelled" -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "⏳ Updating Cloud Run service with VAPID keys..." -ForegroundColor Yellow

# Update Cloud Run service with all keys at once
gcloud run services update $SERVICE_NAME `
    --region $REGION `
    --set-env-vars "VAPID_PUBLIC_KEY=$VAPID_PUBLIC_KEY,VAPID_PRIVATE_KEY=$VAPID_PRIVATE_KEY,VAPID_CLAIMS_SUB=$VAPID_CLAIMS_SUB"

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✅ Deployment successful!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next Steps:" -ForegroundColor Cyan
    Write-Host "  1. Wait 1-2 minutes for deployment to complete" -ForegroundColor White
    Write-Host "  2. Go to: /my-profile" -ForegroundColor White
    Write-Host "  3. Click 'Enable Notifications on this device'" -ForegroundColor White
    Write-Host "  4. Check browser console (F12) for debug logs" -ForegroundColor White
    Write-Host "  5. Should see: '✅ Successfully converted VAPID key'" -ForegroundColor White
    Write-Host ""
    Write-Host "Check Cloud Run Logs at:" -ForegroundColor Cyan
    Write-Host "  https://console.cloud.google.com/run/detail/$REGION/$SERVICE_NAME/logs" -ForegroundColor White
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "❌ Deployment failed!" -ForegroundColor Red
    Write-Host "Check the error message above and try again" -ForegroundColor Red
    Write-Host ""
    exit 1
}
