-- =========================================================
-- 1. ORGANIZATIONS
-- =========================================================

CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    legal_name VARCHAR(255),

    email VARCHAR(255),
    phone VARCHAR(30),

    address_line1 VARCHAR(255),
    address_line2 VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(100),
    country VARCHAR(100),
    postal_code VARCHAR(20),

    timezone VARCHAR(100) DEFAULT 'Asia/Kolkata',

    status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- =========================================================
-- 2. USERS
-- =========================================================

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id UUID NOT NULL,

    user_code VARCHAR(50) NOT NULL,

    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100),

    email VARCHAR(255) NOT NULL,
    phone VARCHAR(30),

    password_hash TEXT NOT NULL,

    status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',

    last_login_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ,

    CONSTRAINT fk_users_organization
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE CASCADE,

    CONSTRAINT uq_users_org_email
        UNIQUE (organization_id, email),

    CONSTRAINT uq_users_org_code
        UNIQUE (organization_id, user_code)
);


-- =========================================================
-- 3. ROLES
-- =========================================================

CREATE TABLE roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id UUID,

    name VARCHAR(100) NOT NULL,
    code VARCHAR(50) NOT NULL,

    description TEXT,

    is_system_role BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_roles_organization
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE CASCADE
);


-- =========================================================
-- 4. PERMISSIONS
-- =========================================================

CREATE TABLE permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    module VARCHAR(100) NOT NULL,
    action VARCHAR(50) NOT NULL,

    code VARCHAR(150) NOT NULL UNIQUE,
    description TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- =========================================================
-- 5. USER ROLES
-- =========================================================

CREATE TABLE user_roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id UUID NOT NULL,
    role_id UUID NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_user_roles_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_user_roles_role
        FOREIGN KEY (role_id)
        REFERENCES roles(id)
        ON DELETE CASCADE,

    CONSTRAINT uq_user_role
        UNIQUE (user_id, role_id)
);


-- =========================================================
-- 6. ROLE PERMISSIONS
-- =========================================================

CREATE TABLE role_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    role_id UUID NOT NULL,
    permission_id UUID NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_role_permissions_role
        FOREIGN KEY (role_id)
        REFERENCES roles(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_role_permissions_permission
        FOREIGN KEY (permission_id)
        REFERENCES permissions(id)
        ON DELETE CASCADE,

    CONSTRAINT uq_role_permission
        UNIQUE (role_id, permission_id)
);


-- =========================================================
-- 7. STORES
-- =========================================================

CREATE TABLE stores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id UUID NOT NULL,

    store_code VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,

    address_line1 VARCHAR(255),
    address_line2 VARCHAR(255),

    city VARCHAR(100),
    state VARCHAR(100),
    country VARCHAR(100),
    postal_code VARCHAR(20),

    latitude DECIMAL(10,7),
    longitude DECIMAL(10,7),

    timezone VARCHAR(100) DEFAULT 'Asia/Kolkata',

    status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_stores_organization
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE CASCADE,

    CONSTRAINT uq_store_code_per_org
        UNIQUE (organization_id, store_code)
);


-- =========================================================
-- 8. ZONES
-- =========================================================

CREATE TABLE zones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id UUID NOT NULL,
    store_id UUID NOT NULL,

    zone_code VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,

    zone_type VARCHAR(50) NOT NULL,

    polygon JSONB,

    threshold_config JSONB,

    status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_zones_organization
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_zones_store
        FOREIGN KEY (store_id)
        REFERENCES stores(id)
        ON DELETE CASCADE,

    CONSTRAINT uq_zone_code_per_store
        UNIQUE (store_id, zone_code)
);


-- =========================================================
-- 9. CAMERAS
-- =========================================================

