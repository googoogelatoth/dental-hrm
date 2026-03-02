# 🔔 VAPID Key Troubleshooting Guide

## ❌ Error: "The provided applicationServerKey is not valid"

This error occurs when the VAPID public key is:
- Empty or not configured
- Malformed or incorrectly formatted
- Not properly base64-encoded
- The wrong length

---

## ✅ Quick Diagnostics

### Step 1: Check Browser Console (F12)

When you click "Enable Notifications", open the browser developer tools and look for these logs:

#### ✅ Good Signs:
```
Step 1 - Cleaned string length: 136
Step 2 - After padding length: 136
Step 3 - Standard base64 length: 136
Step 4 - Raw data length: 65
✅ Successfully converted VAPID key to Uint8Array, length: 65
✅ applicationServerKey prepared, length: 65
✅ Push subscription successful
```

#### ❌ Bad Signs:
```
Step 1 - Cleaned string length: 0          ← VAPID key is empty!
Step 4 - Raw data length: 0                ← Key conversion failed
Invalid VAPID key format: ...               ← Decoding error
```

---

## 🔧 Verification Steps

### 1. Check Environment Variables

```bash
# On Windows (PowerShell)
$env:VAPID_PUBLIC_KEY
$env:VAPID_PRIVATE_KEY

# Should output long string like:
# BC... (136+ characters for public key)
# ... (88+ characters for private key)
```

### 2. Check if .env File is Loaded

```bash
# If using .env file
cat .env | grep VAPID

# Output should show:
# VAPID_PUBLIC_KEY=BCx...xxx
# VAPID_PRIVATE_KEY=xGz...yyy
```

### 3. Validate Key Format

VAPID keys should follow this pattern:
- **Public Key:** ~136 characters (base64url encoded)
- **Private Key:** ~88 characters (base64url encoded)

Example lengths:
```
VAPID_PUBLIC_KEY=BC... (should be 130-140 chars)
VAPID_PRIVATE_KEY=xG...= (should be 85-95 chars)
```

### 4. Check Server Logs on Startup

When you restart the app, check for messages like:

```
✅ VAPID_PUBLIC_KEY loaded: 136 characters
✅ VAPID_PRIVATE_KEY loaded: 87 characters
```

If you see warnings:
```
⚠️ VAPID_PUBLIC_KEY may be invalid: 50 chars (expected ~136+)
⚠️ VAPID_PRIVATE_KEY may be invalid: 45 chars (expected ~88+)
```

This means the keys are too short - they may be truncated or incorrect.

---

## 🛠️ How to Generate/Regenerate VAPID Keys

If your keys are invalid, generate new ones:

### Step 1: Install web-push CLI
```bash
npm install -g web-push
# or if you prefer local install:
npm install --save-dev web-push
```

### Step 2: Generate VAPID Keys
```bash
npx web-push generate-vapid-keys
```

Output will look like:
```
Public Key: BCx_SxWWVAZNg2Ky2A_KBzHNaLKtVNQ_WbkHvgTp...
Private Key: xGz8Ky2UDzO99Sx9VBzJqKpLmN3OzH4IqRsT...
```

### Step 3: Add to .env File
```env
VAPID_PUBLIC_KEY=BCx_SxWWVAZNg2Ky2A_KBzHNaLKtVNQ_WbkHvgTp...
VAPID_PRIVATE_KEY=xGz8Ky2UDzO99Sx9VBzJqKpLmN3OzH4IqRsT...
VAPID_CLAIMS_SUB=mailto:admin@clinic.com
```

### Step 4: Restart Application
```bash
# Kill the running app (Ctrl+C)
# Clear Python cache
rm -r __pycache__ app/__pycache__

# Start fresh
uvicorn app.main:app --reload
```

---

## 🧪 Testing After Fix

### Test 1: Check Server Logs
After restart, look for confirmation messages:
```
✅ VAPID_PUBLIC_KEY loaded: 136 characters
✅ VAPID_PRIVATE_KEY loaded: 87 characters
```

