# Immediate Action Required: Set VAPID Claims Email

## What Changed
Fixed the notification system that was failing with "Missing 'sub' from claims" error. The application now requires a valid admin email to be configured for Web Push notifications.

## Quick Fix (5 minutes)

### For Google Cloud Run:
```bash
# Replace admin@yourdomain.com with your actual admin email
gcloud run deploy mini-hrm \
  --update-env-vars VAPID_CLAIMS_SUB=mailto:admin@yourdomain.com \
  --region asia-southeast1 \
  --project YOUR_PROJECT_ID
```

### Or manually via Cloud Console:
1. Go to Cloud Run > mini-hrm > Edit & Deploy New Revision
2. Add environment variable:
   - **Name**: `VAPID_CLAIMS_SUB`
   - **Value**: `mailto:admin@yourdomain.com`
3. Click Deploy

## What This Fixes
✅ Admin can now approve/reject attendance requests without 500 errors
✅ Push notifications work when employees submit requests
✅ Notifications work when admin approves/rejects requests
✅ Both employee and admin receive proper notifications

## Files Modified
- `app/config.py` - Better VAPID claims handling
- `app/main.py` - Improved error handling in notifications
- `.env.example` - Added VAPID_CLAIMS_SUB documentation

## Testing After Fix
1. Employee submits manual attendance request
2. Admin should receive a push notification
3. Admin approves the request
4. Employee should receive a notification
5. No 500 errors in logs
