-- Add missing column
ALTER TABLE users ADD COLUMN IF NOT EXISTS store_id UUID REFERENCES stores(id) ON DELETE SET NULL;

-- Ensure Organization exists
INSERT INTO organizations (id, organization_code, name, legal_name, email, country, timezone, status)
VALUES (
    'a0000000-0000-0000-0000-000000000001',
    'BACHRAJ',
    'Bachraj Smart Retail',
    'Bachraj Smart Retail',
    'admin@bachraj.com',
    'India',
    'Asia/Kolkata',
    'ACTIVE'
)
ON CONFLICT (organization_code) DO NOTHING;

-- Ensure SUPER_ADMIN role exists
INSERT INTO roles (id, organization_id, name, code, description, is_system_role)
SELECT
    'b0000000-0000-0000-0000-000000000001',
    id,
    'Super Admin',
    'SUPER_ADMIN',
    'System Super Administrator',
    true
FROM organizations
WHERE organization_code = 'BACHRAJ'
ON CONFLICT DO NOTHING;

-- Ensure Super Admin user exists
INSERT INTO users (id, organization_id, user_code, first_name, last_name, email, password_hash, status)
SELECT
    'c0000000-0000-0000-0000-000000000001',
    id,
    'SUPERADMIN001',
    'Super',
    'Admin',
    'superadmin@bachraj.com',
    '$2b$12$5ORUkQGe.A9vp8H5ZKLfY.p8/e60Cc1qkQctFXGJqmOKbUxUj.S0O',
    'ACTIVE'
FROM organizations
WHERE organization_code = 'BACHRAJ'
ON CONFLICT DO NOTHING;

-- Connect User to Role
INSERT INTO user_roles (id, user_id, role_id)
SELECT
    'd0000000-0000-0000-0000-000000000001',
    u.id,
    r.id
FROM users u, roles r
WHERE u.email = 'superadmin@bachraj.com' AND r.code = 'SUPER_ADMIN'
ON CONFLICT DO NOTHING;