### Test 2: Check Browser Console
Open F12 while clicking "Enable Notifications":
```
Step 1 - Cleaned string length: 136
Step 2 - After padding length: 136
Step 3 - Standard base64 length: 136
Step 4 - Raw data length: 65
✅ Successfully converted VAPID key to Uint8Array, length: 65
```

### Test 3: Full Notification Test
1. Click "Enable Notifications"
2. Grant browser permission
3. Should see ✅ success message
4. Check Activity Logs to verify subscription was saved

---

## 📝 Common Issues & Solutions

### Issue 1: Keys are empty
**Symptoms:** No VAPID keys in console logs

**Solution:**
```bash
# Check .env file exists
ls -la .env

# Check env vars are accessible
echo $VAPID_PUBLIC_KEY

# If empty, add them to .env
```

### Issue 2: Keys are too short
**Symptoms:**
```
⚠️ VAPID_PUBLIC_KEY may be invalid: 50 chars (expected ~136+)
```

**Solution:**
- Keys may be truncated during copy/paste
- Regenerate and copy carefully
- Check there are no line breaks in .env

### Issue 3: Invalid base64 format
**Symptoms:**
```
❌ ERROR: Failed to convert VAPID key
  Message: String contains an invalid character
```

**Solution:**
- Ensure no extra quotes in .env: `VAPID_PUBLIC_KEY=BC...` (not `"BC..."`)
- Ensure no line breaks within the key
- Regenerate keys with web-push CLI

### Issue 4: Old service workers interfering
**Symptoms:**
- Errors still occur after fixing key
- Registration keeps failing

**Solution:**
```javascript
// In browser console:
navigator.serviceWorker.getRegistrations().then(regs => {
  regs.forEach(reg => reg.unregister());
});

// Then refresh the page and try again
```

---

## 📊 Debug Checklist

- [ ] Server logs show VAPID keys are loaded (length check)
- [ ] .env file contains valid VAPID keys (136+ and 88+ chars)
- [ ] Browser console shows Step 1-4 without errors
- [ ] Raw data length shows 65 bytes (correct for EC P-256)
- [ ] No quotes around keys in .env
- [ ] No line breaks in keys
- [ ] App was restarted after changing .env
- [ ] Service workers are cleaned up (unregistered)
- [ ] Browser cache is cleared (Ctrl+Shift+Delete)

---

## 🔗 Reference Links

- [Web Push Protocol Spec](https://datatracker.ietf.org/doc/html/rfc8030)
- [VAPID Spec (RFC 8292)](https://datatracker.ietf.org/doc/html/rfc8292)
- [web-push npm package](https://www.npmjs.com/package/web-push)
- [MDN: Push API](https://developer.mozilla.org/en-US/docs/Web/API/Push_API)
- [MDN: PushManager.subscribe()](https://developer.mozilla.org/en-US/docs/Web/API/PushManager/subscribe)

---

## 📞 Still Having Issues?

1. **Collect Debug Info:**
   - Server logs (copy full startup output)
   - Browser console logs (F12 > Console tab)
   - .env file (without actual keys, just show format)
   - VAPID key lengths

2. **Check These Files:**
   - [config.py](app/config.py) - VAPID key loading
   - [main.py](app/main.py) - startup validation
   - [employee_detail_content.html](app/templates/employee_detail_content.html) - frontend conversion
   - [dashboard.html](app/templates/dashboard.html) - dashboard notifications

3. **Run Diagnostic Script:**
   ```bash
   python -c "
   import os
   pub = os.getenv('VAPID_PUBLIC_KEY', '')
   priv = os.getenv('VAPID_PRIVATE_KEY', '')
   print(f'Public key: {len(pub)} chars')
   print(f'Private key: {len(priv)} chars')
   print(f'First 10 chars (pub): {pub[:10]}')
   print(f'First 10 chars (priv): {priv[:10]}')
   "
   ```

---

**Last Updated:** March 2, 2026  
**Status:** Diagnostic tools added for VAPID key troubleshooting
