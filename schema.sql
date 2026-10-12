-- ==============================================================================
-- SMART CAMPUS 360 - DATABASE SCHEMA (MySQL 8.0+)
-- Institutional Target: Government Engineering College, Mosalehosahalli (Hassan)
-- Unified Database for Navigation, Lost & Found, and Smart Canteen Management
-- ==============================================================================

CREATE DATABASE IF NOT EXISTS smart_campus_360
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE smart_campus_360;

-- ------------------------------------------------------------------------------
-- 1. USERS & ROLE-BASED ACCESS CONTROL (RBAC)
-- Roles: main_admin, canteen_admin, teacher, student, visitor
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('main_admin', 'canteen_admin', 'teacher', 'student', 'visitor') NOT NULL DEFAULT 'student',
    department VARCHAR(100) NULL COMMENT 'e.g. CSE, ECE, ME, Civil, Basic Science, Admin',
    phone VARCHAR(20) NULL,
    usn_or_emp_id VARCHAR(50) NULL COMMENT 'University USN for students, Employee ID for teachers/staff',
    designation VARCHAR(100) NULL COMMENT 'e.g. Professor, Assistant Professor, HOD',
    semester VARCHAR(20) NULL COMMENT 'For students: e.g. 1st Sem, 3rd Sem, 5th Sem, 7th Sem',
    purpose_of_visit VARCHAR(150) NULL COMMENT 'For visitors: e.g. Campus Tour, Parent Meeting, Admission Enquiry',
    is_verified BOOLEAN NOT NULL DEFAULT TRUE COMMENT 'Teachers require Main Admin verification for canteen priority',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    reset_token VARCHAR(100) NULL,
    reset_token_expiry DATETIME NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_role (role),
    INDEX idx_user_email (email),
    INDEX idx_reset_token (reset_token)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ------------------------------------------------------------------------------