CREATE TABLE cameras (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id UUID NOT NULL,
    store_id UUID NOT NULL,
    zone_id UUID,

    camera_code VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,

    stream_reference TEXT,

    resolution VARCHAR(50),
    fps DECIMAL(10,2),

    health_status VARCHAR(30) DEFAULT 'OFFLINE',

    last_seen_at TIMESTAMPTZ,

    status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_cameras_organization
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_cameras_store
        FOREIGN KEY (store_id)
        REFERENCES stores(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_cameras_zone
        FOREIGN KEY (zone_id)
        REFERENCES zones(id)
        ON DELETE SET NULL,

    CONSTRAINT uq_camera_code_per_store
        UNIQUE (store_id, camera_code)
);


-- =========================================================
-- 10. EMPLOYEES
-- =========================================================

CREATE TABLE employees (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id UUID NOT NULL,
    store_id UUID NOT NULL,

    erp_employee_id VARCHAR(100),

    employee_code VARCHAR(100) NOT NULL,

    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100),

    phone VARCHAR(30),
    email VARCHAR(255),

    shift_start TIME,
    shift_end TIME,

    status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_employees_organization
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_employees_store
        FOREIGN KEY (store_id)
        REFERENCES stores(id)
        ON DELETE CASCADE,

    CONSTRAINT uq_employee_code_per_org
        UNIQUE (organization_id, employee_code),

    CONSTRAINT uq_erp_employee_per_org
        UNIQUE (organization_id, erp_employee_id)
);


-- =========================================================
-- 11. EMPLOYEE ZONE ASSIGNMENTS
-- =========================================================

CREATE TABLE employee_zone_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id UUID NOT NULL,

    employee_id UUID NOT NULL,
    zone_id UUID NOT NULL,

    assigned_from TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    assigned_to TIMESTAMPTZ,

    is_primary BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_employee_zone_org
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_employee_zone_employee
        FOREIGN KEY (employee_id)
        REFERENCES employees(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_employee_zone_zone
        FOREIGN KEY (zone_id)
        REFERENCES zones(id)
        ON DELETE CASCADE
);


-- =========================================================
-- 12. EMPLOYEE SESSIONS
-- =========================================================

CREATE TABLE employee_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id UUID NOT NULL,

    employee_id UUID NOT NULL,
    store_id UUID NOT NULL,

    session_start TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    session_end TIMESTAMPTZ,

    shift_start TIMESTAMPTZ,
    shift_end TIMESTAMPTZ,

    status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_employee_sessions_org
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_employee_sessions_employee
        FOREIGN KEY (employee_id)
        REFERENCES employees(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_employee_sessions_store
        FOREIGN KEY (store_id)
        REFERENCES stores(id)
        ON DELETE CASCADE
);


-- =========================================================
-- 13. BUSINESS RULES
-- =========================================================

CREATE TABLE business_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id UUID NOT NULL,
    store_id UUID,
    zone_id UUID,

    rule_code VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,

    rule_type VARCHAR(100) NOT NULL,
    event_type VARCHAR(100),

    condition_config JSONB,
    threshold_config JSONB,

    severity VARCHAR(20) DEFAULT 'MEDIUM',

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_rules_organization
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_rules_store
        FOREIGN KEY (store_id)
        REFERENCES stores(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_rules_zone
        FOREIGN KEY (zone_id)
        REFERENCES zones(id)
        ON DELETE CASCADE,

    CONSTRAINT uq_rule_code_per_org
        UNIQUE (organization_id, rule_code)
);


-- =========================================================
-- 14. CUSTOMER SESSIONS
-- =========================================================

CREATE TABLE customer_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id UUID NOT NULL,
    store_id UUID NOT NULL,

    session_code VARCHAR(100) NOT NULL,

    customer_tracking_id VARCHAR(150),

    current_zone_id UUID,

    assigned_employee_id UUID,

    start_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMPTZ,

    status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',

    response_time_seconds DECIMAL(12,2),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_customer_sessions_org
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_customer_sessions_store
        FOREIGN KEY (store_id)
        REFERENCES stores(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_customer_sessions_zone
        FOREIGN KEY (current_zone_id)
        REFERENCES zones(id)
        ON DELETE SET NULL,

    CONSTRAINT fk_customer_sessions_employee
        FOREIGN KEY (assigned_employee_id)
        REFERENCES employees(id)
        ON DELETE SET NULL,

    CONSTRAINT uq_customer_session_code
        UNIQUE (organization_id, session_code)
);


-- =========================================================
-- 15. POS INTEGRATIONS
-- =========================================================

CREATE TABLE pos_integrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id UUID NOT NULL,

    provider_name VARCHAR(100) NOT NULL,

    base_url TEXT,

    authentication_type VARCHAR(50),

    config JSONB,

    status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',

    last_sync_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_pos_integrations_org
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE CASCADE
);


