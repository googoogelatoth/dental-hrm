-- ===================================================================
-- SQL Script: Clear Old Encrypted Data (Before Using New Key)
-- ===================================================================
-- 
-- Purpose: Remove old encrypted data that was encrypted with the old key
--          This prevents "InvalidToken" errors after changing ENCRYPTION_KEY
--
-- WARNING: This will DELETE the following data:
--   - phone_number
--   - id_card_number  
--   - bank_account_number
--
-- Employees will need to re-enter this information after the update
-- ===================================================================

BEGIN;

-- 1. Check how many records will be affected
SELECT 
    COUNT(*) AS total_employees,
    COUNT(*) FILTER (WHERE phone_number IS NOT NULL) AS has_phone,
    COUNT(*) FILTER (WHERE id_card_number IS NOT NULL) AS has_id_card,
    COUNT(*) FILTER (WHERE bank_account_number IS NOT NULL) AS has_bank_account
FROM employees;

-- 2. Preview which employees will be affected (first 10)
SELECT id, employee_code, first_name, last_name,
       CASE WHEN phone_number IS NOT NULL THEN 'YES' ELSE 'NO' END AS has_encrypted_data
FROM employees
WHERE phone_number IS NOT NULL 
   OR id_card_number IS NOT NULL 
   OR bank_account_number IS NOT NULL
LIMIT 10;

-- 3. Clear the encrypted fields
UPDATE employees 
SET 
    phone_number = NULL,
    id_card_number = NULL,
    bank_account_number = NULL
WHERE phone_number IS NOT NULL 
   OR id_card_number IS NOT NULL 
   OR bank_account_number IS NOT NULL;

-- 4. Verify the update
SELECT 
    COUNT(*) AS total_employees,
    COUNT(*) FILTER (WHERE phone_number IS NOT NULL) AS remaining_phone,
    COUNT(*) FILTER (WHERE id_card_number IS NOT NULL) AS remaining_id_card,
    COUNT(*) FILTER (WHERE bank_account_number IS NOT NULL) AS remaining_bank_account
FROM employees;

COMMIT;

-- ===================================================================
-- After running this script:
-- 1. Deploy the new ENCRYPTION_KEY to Cloud Run
-- 2. Restart the service
-- 3. Test by visiting /my-profile (should NOT see "InvalidToken")
-- 4. Ask employees/admins to re-enter their personal data
-- ===================================================================