-- 2. MODULE 1: SMART CAMPUS NAVIGATION TABLES
-- Nodes, Waypoints, POIs, and Route Graph (A* / Dijkstra)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS navigation_nodes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    node_code VARCHAR(50) NOT NULL UNIQUE COMMENT 'Unique identifier e.g. NODE_MAIN_GATE',
    name VARCHAR(150) NOT NULL COMMENT 'Display name of the location',
    building VARCHAR(100) NOT NULL COMMENT 'Building / Block name',
    floor VARCHAR(50) NOT NULL DEFAULT 'Ground Floor' COMMENT 'Ground Floor, 1st Floor, Campus Grounds, etc.',
    category ENUM('Classroom', 'Laboratory', 'HOD Room', 'Office', 'Library', 'Canteen', 'Restroom', 'Gate', 'Sports Ground', 'Auditorium', 'Corridor') NOT NULL DEFAULT 'Classroom',
    description TEXT NULL,
    x_coord INT NOT NULL DEFAULT 0 COMMENT 'X coordinate on 2D floorplan/canvas',
    y_coord INT NOT NULL DEFAULT 0 COMMENT 'Y coordinate on 2D floorplan/canvas',
    photo_url VARCHAR(255) NULL COMMENT 'Relative URL to real/sample 360 or POV photograph',
    is_accessible BOOLEAN NOT NULL DEFAULT TRUE COMMENT 'Wheelchair / Universal accessibility',
    is_sample_data BOOLEAN NOT NULL DEFAULT TRUE COMMENT 'Explicit marker for sample/unverified data',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_node_building (building),
    INDEX idx_node_floor (floor),
    INDEX idx_node_category (category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS navigation_edges (
    id INT AUTO_INCREMENT PRIMARY KEY,
    source_node_id INT NOT NULL,
    target_node_id INT NOT NULL,
    distance_meters FLOAT NOT NULL DEFAULT 10.0 COMMENT 'Distance in meters for A*/Dijkstra edge weight',
    direction_hint VARCHAR(255) NULL COMMENT 'Instruction hint e.g., "Walk straight towards the library foyer"',
    is_bidirectional BOOLEAN NOT NULL DEFAULT TRUE,
    is_sample_data BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_node_id) REFERENCES navigation_nodes(id) ON DELETE CASCADE,
    FOREIGN KEY (target_node_id) REFERENCES navigation_nodes(id) ON DELETE CASCADE,
    INDEX idx_edge_source (source_node_id),
    INDEX idx_edge_target (target_node_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ------------------------------------------------------------------------------
-- 3. MODULE 2: AI LOST & FOUND TABLES
-- Item logs, feature vector embeddings, match recommendations
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lost_found_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    report_type ENUM('lost', 'found') NOT NULL,
    title VARCHAR(150) NOT NULL,
    category ENUM('Electronics', 'ID Cards & Docs', 'Books & Stationery', 'Personal Items', 'Valuables', 'Other') NOT NULL DEFAULT 'Other',
    location_reported VARCHAR(150) NOT NULL COMMENT 'Campus location where item was lost or found',
    date_time_reported DATETIME NOT NULL COMMENT 'Incident date and approximate time',
    description TEXT NOT NULL,
    photo_url VARCHAR(255) NULL COMMENT 'Photograph uploaded by reporter',
    image_feature_vector MEDIUMTEXT NULL COMMENT 'JSON/Base64 serialized feature vector for AI similarity matching',
    status ENUM('open', 'matched', 'claimed', 'closed') NOT NULL DEFAULT 'open',
    contact_phone VARCHAR(20) NULL,
    claimed_by_user_id INT NULL,
    verified_by_admin_id INT NULL,
    collected_at DATETIME NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (claimed_by_user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (verified_by_admin_id) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_lf_type (report_type),
    INDEX idx_lf_status (status),
    INDEX idx_lf_category (category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS lost_found_matches (
    id INT AUTO_INCREMENT PRIMARY KEY,
    lost_item_id INT NOT NULL,
    found_item_id INT NOT NULL,
    similarity_score FLOAT NOT NULL COMMENT 'Score between 0.0 and 1.0 calculated by AI matcher',
    status ENUM('suggested', 'verified', 'rejected') NOT NULL DEFAULT 'suggested',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (lost_item_id) REFERENCES lost_found_items(id) ON DELETE CASCADE,
    FOREIGN KEY (found_item_id) REFERENCES lost_found_items(id) ON DELETE CASCADE,
    UNIQUE KEY uq_item_match (lost_item_id, found_item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ------------------------------------------------------------------------------
-- 4. MODULE 3: SMART CANTEEN TABLES
-- Menu categories, menu items, advance orders, teacher priority queue
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS canteen_categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    display_order INT NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS canteen_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    category_id INT NOT NULL,
    name VARCHAR(150) NOT NULL,
    description TEXT NULL,
    price DECIMAL(8, 2) NOT NULL DEFAULT 0.00,
    stock_quantity INT NOT NULL DEFAULT 50,
    is_available BOOLEAN NOT NULL DEFAULT TRUE,
    preparation_time_mins INT NOT NULL DEFAULT 10,
    photo_url VARCHAR(255) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES canteen_categories(id) ON DELETE CASCADE,
    INDEX idx_item_category (category_id),
    INDEX idx_item_available (is_available)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS canteen_orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_code VARCHAR(50) NOT NULL UNIQUE COMMENT 'Human-readable order tracking ID e.g. ORD-20261012-001',
    user_id INT NOT NULL,
    user_role_at_order VARCHAR(20) NOT NULL COMMENT 'Role of user at time of booking',
    is_priority BOOLEAN NOT NULL DEFAULT FALSE COMMENT 'TRUE for Teachers: guarantees teacher-first queue priority',
    total_amount DECIMAL(8, 2) NOT NULL DEFAULT 0.00,
    pickup_time DATETIME NOT NULL COMMENT 'Scheduled advance pickup timestamp',
    order_status ENUM('placed', 'preparing', 'ready', 'collected', 'cancelled', 'refunded') NOT NULL DEFAULT 'placed',
    payment_status ENUM('pending', 'paid', 'refunded') NOT NULL DEFAULT 'paid',
    payment_method ENUM('upi_simulation', 'cash_at_counter', 'card') NOT NULL DEFAULT 'upi_simulation',
    qr_code_path VARCHAR(255) NULL COMMENT 'Path to generated QR code verification image',
    refund_reason TEXT NULL,
    collected_at DATETIME NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_order_status (order_status),
    INDEX idx_order_priority (is_priority),
    INDEX idx_order_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS canteen_order_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    item_id INT NOT NULL,
    item_name VARCHAR(150) NOT NULL,
    unit_price DECIMAL(8, 2) NOT NULL,
    quantity INT NOT NULL DEFAULT 1,
    subtotal DECIMAL(8, 2) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES canteen_orders(id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES canteen_items(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ------------------------------------------------------------------------------
-- 5. AUDIT LOGS TABLE
-- Global auditing of security, administration, and critical transactions
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL,
    action VARCHAR(100) NOT NULL,
    module ENUM('AUTH', 'NAVIGATION', 'LOST_FOUND', 'CANTEEN', 'ADMIN') NOT NULL,
    details TEXT NULL,
    ip_address VARCHAR(50) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_audit_module (module),
    INDEX idx_audit_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