-- =========================================================
-- 16. PRODUCTS
-- =========================================================

CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id UUID NOT NULL,

    external_product_id VARCHAR(150),

    sku VARCHAR(100) NOT NULL,

    name VARCHAR(255) NOT NULL,
    description TEXT,

    category VARCHAR(100),

    unit VARCHAR(30),

    status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_products_org
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE CASCADE,

    CONSTRAINT uq_product_sku_per_org
        UNIQUE (organization_id, sku)
);


-- =========================================================
-- 17. TRANSACTIONS
-- =========================================================

CREATE TABLE transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id UUID NOT NULL,
    store_id UUID NOT NULL,

    customer_session_id UUID,

    transaction_code VARCHAR(100) NOT NULL,

    external_transaction_id VARCHAR(150),

    invoice_number VARCHAR(150),

    pos_reference VARCHAR(150),

    subtotal_amount NUMERIC(14,2) DEFAULT 0,
    discount_amount NUMERIC(14,2) DEFAULT 0,
    tax_amount NUMERIC(14,2) DEFAULT 0,
    total_amount NUMERIC(14,2) NOT NULL DEFAULT 0,

    currency VARCHAR(10) DEFAULT 'INR',

    status VARCHAR(50) NOT NULL DEFAULT 'OPEN',

    transaction_timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

    source_system VARCHAR(100),

    raw_payload JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_transactions_org
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_transactions_store
        FOREIGN KEY (store_id)
        REFERENCES stores(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_transactions_customer_session
        FOREIGN KEY (customer_session_id)
        REFERENCES customer_sessions(id)
        ON DELETE SET NULL,

    CONSTRAINT uq_transaction_code_per_org
        UNIQUE (organization_id, transaction_code)
);


-- =========================================================
-- 18. TRANSACTION ITEMS
-- =========================================================

CREATE TABLE transaction_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id UUID NOT NULL,

    transaction_id UUID NOT NULL,

    product_id UUID,

    sku VARCHAR(100),

    product_name VARCHAR(255) NOT NULL,

    quantity NUMERIC(14,3) NOT NULL DEFAULT 1,

    unit_price NUMERIC(14,2) NOT NULL DEFAULT 0,

    discount_amount NUMERIC(14,2) DEFAULT 0,

    total_price NUMERIC(14,2) NOT NULL DEFAULT 0,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_transaction_items_org
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_transaction_items_transaction
        FOREIGN KEY (transaction_id)
        REFERENCES transactions(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_transaction_items_product
        FOREIGN KEY (product_id)
        REFERENCES products(id)
        ON DELETE SET NULL
);


-- =========================================================
-- 19. PAYMENTS
-- =========================================================

CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id UUID NOT NULL,

    transaction_id UUID NOT NULL,

    external_payment_id VARCHAR(150),

    payment_reference VARCHAR(150),

    payment_mode VARCHAR(50) NOT NULL,

    amount NUMERIC(14,2) NOT NULL,

    currency VARCHAR(10) DEFAULT 'INR',

    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',

    payment_timestamp TIMESTAMPTZ,

    source_system VARCHAR(100),

    raw_payload JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_payments_org
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_payments_transaction
        FOREIGN KEY (transaction_id)
        REFERENCES transactions(id)
        ON DELETE CASCADE
);


-- =========================================================
-- 20. AI EVENTS
-- =========================================================

CREATE TABLE ai_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id UUID NOT NULL,

    event_id VARCHAR(100) NOT NULL,

    event_type VARCHAR(100) NOT NULL,

    store_id UUID NOT NULL,
    camera_id UUID NOT NULL,
    zone_id UUID,

    subject_id VARCHAR(150),

    employee_id UUID,

    customer_session_id UUID,
    employee_session_id UUID,

    event_timestamp TIMESTAMPTZ NOT NULL,

    confidence DECIMAL(5,4),

    duration_seconds DECIMAL(12,2),

    severity VARCHAR(20),

    correlation_id VARCHAR(150),

    model_name VARCHAR(100),
    model_version VARCHAR(100),

    raw_payload JSONB,

    normalized_payload JSONB,

    processing_status VARCHAR(30) NOT NULL DEFAULT 'PENDING',

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_ai_events_org
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_ai_events_store
        FOREIGN KEY (store_id)
        REFERENCES stores(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_ai_events_camera
        FOREIGN KEY (camera_id)
        REFERENCES cameras(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_ai_events_zone
        FOREIGN KEY (zone_id)
        REFERENCES zones(id)
        ON DELETE SET NULL,

    CONSTRAINT fk_ai_events_employee
        FOREIGN KEY (employee_id)
        REFERENCES employees(id)
        ON DELETE SET NULL,

    CONSTRAINT fk_ai_events_customer_session
        FOREIGN KEY (customer_session_id)
        REFERENCES customer_sessions(id)
        ON DELETE SET NULL,

    CONSTRAINT fk_ai_events_employee_session
        FOREIGN KEY (employee_session_id)
        REFERENCES employee_sessions(id)
        ON DELETE SET NULL,

    CONSTRAINT uq_ai_event_per_org
        UNIQUE (organization_id, event_id)
);


-- =========================================================
-- 21. TRANSACTION STATE HISTORY
-- =========================================================

CREATE TABLE transaction_state_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id UUID NOT NULL,

    transaction_id UUID NOT NULL,

    previous_state VARCHAR(50),
    new_state VARCHAR(50) NOT NULL,

    event_id UUID,

    source VARCHAR(50),

    metadata JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_transaction_history_org
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_transaction_history_transaction
        FOREIGN KEY (transaction_id)
        REFERENCES transactions(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_transaction_history_event
        FOREIGN KEY (event_id)
        REFERENCES ai_events(id)
        ON DELETE SET NULL
);


-- =========================================================
-- 22. RECONCILIATIONS
-- =========================================================

CREATE TABLE reconciliations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id UUID NOT NULL,

    transaction_id UUID NOT NULL,

    reconciliation_type VARCHAR(100) NOT NULL,

    expected_value JSONB,

    observed_value JSONB,

    variance JSONB,

    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',

    exception_reason TEXT,

    resolved_by UUID,
    resolved_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_reconciliations_org
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_reconciliations_transaction
        FOREIGN KEY (transaction_id)
        REFERENCES transactions(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_reconciliations_resolved_by
        FOREIGN KEY (resolved_by)
        REFERENCES users(id)
        ON DELETE SET NULL
);


-- =========================================================
-- 23. ALERTS
-- =========================================================

CREATE TABLE alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id UUID NOT NULL,
    store_id UUID NOT NULL,

    alert_code VARCHAR(100) NOT NULL,

    event_id UUID,

    customer_session_id UUID,
    employee_session_id UUID,
    transaction_id UUID,

    business_rule_id UUID,

    severity VARCHAR(20) NOT NULL DEFAULT 'MEDIUM',

    title VARCHAR(255) NOT NULL,

    description TEXT,

    status VARCHAR(30) NOT NULL DEFAULT 'OPEN',

    assigned_to UUID,

    acknowledged_by UUID,
    acknowledged_at TIMESTAMPTZ,

    resolved_by UUID,
    resolved_at TIMESTAMPTZ,

    resolution_notes TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_alerts_org
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_alerts_store
        FOREIGN KEY (store_id)
        REFERENCES stores(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_alerts_event
        FOREIGN KEY (event_id)
        REFERENCES ai_events(id)
        ON DELETE SET NULL,

    CONSTRAINT fk_alerts_customer_session
        FOREIGN KEY (customer_session_id)
        REFERENCES customer_sessions(id)
        ON DELETE SET NULL,

    CONSTRAINT fk_alerts_employee_session
        FOREIGN KEY (employee_session_id)
        REFERENCES employee_sessions(id)
        ON DELETE SET NULL,

    CONSTRAINT fk_alerts_transaction
        FOREIGN KEY (transaction_id)
        REFERENCES transactions(id)
        ON DELETE SET NULL,

    CONSTRAINT fk_alerts_business_rule
        FOREIGN KEY (business_rule_id)
        REFERENCES business_rules(id)
        ON DELETE SET NULL,

    CONSTRAINT fk_alerts_assigned_to
        FOREIGN KEY (assigned_to)
        REFERENCES users(id)
        ON DELETE SET NULL,

    CONSTRAINT fk_alerts_acknowledged_by
        FOREIGN KEY (acknowledged_by)
        REFERENCES users(id)
        ON DELETE SET NULL,

    CONSTRAINT fk_alerts_resolved_by
        FOREIGN KEY (resolved_by)
        REFERENCES users(id)
        ON DELETE SET NULL
);


-- =========================================================
-- 24. ALERT STATUS HISTORY
-- =========================================================

CREATE TABLE alert_status_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id UUID NOT NULL,

    alert_id UUID NOT NULL,

    previous_status VARCHAR(30),
    new_status VARCHAR(30) NOT NULL,

    changed_by UUID,

    remarks TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_alert_history_org
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_alert_history_alert
        FOREIGN KEY (alert_id)
        REFERENCES alerts(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_alert_history_user
        FOREIGN KEY (changed_by)
        REFERENCES users(id)
        ON DELETE SET NULL
);


-- =========================================================
-- 25. EXCEPTIONS
-- =========================================================

CREATE TABLE exceptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id UUID NOT NULL,

    exception_code VARCHAR(100),

    exception_type VARCHAR(100) NOT NULL,

    severity VARCHAR(20) NOT NULL DEFAULT 'MEDIUM',

    event_id UUID,
    transaction_id UUID,

    customer_session_id UUID,
    employee_session_id UUID,

    description TEXT,

    status VARCHAR(30) NOT NULL DEFAULT 'OPEN',

    assigned_to UUID,

    resolved_by UUID,
    resolved_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_exceptions_org
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_exceptions_event
        FOREIGN KEY (event_id)
        REFERENCES ai_events(id)
        ON DELETE SET NULL,

    CONSTRAINT fk_exceptions_transaction
        FOREIGN KEY (transaction_id)
        REFERENCES transactions(id)
        ON DELETE SET NULL,

    CONSTRAINT fk_exceptions_customer_session
        FOREIGN KEY (customer_session_id)
        REFERENCES customer_sessions(id)
        ON DELETE SET NULL,

    CONSTRAINT fk_exceptions_employee_session
        FOREIGN KEY (employee_session_id)
        REFERENCES employee_sessions(id)
        ON DELETE SET NULL,

    CONSTRAINT fk_exceptions_assigned_to
        FOREIGN KEY (assigned_to)
        REFERENCES users(id)
        ON DELETE SET NULL,

    CONSTRAINT fk_exceptions_resolved_by
        FOREIGN KEY (resolved_by)
        REFERENCES users(id)
        ON DELETE SET NULL
);


-- =========================================================
-- 26. EVIDENCE
-- =========================================================

CREATE TABLE evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id UUID NOT NULL,

    event_id UUID NOT NULL,

    alert_id UUID,

    evidence_type VARCHAR(50) NOT NULL,

    storage_provider VARCHAR(50),

    storage_reference TEXT NOT NULL,

    file_name VARCHAR(255),

    content_type VARCHAR(100),

    file_size BIGINT,

    start_timestamp TIMESTAMPTZ,
    end_timestamp TIMESTAMPTZ,

    retention_until TIMESTAMPTZ,

    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',

    failure_reason TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_evidence_org
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_evidence_event
        FOREIGN KEY (event_id)
        REFERENCES ai_events(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_evidence_alert
        FOREIGN KEY (alert_id)
        REFERENCES alerts(id)
        ON DELETE SET NULL
);


-- =========================================================
-- 27. EVENT EVIDENCE
-- =========================================================

CREATE TABLE event_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    event_id UUID NOT NULL,
    evidence_id UUID NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_event_evidence_event
        FOREIGN KEY (event_id)
        REFERENCES ai_events(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_event_evidence_evidence
        FOREIGN KEY (evidence_id)
        REFERENCES evidence(id)
        ON DELETE CASCADE,

    CONSTRAINT uq_event_evidence
        UNIQUE (event_id, evidence_id)
);


-- =========================================================
-- 28. EVIDENCE ACCESS LOGS
-- =========================================================

CREATE TABLE evidence_access_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id UUID NOT NULL,

    evidence_id UUID NOT NULL,

    user_id UUID,

    access_type VARCHAR(50) NOT NULL,

    ip_address INET,

    accessed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_evidence_access_org
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_evidence_access_evidence
        FOREIGN KEY (evidence_id)
        REFERENCES evidence(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_evidence_access_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE SET NULL
);


-- =========================================================
-- 29. AUDIT LOGS
-- =========================================================

CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id UUID,

    user_id UUID,

    action VARCHAR(100) NOT NULL,

    entity_type VARCHAR(100),

    entity_id VARCHAR(100),

    old_values JSONB,

    new_values JSONB,

    metadata JSONB,

    ip_address INET,

    user_agent TEXT,

    request_id VARCHAR(100),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_audit_org
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE SET NULL,

    CONSTRAINT fk_audit_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE SET NULL
);


-- =========================================================
-- 30. IDEMPOTENCY KEYS
-- =========================================================

CREATE TABLE idempotency_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id UUID NOT NULL,

    idempotency_key VARCHAR(255) NOT NULL,

    source VARCHAR(100),

    resource_type VARCHAR(100),

    request_hash VARCHAR(255),

    response_data JSONB,

    status VARCHAR(30) NOT NULL DEFAULT 'PROCESSING',

    expires_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_idempotency_org
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE CASCADE,

    CONSTRAINT uq_idempotency_key
        UNIQUE (organization_id, idempotency_key)
);


-- =========================================================
-- 31. INTEGRATION LOGS
-- =========================================================

CREATE TABLE integration_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id UUID NOT NULL,

    integration_type VARCHAR(100) NOT NULL,

    operation VARCHAR(100),

    request_payload JSONB,

    response_payload JSONB,

    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',

    error_message TEXT,

    retry_count INTEGER NOT NULL DEFAULT 0,

    next_retry_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_integration_logs_org
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE CASCADE
);


-- =========================================================
-- 32. RETENTION POLICIES
-- =========================================================

CREATE TABLE retention_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    organization_id UUID,

    resource_type VARCHAR(100) NOT NULL,

    retention_days INTEGER NOT NULL,

    action VARCHAR(50) NOT NULL DEFAULT 'DELETE',

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_retention_org
        FOREIGN KEY (organization_id)
        REFERENCES organizations(id)
        ON DELETE CASCADE
);


-- =========================================================
-- INDEXES
-- =========================================================

CREATE INDEX idx_users_organization ON users(organization_id);
CREATE INDEX idx_stores_organization ON stores(organization_id);
CREATE INDEX idx_zones_store ON zones(store_id);
CREATE INDEX idx_cameras_store ON cameras(store_id);
CREATE INDEX idx_employees_store ON employees(store_id);
CREATE INDEX idx_customer_sessions_store ON customer_sessions(store_id);
CREATE INDEX idx_customer_sessions_tracking ON customer_sessions(customer_tracking_id);
CREATE INDEX idx_employee_sessions_employee ON employee_sessions(employee_id);
CREATE INDEX idx_ai_events_org ON ai_events(organization_id);
CREATE INDEX idx_ai_events_store ON ai_events(store_id);
CREATE INDEX idx_ai_events_camera ON ai_events(camera_id);
CREATE INDEX idx_ai_events_zone ON ai_events(zone_id);
CREATE INDEX idx_ai_events_event_type ON ai_events(event_type);
CREATE INDEX idx_ai_events_timestamp ON ai_events(event_timestamp);
CREATE INDEX idx_ai_events_correlation ON ai_events(correlation_id);
CREATE INDEX idx_transactions_org ON transactions(organization_id);
CREATE INDEX idx_transactions_store ON transactions(store_id);
CREATE INDEX idx_transactions_timestamp ON transactions(transaction_timestamp);
CREATE INDEX idx_transaction_items_transaction ON transaction_items(transaction_id);
CREATE INDEX idx_payments_transaction ON payments(transaction_id);
CREATE INDEX idx_alerts_org ON alerts(organization_id);
CREATE INDEX idx_alerts_store ON alerts(store_id);
CREATE INDEX idx_alerts_status ON alerts(status);
CREATE INDEX idx_alerts_severity ON alerts(severity);
CREATE INDEX idx_exceptions_org ON exceptions(organization_id);
CREATE INDEX idx_exceptions_status ON exceptions(status);
CREATE INDEX idx_evidence_event ON evidence(event_id);
CREATE INDEX idx_audit_logs_org ON audit_logs(organization_id);
CREATE INDEX idx_audit_logs_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX idx_integration_logs_status ON integration_logs(status);