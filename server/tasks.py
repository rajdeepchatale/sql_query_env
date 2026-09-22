"""
Database schemas, seed data, and task definitions.

Tasks span three independent database domains so an agent has to read the
schema it is given rather than memorize a single layout.

Seed data is intentionally small (3-24 rows per table): grading runs
the reference query on every step, so small tables keep episodes fast while
still containing the edge cases the tasks depend on (NULLs, inactive rows,
cancelled orders, rows with no matches).

When adding a task, also add it to ``openenv.yaml`` and to ``TASK_IDS`` in
``inference.py``; ``tests/test_tasks.py`` fails if the three drift apart.
"""

import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DatabaseSchema:
    """A database domain with its own schema, seed data, and description."""
    id: str
    name: str
    schema_sql: str
    seed_sql: str
    description: str


@dataclass
class Task:
    """A single SQL query task with ground truth."""
    id: str
    difficulty: str  # "easy", "medium", "hard"
    schema_id: str  # Which database schema to use
    question: str
    ground_truth_query: str
    expected_columns: List[str]
    description: str = ""
    hints: List[str] = field(default_factory=list)
    max_steps: int = 5
    challenge_type: str = ""  # e.g. "null_handling", "self_join", "anti_join"


# ---------------------------------------------------------------------------
# Schema 1: Company Analytics
# ---------------------------------------------------------------------------

COMPANY_SCHEMA_SQL = """
CREATE TABLE departments (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    budget REAL NOT NULL,
    location TEXT NOT NULL
);

CREATE TABLE employees (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    department_id INTEGER NOT NULL,
    salary REAL NOT NULL,
    hire_date TEXT NOT NULL,
    manager_id INTEGER,
    is_active INTEGER DEFAULT 1,
    FOREIGN KEY (department_id) REFERENCES departments(id),
    FOREIGN KEY (manager_id) REFERENCES employees(id)
);

CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price REAL NOT NULL,
    stock INTEGER NOT NULL DEFAULT 0,
    created_date TEXT NOT NULL
);

CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    city TEXT NOT NULL,
    country TEXT NOT NULL,
    join_date TEXT NOT NULL,
    tier TEXT NOT NULL DEFAULT 'standard'
);

CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    total_price REAL NOT NULL,
    order_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE reviews (
    id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    review_text TEXT,
    review_date TEXT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(id),
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);
"""

COMPANY_SEED_SQL = """
INSERT INTO departments VALUES (1, 'Engineering', 500000.00, 'San Francisco');
INSERT INTO departments VALUES (2, 'Marketing', 250000.00, 'New York');
INSERT INTO departments VALUES (3, 'Sales', 300000.00, 'Chicago');
INSERT INTO departments VALUES (4, 'Human Resources', 150000.00, 'San Francisco');
INSERT INTO departments VALUES (5, 'Finance', 200000.00, 'New York');

INSERT INTO employees VALUES (1, 'Alice Chen', 'alice@company.com', 1, 145000, '2020-03-15', NULL, 1);
INSERT INTO employees VALUES (2, 'Bob Smith', 'bob@company.com', 1, 130000, '2021-06-01', 1, 1);
INSERT INTO employees VALUES (3, 'Carol Davis', 'carol@company.com', 2, 95000, '2019-11-20', NULL, 1);
INSERT INTO employees VALUES (4, 'David Wilson', 'david@company.com', 1, 125000, '2022-01-10', 1, 1);
INSERT INTO employees VALUES (5, 'Eva Martinez', 'eva@company.com', 3, 110000, '2020-08-05', NULL, 1);
INSERT INTO employees VALUES (6, 'Frank Brown', 'frank@company.com', 3, 98000, '2021-04-22', 5, 1);
INSERT INTO employees VALUES (7, 'Grace Lee', 'grace@company.com', 2, 105000, '2022-07-14', 3, 1);
INSERT INTO employees VALUES (8, 'Henry Taylor', 'henry@company.com', 4, 88000, '2023-02-28', NULL, 1);
INSERT INTO employees VALUES (9, 'Ivy Nguyen', 'ivy@company.com', 5, 115000, '2020-12-01', NULL, 1);
INSERT INTO employees VALUES (10, 'Jack Anderson', 'jack@company.com', 1, 140000, '2019-09-10', 1, 1);
INSERT INTO employees VALUES (11, 'Karen White', 'karen@company.com', 5, 105000, '2021-10-15', 9, 1);
INSERT INTO employees VALUES (12, 'Leo Garcia', 'leo@company.com', 3, 92000, '2023-05-20', 5, 0);
INSERT INTO employees VALUES (13, 'Mia Johnson', 'mia@company.com', 2, 88000, '2022-11-08', 3, 1);
INSERT INTO employees VALUES (14, 'Nathan Park', 'nathan@company.com', 1, 155000, '2018-06-25', NULL, 1);
INSERT INTO employees VALUES (15, 'Olivia Kim', 'olivia@company.com', 4, 82000, '2023-08-12', 8, 1);

INSERT INTO products VALUES (1, 'Laptop Pro 15', 'Electronics', 1299.99, 45, '2023-01-15');
INSERT INTO products VALUES (2, 'Wireless Mouse', 'Electronics', 29.99, 200, '2023-02-20');
INSERT INTO products VALUES (3, 'Standing Desk', 'Furniture', 549.99, 30, '2023-03-10');
INSERT INTO products VALUES (4, 'Noise-Canceling Headphones', 'Electronics', 199.99, 75, '2023-01-25');
INSERT INTO products VALUES (5, 'Ergonomic Chair', 'Furniture', 399.99, 25, '2023-04-05');
INSERT INTO products VALUES (6, 'USB-C Hub', 'Electronics', 49.99, 150, '2023-05-12');
INSERT INTO products VALUES (7, 'Monitor 27inch', 'Electronics', 449.99, 60, '2023-02-14');
INSERT INTO products VALUES (8, 'Keyboard Mechanical', 'Electronics', 89.99, 100, '2023-06-01');
INSERT INTO products VALUES (9, 'Desk Lamp', 'Furniture', 39.99, 80, '2023-03-22');
INSERT INTO products VALUES (10, 'Webcam HD', 'Electronics', 79.99, 90, '2023-07-08');

INSERT INTO customers VALUES (1, 'TechCorp Inc', 'orders@techcorp.com', 'San Francisco', 'USA', '2023-01-10', 'premium');
INSERT INTO customers VALUES (2, 'DataFlow Ltd', 'buy@dataflow.io', 'London', 'UK', '2023-02-15', 'standard');
INSERT INTO customers VALUES (3, 'StartupXYZ', 'procurement@startupxyz.com', 'Berlin', 'Germany', '2023-03-20', 'standard');
INSERT INTO customers VALUES (4, 'MegaCorp', 'orders@megacorp.com', 'Tokyo', 'Japan', '2023-01-05', 'premium');
INSERT INTO customers VALUES (5, 'CloudNine', 'buy@cloudnine.com', 'New York', 'USA', '2023-04-12', 'premium');
INSERT INTO customers VALUES (6, 'InnovateLab', 'purchasing@innovatelab.com', 'Mumbai', 'India', '2023-05-08', 'standard');
INSERT INTO customers VALUES (7, 'AlphaWorks', 'orders@alphaworks.net', 'Sydney', 'Australia', '2023-02-28', 'standard');
INSERT INTO customers VALUES (8, 'BetaSoft', 'buy@betasoft.co', 'Toronto', 'Canada', '2023-06-15', 'premium');

INSERT INTO orders VALUES (1, 1, 1, 5, 6499.95, '2024-01-15', 'completed');
INSERT INTO orders VALUES (2, 1, 4, 10, 1999.90, '2024-01-20', 'completed');
INSERT INTO orders VALUES (3, 2, 2, 20, 599.80, '2024-02-05', 'completed');
INSERT INTO orders VALUES (4, 3, 3, 3, 1649.97, '2024-02-10', 'completed');
INSERT INTO orders VALUES (5, 4, 1, 8, 10399.92, '2024-02-15', 'completed');
INSERT INTO orders VALUES (6, 5, 7, 4, 1799.96, '2024-03-01', 'completed');
INSERT INTO orders VALUES (7, 1, 6, 15, 749.85, '2024-03-10', 'completed');
INSERT INTO orders VALUES (8, 6, 5, 2, 799.98, '2024-03-15', 'shipped');
INSERT INTO orders VALUES (9, 2, 8, 5, 449.95, '2024-03-20', 'shipped');
INSERT INTO orders VALUES (10, 4, 2, 50, 1499.50, '2024-04-01', 'completed');
INSERT INTO orders VALUES (11, 7, 9, 10, 399.90, '2024-04-05', 'completed');
INSERT INTO orders VALUES (12, 3, 10, 6, 479.94, '2024-04-10', 'shipped');
INSERT INTO orders VALUES (13, 8, 1, 3, 3899.97, '2024-04-15', 'pending');
INSERT INTO orders VALUES (14, 5, 5, 5, 1999.95, '2024-04-20', 'completed');
INSERT INTO orders VALUES (15, 6, 8, 8, 719.92, '2024-05-01', 'completed');
INSERT INTO orders VALUES (16, 1, 3, 2, 1099.98, '2024-05-05', 'completed');
INSERT INTO orders VALUES (17, 4, 6, 25, 1249.75, '2024-05-10', 'shipped');
INSERT INTO orders VALUES (18, 7, 4, 3, 599.97, '2024-05-15', 'completed');
INSERT INTO orders VALUES (19, 2, 7, 2, 899.98, '2024-05-20', 'pending');
INSERT INTO orders VALUES (20, 8, 10, 4, 319.96, '2024-05-25', 'completed');
INSERT INTO orders VALUES (21, 5, 2, 30, 899.70, '2024-06-01', 'completed');
INSERT INTO orders VALUES (22, 3, 1, 2, 2599.98, '2024-06-05', 'completed');
INSERT INTO orders VALUES (23, 6, 3, 1, 549.99, '2024-06-10', 'shipped');
INSERT INTO orders VALUES (24, 4, 8, 12, 1079.88, '2024-06-15', 'completed');

INSERT INTO reviews VALUES (1, 1, 1, 5, 'Excellent laptop, very fast!', '2024-02-01');
INSERT INTO reviews VALUES (2, 1, 4, 4, 'Good performance but heavy', '2024-03-01');
INSERT INTO reviews VALUES (3, 2, 2, 4, 'Good mouse, comfortable grip', '2024-02-20');
INSERT INTO reviews VALUES (4, 3, 3, 5, 'Best standing desk ever!', '2024-03-01');
INSERT INTO reviews VALUES (5, 4, 1, 5, 'Amazing noise cancellation', '2024-02-10');
INSERT INTO reviews VALUES (6, 5, 6, 3, 'Decent chair but could be better', '2024-04-01');
INSERT INTO reviews VALUES (7, 7, 5, 4, 'Great display quality', '2024-03-15');
INSERT INTO reviews VALUES (8, 8, 2, 5, 'Perfect mechanical keyboard', '2024-04-05');
INSERT INTO reviews VALUES (9, 6, 1, 4, 'Works well with all my devices', '2024-03-20');
INSERT INTO reviews VALUES (10, 10, 7, 3, 'Average webcam quality', '2024-05-01');
INSERT INTO reviews VALUES (11, 1, 8, 5, 'Worth every penny', '2024-05-10');
INSERT INTO reviews VALUES (12, 4, 5, 4, 'Great sound quality', '2024-05-20');
INSERT INTO reviews VALUES (13, 9, 3, 4, 'Nice desk lamp, adjustable', '2024-04-15');
INSERT INTO reviews VALUES (14, 5, 8, 2, 'Armrests broke after 2 months', '2024-06-01');
INSERT INTO reviews VALUES (15, 2, 6, 4, 'Reliable and affordable', '2024-06-10');
"""

COMPANY_DESCRIPTION = """DATABASE SCHEMA — Company Analytics
=======================================

TABLE: departments
  - id (INTEGER, PK) | name (TEXT) | budget (REAL) | location (TEXT)

TABLE: employees
  - id (INTEGER, PK) | name (TEXT) | email (TEXT) | department_id (FK→departments)
  - salary (REAL) | hire_date (TEXT, YYYY-MM-DD) | manager_id (FK→employees, nullable)
  - is_active (INTEGER, 1=active/0=inactive)

TABLE: products
  - id (INTEGER, PK) | name (TEXT) | category (TEXT, 'Electronics'/'Furniture')
  - price (REAL) | stock (INTEGER) | created_date (TEXT)

TABLE: customers
  - id (INTEGER, PK) | name (TEXT) | email (TEXT) | city (TEXT) | country (TEXT)
  - join_date (TEXT) | tier (TEXT, 'standard'/'premium')

TABLE: orders
  - id (INTEGER, PK) | customer_id (FK→customers) | product_id (FK→products)
  - quantity (INTEGER) | total_price (REAL) | order_date (TEXT)
  - status (TEXT, 'pending'/'shipped'/'completed')

TABLE: reviews
  - id (INTEGER, PK) | product_id (FK→products) | customer_id (FK→customers)
  - rating (INTEGER, 1-5) | review_text (TEXT, nullable) | review_date (TEXT)

RELATIONSHIPS:
  employees.department_id → departments.id
  employees.manager_id → employees.id (self-referencing, hierarchical)
  orders.customer_id → customers.id
  orders.product_id → products.id
  reviews.product_id → products.id
  reviews.customer_id → customers.id
"""


# ---------------------------------------------------------------------------
# Schema 2: Hospital Management
# ---------------------------------------------------------------------------

HOSPITAL_SCHEMA_SQL = """
CREATE TABLE wards (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    capacity INTEGER NOT NULL,
    floor INTEGER NOT NULL
);

CREATE TABLE doctors (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    specialization TEXT NOT NULL,
    ward_id INTEGER NOT NULL,
    experience_years INTEGER NOT NULL,
    is_available INTEGER DEFAULT 1,
    FOREIGN KEY (ward_id) REFERENCES wards(id)
);

CREATE TABLE patients (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    age INTEGER NOT NULL,
    gender TEXT NOT NULL,
    ward_id INTEGER,
    admission_date TEXT NOT NULL,
    discharge_date TEXT,
    diagnosis TEXT NOT NULL,
    insurance_type TEXT NOT NULL DEFAULT 'none',
    FOREIGN KEY (ward_id) REFERENCES wards(id)
);

CREATE TABLE appointments (
    id INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL,
    doctor_id INTEGER NOT NULL,
    appointment_date TEXT NOT NULL,
    appointment_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'scheduled',
    notes TEXT,
    FOREIGN KEY (patient_id) REFERENCES patients(id),
    FOREIGN KEY (doctor_id) REFERENCES doctors(id)
);

CREATE TABLE medications (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    unit_cost REAL NOT NULL
);

CREATE TABLE prescriptions (
    id INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL,
    doctor_id INTEGER NOT NULL,
    medication_id INTEGER NOT NULL,
    dosage TEXT NOT NULL,
    frequency TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT,
    FOREIGN KEY (patient_id) REFERENCES patients(id),
    FOREIGN KEY (doctor_id) REFERENCES doctors(id),
    FOREIGN KEY (medication_id) REFERENCES medications(id)
);
"""

HOSPITAL_SEED_SQL = """
INSERT INTO wards VALUES (1, 'Cardiology', 30, 2);
INSERT INTO wards VALUES (2, 'Neurology', 20, 3);
INSERT INTO wards VALUES (3, 'Orthopedics', 25, 1);
INSERT INTO wards VALUES (4, 'Pediatrics', 35, 1);
INSERT INTO wards VALUES (5, 'Emergency', 40, 0);

INSERT INTO doctors VALUES (1, 'Dr. Sarah Patel', 'Cardiologist', 1, 15, 1);
INSERT INTO doctors VALUES (2, 'Dr. James Liu', 'Neurologist', 2, 12, 1);
INSERT INTO doctors VALUES (3, 'Dr. Maria Garcia', 'Orthopedic Surgeon', 3, 20, 1);
INSERT INTO doctors VALUES (4, 'Dr. Robert Kim', 'Pediatrician', 4, 8, 1);
INSERT INTO doctors VALUES (5, 'Dr. Emily Chen', 'Emergency Medicine', 5, 10, 1);
INSERT INTO doctors VALUES (6, 'Dr. Michael Brown', 'Cardiologist', 1, 5, 0);
INSERT INTO doctors VALUES (7, 'Dr. Lisa Wong', 'Neurologist', 2, 18, 1);
INSERT INTO doctors VALUES (8, 'Dr. David Okafor', 'Pediatrician', 4, 3, 1);

INSERT INTO patients VALUES (1, 'John Doe', 65, 'M', 1, '2024-01-10', '2024-01-20', 'Chest Pain', 'private');
INSERT INTO patients VALUES (2, 'Jane Smith', 45, 'F', 2, '2024-01-15', '2024-02-01', 'Migraine', 'government');
INSERT INTO patients VALUES (3, 'Bob Johnson', 72, 'M', 1, '2024-02-01', NULL, 'Heart Failure', 'private');
INSERT INTO patients VALUES (4, 'Alice Williams', 8, 'F', 4, '2024-02-10', '2024-02-15', 'Flu', 'private');
INSERT INTO patients VALUES (5, 'Charlie Brown', 55, 'M', 3, '2024-02-20', '2024-03-15', 'Fracture', 'government');
INSERT INTO patients VALUES (6, 'Diana Ross', 38, 'F', 5, '2024-03-01', '2024-03-02', 'Laceration', 'none');
INSERT INTO patients VALUES (7, 'Edward Lee', 80, 'M', 1, '2024-03-10', NULL, 'Arrhythmia', 'government');
INSERT INTO patients VALUES (8, 'Fiona Clark', 12, 'F', 4, '2024-03-15', '2024-03-18', 'Asthma', 'private');
INSERT INTO patients VALUES (9, 'George Martin', 60, 'M', 2, '2024-03-20', '2024-04-05', 'Stroke', 'private');
INSERT INTO patients VALUES (10, 'Helen Park', 50, 'F', 3, '2024-04-01', NULL, 'Joint Replacement', 'government');
INSERT INTO patients VALUES (11, 'Ivan Petrov', 70, 'M', 5, '2024-04-10', '2024-04-11', 'Chest Pain', 'none');
INSERT INTO patients VALUES (12, 'Julia Santos', 5, 'F', 4, '2024-04-15', '2024-04-17', 'Ear Infection', 'private');

INSERT INTO appointments VALUES (1, 1, 1, '2024-01-12', 'Follow-up', 'completed', 'ECG normal');
INSERT INTO appointments VALUES (2, 2, 2, '2024-01-20', 'Consultation', 'completed', 'MRI scheduled');
INSERT INTO appointments VALUES (3, 3, 1, '2024-02-05', 'Initial', 'completed', 'Admitted to ICU');
INSERT INTO appointments VALUES (4, 4, 4, '2024-02-12', 'Follow-up', 'completed', 'Recovering well');
INSERT INTO appointments VALUES (5, 5, 3, '2024-02-25', 'Surgery', 'completed', 'Pin insertion');
INSERT INTO appointments VALUES (6, 6, 5, '2024-03-01', 'Emergency', 'completed', 'Stitches applied');
INSERT INTO appointments VALUES (7, 7, 1, '2024-03-12', 'Initial', 'completed', 'Pacemaker evaluation');
INSERT INTO appointments VALUES (8, 9, 7, '2024-03-22', 'Initial', 'completed', 'CT scan ordered');
INSERT INTO appointments VALUES (9, 3, 6, '2024-03-15', 'Follow-up', 'cancelled', NULL);
INSERT INTO appointments VALUES (10, 10, 3, '2024-04-03', 'Surgery', 'scheduled', 'Pre-op clearance needed');
INSERT INTO appointments VALUES (11, 11, 5, '2024-04-10', 'Emergency', 'completed', 'Ruled out MI');
INSERT INTO appointments VALUES (12, 1, 1, '2024-04-15', 'Follow-up', 'scheduled', NULL);
INSERT INTO appointments VALUES (13, 8, 4, '2024-03-16', 'Follow-up', 'completed', 'Inhaler prescribed');
INSERT INTO appointments VALUES (14, 9, 2, '2024-04-01', 'Follow-up', 'completed', 'Rehab started');
INSERT INTO appointments VALUES (15, 1, 1, '2024-05-10', 'Follow-up', 'completed', 'Stable condition');
INSERT INTO appointments VALUES (16, 3, 1, '2024-04-20', 'Follow-up', 'completed', 'Medication adjusted');
INSERT INTO appointments VALUES (17, 9, 7, '2024-04-25', 'Follow-up', 'completed', 'Good progress');

INSERT INTO medications VALUES (1, 'Aspirin', 'Blood Thinner', 0.50);
INSERT INTO medications VALUES (2, 'Metoprolol', 'Beta Blocker', 1.20);
INSERT INTO medications VALUES (3, 'Sumatriptan', 'Migraine Relief', 8.50);
INSERT INTO medications VALUES (4, 'Amoxicillin', 'Antibiotic', 0.80);
INSERT INTO medications VALUES (5, 'Ibuprofen', 'Pain Relief', 0.30);
INSERT INTO medications VALUES (6, 'Albuterol', 'Bronchodilator', 15.00);
INSERT INTO medications VALUES (7, 'Warfarin', 'Anticoagulant', 2.00);
INSERT INTO medications VALUES (8, 'Lisinopril', 'ACE Inhibitor', 0.90);

INSERT INTO prescriptions VALUES (1, 1, 1, 1, '81mg', 'daily', '2024-01-12', NULL);
INSERT INTO prescriptions VALUES (2, 1, 1, 2, '50mg', 'twice daily', '2024-01-12', '2024-03-12');
INSERT INTO prescriptions VALUES (3, 2, 2, 3, '50mg', 'as needed', '2024-01-20', NULL);
INSERT INTO prescriptions VALUES (4, 3, 1, 7, '5mg', 'daily', '2024-02-05', NULL);
INSERT INTO prescriptions VALUES (5, 3, 1, 8, '10mg', 'daily', '2024-02-05', NULL);
INSERT INTO prescriptions VALUES (6, 5, 3, 5, '400mg', 'three times daily', '2024-02-25', '2024-03-25');
INSERT INTO prescriptions VALUES (7, 8, 4, 6, '2 puffs', 'as needed', '2024-03-16', NULL);
INSERT INTO prescriptions VALUES (8, 7, 1, 2, '25mg', 'daily', '2024-03-12', NULL);
INSERT INTO prescriptions VALUES (9, 9, 7, 1, '325mg', 'daily', '2024-03-22', NULL);
INSERT INTO prescriptions VALUES (10, 12, 4, 4, '250mg', 'three times daily', '2024-04-15', '2024-04-25');
INSERT INTO prescriptions VALUES (11, 11, 1, 1, '81mg', 'daily', '2024-04-10', NULL);
INSERT INTO prescriptions VALUES (12, 8, 5, 5, '200mg', 'as needed', '2024-03-17', '2024-03-20');
INSERT INTO prescriptions VALUES (13, 10, 7, 5, '400mg', 'twice daily', '2024-04-05', NULL);
"""

HOSPITAL_DESCRIPTION = """DATABASE SCHEMA — Hospital Management
=======================================

TABLE: wards
  - id (INTEGER, PK) | name (TEXT) | capacity (INTEGER) | floor (INTEGER)

TABLE: doctors
  - id (INTEGER, PK) | name (TEXT) | specialization (TEXT)
  - ward_id (FK→wards) | experience_years (INTEGER) | is_available (INTEGER)

TABLE: patients
  - id (INTEGER, PK) | name (TEXT) | age (INTEGER) | gender (TEXT, 'M'/'F')
  - ward_id (FK→wards, nullable) | admission_date (TEXT) | discharge_date (TEXT, nullable)
  - diagnosis (TEXT) | insurance_type (TEXT, 'private'/'government'/'none')

TABLE: appointments
  - id (INTEGER, PK) | patient_id (FK→patients) | doctor_id (FK→doctors)
  - appointment_date (TEXT) | appointment_type (TEXT)
  - status (TEXT, 'scheduled'/'completed'/'cancelled') | notes (TEXT, nullable)

TABLE: medications
  - id (INTEGER, PK) | name (TEXT) | category (TEXT) | unit_cost (REAL)

TABLE: prescriptions
  - id (INTEGER, PK) | patient_id (FK→patients) | doctor_id (FK→doctors)
  - medication_id (FK→medications) | dosage (TEXT) | frequency (TEXT)
  - start_date (TEXT) | end_date (TEXT, nullable — NULL means ongoing)

RELATIONSHIPS:
  doctors.ward_id → wards.id
  patients.ward_id → wards.id (nullable — outpatients have no ward)
  appointments.patient_id → patients.id
  appointments.doctor_id → doctors.id
  prescriptions.patient_id → patients.id
  prescriptions.doctor_id → doctors.id
  prescriptions.medication_id → medications.id

NOTE: discharge_date = NULL means patient is still admitted.
      end_date = NULL in prescriptions means medication is ongoing.
"""


# ---------------------------------------------------------------------------
# Schema 3: E-Commerce Platform
# ---------------------------------------------------------------------------

ECOMMERCE_SCHEMA_SQL = """
CREATE TABLE sellers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    rating REAL NOT NULL,
    city TEXT NOT NULL,
    joined_date TEXT NOT NULL
);

CREATE TABLE categories (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    parent_category TEXT
);

CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category_id INTEGER NOT NULL,
    seller_id INTEGER NOT NULL,
    price REAL NOT NULL,
    stock INTEGER NOT NULL DEFAULT 0,
    listed_date TEXT NOT NULL,
    FOREIGN KEY (category_id) REFERENCES categories(id),
    FOREIGN KEY (seller_id) REFERENCES sellers(id)
);

CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    city TEXT NOT NULL,
    signup_date TEXT NOT NULL,
    is_premium INTEGER DEFAULT 0
);

CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    order_date TEXT NOT NULL,
    total_amount REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    payment_method TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE order_items (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE returns (
    id INTEGER PRIMARY KEY,
    order_item_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    return_date TEXT NOT NULL,
    refund_amount REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    FOREIGN KEY (order_item_id) REFERENCES order_items(id)
);
"""

ECOMMERCE_SEED_SQL = """
INSERT INTO sellers VALUES (1, 'TechWorld', 4.5, 'Shenzhen', '2022-01-10');
INSERT INTO sellers VALUES (2, 'HomeStyle', 4.2, 'Mumbai', '2022-03-15');
INSERT INTO sellers VALUES (3, 'FashionHub', 3.8, 'Milan', '2022-06-20');
INSERT INTO sellers VALUES (4, 'BookBarn', 4.7, 'New York', '2021-11-01');
INSERT INTO sellers VALUES (5, 'SportZone', 4.0, 'Tokyo', '2023-02-14');

INSERT INTO categories VALUES (1, 'Electronics', NULL);
INSERT INTO categories VALUES (2, 'Smartphones', 'Electronics');
INSERT INTO categories VALUES (3, 'Laptops', 'Electronics');
INSERT INTO categories VALUES (4, 'Home & Kitchen', NULL);
INSERT INTO categories VALUES (5, 'Furniture', 'Home & Kitchen');
INSERT INTO categories VALUES (6, 'Appliances', 'Home & Kitchen');
INSERT INTO categories VALUES (7, 'Books', NULL);
INSERT INTO categories VALUES (8, 'Fiction', 'Books');
INSERT INTO categories VALUES (9, 'Non-Fiction', 'Books');
INSERT INTO categories VALUES (10, 'Sports', NULL);

INSERT INTO products VALUES (1, 'Galaxy S24', 2, 1, 899.99, 120, '2024-01-15');
INSERT INTO products VALUES (2, 'MacBook Air M3', 3, 1, 1199.99, 45, '2024-01-20');
INSERT INTO products VALUES (3, 'Blender Pro', 6, 2, 79.99, 200, '2024-02-01');
INSERT INTO products VALUES (4, 'Oak Dining Table', 5, 2, 599.99, 15, '2024-02-10');
INSERT INTO products VALUES (5, 'Running Shoes X1', 10, 5, 129.99, 300, '2024-01-05');
INSERT INTO products VALUES (6, 'Python Crash Course', 9, 4, 39.99, 500, '2024-03-01');
INSERT INTO products VALUES (7, 'The Great Gatsby', 8, 4, 12.99, 350, '2024-01-10');
INSERT INTO products VALUES (8, 'Yoga Mat Premium', 10, 5, 49.99, 180, '2024-02-20');
INSERT INTO products VALUES (9, 'Coffee Maker Deluxe', 6, 2, 149.99, 90, '2024-03-05');
INSERT INTO products VALUES (10, 'Pixel 8 Pro', 2, 1, 999.99, 80, '2024-03-10');
INSERT INTO products VALUES (11, 'Standing Desk Frame', 5, 2, 349.99, 40, '2024-03-15');
INSERT INTO products VALUES (12, 'Dune: Part One', 8, 4, 14.99, 200, '2024-02-01');

INSERT INTO users VALUES (1, 'Priya Sharma', 'priya@email.com', 'Mumbai', '2023-06-15', 1);
INSERT INTO users VALUES (2, 'Tom Baker', 'tom@email.com', 'London', '2023-08-20', 0);
INSERT INTO users VALUES (3, 'Yuki Tanaka', 'yuki@email.com', 'Tokyo', '2023-09-01', 1);
INSERT INTO users VALUES (4, 'Carlos Mendez', 'carlos@email.com', 'Mexico City', '2023-11-10', 0);
INSERT INTO users VALUES (5, 'Anna Kowalski', 'anna@email.com', 'Warsaw', '2024-01-05', 1);
INSERT INTO users VALUES (6, 'Wei Zhang', 'wei@email.com', 'Shanghai', '2024-02-14', 0);

INSERT INTO orders VALUES (1, 1, '2024-01-20', 899.99, 'delivered', 'credit_card');
INSERT INTO orders VALUES (2, 1, '2024-02-15', 1279.98, 'delivered', 'credit_card');
INSERT INTO orders VALUES (3, 2, '2024-02-01', 79.99, 'delivered', 'paypal');
INSERT INTO orders VALUES (4, 3, '2024-02-20', 1329.98, 'delivered', 'credit_card');
INSERT INTO orders VALUES (5, 4, '2024-03-01', 52.98, 'delivered', 'debit_card');
INSERT INTO orders VALUES (6, 5, '2024-03-10', 899.99, 'delivered', 'credit_card');
INSERT INTO orders VALUES (7, 1, '2024-03-15', 199.98, 'shipped', 'credit_card');
INSERT INTO orders VALUES (8, 2, '2024-03-20', 599.99, 'delivered', 'paypal');
INSERT INTO orders VALUES (9, 3, '2024-04-01', 179.98, 'delivered', 'credit_card');
INSERT INTO orders VALUES (10, 6, '2024-04-05', 1199.99, 'pending', 'credit_card');
INSERT INTO orders VALUES (11, 4, '2024-04-10', 129.99, 'delivered', 'debit_card');
INSERT INTO orders VALUES (12, 5, '2024-04-15', 349.99, 'cancelled', 'credit_card');

INSERT INTO order_items VALUES (1, 1, 1, 1, 899.99);
INSERT INTO order_items VALUES (2, 2, 2, 1, 1199.99);
INSERT INTO order_items VALUES (3, 2, 3, 1, 79.99);
INSERT INTO order_items VALUES (4, 3, 3, 1, 79.99);
INSERT INTO order_items VALUES (5, 4, 2, 1, 1199.99);
INSERT INTO order_items VALUES (6, 4, 5, 1, 129.99);
INSERT INTO order_items VALUES (7, 5, 6, 1, 39.99);
INSERT INTO order_items VALUES (8, 5, 7, 1, 12.99);
INSERT INTO order_items VALUES (9, 6, 1, 1, 899.99);
INSERT INTO order_items VALUES (10, 7, 8, 2, 49.99);
INSERT INTO order_items VALUES (11, 7, 9, 1, 149.99);
INSERT INTO order_items VALUES (12, 8, 4, 1, 599.99);
INSERT INTO order_items VALUES (13, 9, 5, 1, 129.99);
INSERT INTO order_items VALUES (14, 9, 8, 1, 49.99);
INSERT INTO order_items VALUES (15, 10, 2, 1, 1199.99);
INSERT INTO order_items VALUES (16, 11, 5, 1, 129.99);
INSERT INTO order_items VALUES (17, 12, 11, 1, 349.99);

INSERT INTO returns VALUES (1, 4, 'Defective product', '2024-02-10', 79.99, 'refunded');
INSERT INTO returns VALUES (2, 6, 'Wrong size', '2024-03-01', 129.99, 'refunded');
INSERT INTO returns VALUES (3, 10, 'Changed mind', '2024-03-25', 99.98, 'pending');
"""

ECOMMERCE_DESCRIPTION = """DATABASE SCHEMA — E-Commerce Platform
=======================================

TABLE: sellers
  - id (INTEGER, PK) | name (TEXT) | rating (REAL, 0.0-5.0) | city (TEXT)
  - joined_date (TEXT)

TABLE: categories
  - id (INTEGER, PK) | name (TEXT) | parent_category (TEXT, nullable — NULL = top-level)

TABLE: products
  - id (INTEGER, PK) | name (TEXT) | category_id (FK→categories) | seller_id (FK→sellers)
  - price (REAL) | stock (INTEGER) | listed_date (TEXT)

TABLE: users
  - id (INTEGER, PK) | name (TEXT) | email (TEXT) | city (TEXT)
  - signup_date (TEXT) | is_premium (INTEGER, 0/1)

TABLE: orders
  - id (INTEGER, PK) | user_id (FK→users) | order_date (TEXT)
  - total_amount (REAL) | status (TEXT, 'pending'/'shipped'/'delivered'/'cancelled')
  - payment_method (TEXT, 'credit_card'/'debit_card'/'paypal')

TABLE: order_items
  - id (INTEGER, PK) | order_id (FK→orders) | product_id (FK→products)
  - quantity (INTEGER) | unit_price (REAL)

TABLE: returns
  - id (INTEGER, PK) | order_item_id (FK→order_items) | reason (TEXT)
  - return_date (TEXT) | refund_amount (REAL)
  - status (TEXT, 'pending'/'refunded'/'rejected')

RELATIONSHIPS:
  products.category_id → categories.id
  products.seller_id → sellers.id
  orders.user_id → users.id
  order_items.order_id → orders.id
  order_items.product_id → products.id
  returns.order_item_id → order_items.id

NOTE: Categories have a parent_category for hierarchy (e.g., Smartphones → Electronics).
      Returns reference order_items, not orders directly.
"""


# ---------------------------------------------------------------------------
# Schema registry
# ---------------------------------------------------------------------------

SCHEMAS: Dict[str, DatabaseSchema] = {
    "company": DatabaseSchema(
        id="company",
        name="Company Analytics",
        schema_sql=COMPANY_SCHEMA_SQL,
        seed_sql=COMPANY_SEED_SQL,
        description=COMPANY_DESCRIPTION,
    ),
    "hospital": DatabaseSchema(
        id="hospital",
        name="Hospital Management",
        schema_sql=HOSPITAL_SCHEMA_SQL,
        seed_sql=HOSPITAL_SEED_SQL,
        description=HOSPITAL_DESCRIPTION,
    ),
    "ecommerce": DatabaseSchema(
        id="ecommerce",
        name="E-Commerce Platform",
        schema_sql=ECOMMERCE_SCHEMA_SQL,
        seed_sql=ECOMMERCE_SEED_SQL,
        description=ECOMMERCE_DESCRIPTION,
    ),
}


# Authorizer action codes a plain SELECT needs. Everything else (writes,
# schema changes, PRAGMA, ATTACH, transactions) is denied. SQLITE_RECURSIVE
# (33) is needed for recursive CTEs; the constant only exists on Python 3.11+.
_READ_ONLY_ACTIONS = frozenset({
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    getattr(sqlite3, "SQLITE_RECURSIVE", 33),
})


def _read_only_authorizer(action: int, *_args) -> int:
    return sqlite3.SQLITE_OK if action in _READ_ONLY_ACTIONS else sqlite3.SQLITE_DENY


def create_database(schema_id: str = "company") -> sqlite3.Connection:
    """Create a seeded, read-only in-memory SQLite database for a domain.

    The authorizer is installed after seeding, so every statement the agent
    submits is compiled against it: anything other than a read is rejected
    by SQLite before it runs, and the episode's data cannot be modified.
    """
    schema = SCHEMAS[schema_id]
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema.schema_sql)
    conn.executescript(schema.seed_sql)
    conn.set_authorizer(_read_only_authorizer)
    return conn


def get_expected_result(conn: sqlite3.Connection, query: str) -> List[Tuple]:
    """Execute a query and return the result set."""
    cursor = conn.execute(query)
    return cursor.fetchall()


# ---------------------------------------------------------------------------
# Company tasks
# ---------------------------------------------------------------------------

COMPANY_TASKS = [
    # ── EASY ──
    Task(
        id="company_easy_1",
        difficulty="easy",
        schema_id="company",
        question="List all active employees in the Engineering department, showing their name and salary, sorted by salary from highest to lowest.",
        ground_truth_query="""
            SELECT e.name, e.salary
            FROM employees e
            JOIN departments d ON e.department_id = d.id
            WHERE d.name = 'Engineering' AND e.is_active = 1
            ORDER BY e.salary DESC
        """,
        expected_columns=["name", "salary"],
        description="Simple filtered query with sorting",
        hints=["Use employees and departments tables", "Filter by department name and active status"],
        max_steps=5,
    ),
    Task(
        id="company_easy_2",
        difficulty="easy",
        schema_id="company",
        question="Show all products in the 'Electronics' category with a price greater than $50, sorted by price ascending.",
        ground_truth_query="""
            SELECT name, price
            FROM products
            WHERE category = 'Electronics' AND price > 50
            ORDER BY price ASC
        """,
        expected_columns=["name", "price"],
        description="Single table filter and sort",
        hints=["Use the products table", "Filter by category and price"],
        max_steps=5,
    ),
    # ── MEDIUM ──
    Task(
        id="company_medium_1",
        difficulty="medium",
        schema_id="company",
        question="Find the total revenue (sum of total_price) per product category for completed orders. Show the category and total revenue, sorted by revenue descending.",
        ground_truth_query="""
            SELECT p.category, SUM(o.total_price) AS total_revenue
            FROM orders o
            JOIN products p ON o.product_id = p.id
            WHERE o.status = 'completed'
            GROUP BY p.category
            ORDER BY total_revenue DESC
        """,
        expected_columns=["category", "total_revenue"],
        description="Aggregation with JOIN and GROUP BY",
        hints=["Join orders with products", "Filter for completed orders", "Group by category"],
        max_steps=6,
    ),
    Task(
        id="company_medium_2",
        difficulty="medium",
        schema_id="company",
        question="Considering only active employees, find the average salary per department, but only show departments where that average exceeds $100,000. Show department name and average salary, sorted by average salary descending.",
        ground_truth_query="""
            SELECT d.name, AVG(e.salary) AS avg_salary
            FROM employees e
            JOIN departments d ON e.department_id = d.id
            WHERE e.is_active = 1
            GROUP BY d.name
            HAVING AVG(e.salary) > 100000
            ORDER BY avg_salary DESC
        """,
        expected_columns=["name", "avg_salary"],
        description="GROUP BY with HAVING clause",
        hints=["Join employees with departments", "Use GROUP BY and HAVING"],
        max_steps=6,
    ),
    # ── HARD ──
    Task(
        id="company_hard_1",
        difficulty="hard",
        schema_id="company",
        question="Calculate each department's salary budget utilization: show the department name, total active employee salaries, department budget, and the utilization percentage (total salaries / budget * 100, rounded to 1 decimal). Sort by utilization percentage descending.",
        ground_truth_query="""
            SELECT
                d.name,
                SUM(e.salary) AS total_salaries,
                d.budget,
                ROUND(SUM(e.salary) * 100.0 / d.budget, 1) AS utilization_pct
            FROM departments d
            JOIN employees e ON d.id = e.department_id
            WHERE e.is_active = 1
            GROUP BY d.id, d.name, d.budget
            ORDER BY utilization_pct DESC
        """,
        expected_columns=["name", "total_salaries", "budget", "utilization_pct"],
        description="Computed columns with percentage calculations",
        hints=[
            "Join departments with employees",
            "Filter active employees only",
            "Compute: total_salaries / budget * 100",
        ],
        max_steps=8,
        challenge_type="computation",
    ),
]

# ---------------------------------------------------------------------------
# Hospital tasks
# ---------------------------------------------------------------------------

HOSPITAL_TASKS = [
    # ── EASY ──
    Task(
        id="hospital_easy_1",
        difficulty="easy",
        schema_id="hospital",
        question="List all patients who are currently still admitted (discharge_date is NULL). Show their name, diagnosis, and admission date, sorted by admission date.",
        ground_truth_query="""
            SELECT name, diagnosis, admission_date
            FROM patients
            WHERE discharge_date IS NULL
            ORDER BY admission_date ASC
        """,
        expected_columns=["name", "diagnosis", "admission_date"],
        description="NULL handling filter",
        hints=["Use the patients table", "NULL means still admitted — use IS NULL"],
        max_steps=5,
        challenge_type="null_handling",
    ),
    # ── MEDIUM ──
    Task(
        id="hospital_medium_1",
        difficulty="medium",
        schema_id="hospital",
        question="Find the total medication cost for each currently admitted patient. Show the patient name, number of active prescriptions (end_date IS NULL), and the total daily medication cost (sum of medication unit_cost). Sort by total cost descending.",
        ground_truth_query="""
            SELECT
                p.name,
                COUNT(pr.id) AS active_prescriptions,
                SUM(m.unit_cost) AS daily_med_cost
            FROM patients p
            JOIN prescriptions pr ON p.id = pr.patient_id
            JOIN medications m ON pr.medication_id = m.id
            WHERE p.discharge_date IS NULL AND pr.end_date IS NULL
            GROUP BY p.id, p.name
            ORDER BY daily_med_cost DESC
        """,
        expected_columns=["name", "active_prescriptions", "daily_med_cost"],
        description="Multi-table JOIN with NULL filters and aggregation",
        hints=[
            "Join patients, prescriptions, and medications",
            "Filter: patient still admitted (discharge_date IS NULL)",
            "Filter: prescription still active (end_date IS NULL)",
        ],
        max_steps=7,
        challenge_type="multi_null",
    ),
    # ── HARD ──
    Task(
        id="hospital_hard_1",
        difficulty="hard",
        schema_id="hospital",
        question="Find doctors who have prescribed medications to patients outside their own ward. Show the doctor's name, their ward name, the patient's name, the patient's ward name, and the medication prescribed. Sort by doctor name.",
        ground_truth_query="""
            SELECT
                d.name AS doctor_name,
                wd.name AS doctor_ward,
                p.name AS patient_name,
                wp.name AS patient_ward,
                m.name AS medication
            FROM prescriptions pr
            JOIN doctors d ON pr.doctor_id = d.id
            JOIN patients p ON pr.patient_id = p.id
            JOIN medications m ON pr.medication_id = m.id
            JOIN wards wd ON d.ward_id = wd.id
            JOIN wards wp ON p.ward_id = wp.id
            WHERE d.ward_id != p.ward_id
            ORDER BY d.name
        """,
        expected_columns=["doctor_name", "doctor_ward", "patient_name", "patient_ward", "medication"],
        description="Cross-ward prescription analysis — 5-table JOIN with the wards table joined twice",
        hints=[
            "Join prescriptions with doctors, patients, medications, and wards (twice!)",
            "Join wards once for doctor's ward and once for patient's ward",
            "Compare doctor's ward_id with patient's ward_id",
        ],
        max_steps=10,
        challenge_type="multi_join_complex",
    ),
]

# ---------------------------------------------------------------------------
# E-Commerce tasks
# ---------------------------------------------------------------------------

ECOMMERCE_TASKS = [
    # ── EASY ──
    Task(
        id="ecommerce_easy_1",
        difficulty="easy",
        schema_id="ecommerce",
        question="List all premium users and the city they are from, along with their signup date. Sort by signup date, most recent first.",
        ground_truth_query="""
            SELECT name, city, signup_date
            FROM users
            WHERE is_premium = 1
            ORDER BY signup_date DESC
        """,
        expected_columns=["name", "city", "signup_date"],
        description="Simple filter on single table",
        hints=["Use the users table", "Filter by is_premium = 1"],
        max_steps=5,
    ),
    # ── MEDIUM ──
    Task(
        id="ecommerce_medium_1",
        difficulty="medium",
        schema_id="ecommerce",
        question="Find the total revenue per seller for delivered orders only. Show the seller name, seller rating, number of items sold, and total revenue. Sort by total revenue descending.",
        ground_truth_query="""
            SELECT
                s.name,
                s.rating,
                SUM(oi.quantity) AS items_sold,
                SUM(oi.quantity * oi.unit_price) AS total_revenue
            FROM sellers s
            JOIN products p ON s.id = p.seller_id
            JOIN order_items oi ON p.id = oi.product_id
            JOIN orders o ON oi.order_id = o.id
            WHERE o.status = 'delivered'
            GROUP BY s.id, s.name, s.rating
            ORDER BY total_revenue DESC
        """,
        expected_columns=["name", "rating", "items_sold", "total_revenue"],
        description="4-table JOIN with aggregation and status filter",
        hints=[
            "Chain: sellers → products → order_items → orders",
            "Filter for delivered orders",
            "Group by seller",
        ],
        max_steps=7,
    ),
    # ── HARD ──
    Task(
        id="ecommerce_hard_1",
        difficulty="hard",
        schema_id="ecommerce",
        question="Calculate the return rate for each product category that has delivered sales. Show the category name, total items sold (sum of quantities from delivered orders), total items returned (the number of return records for the category, regardless of order or return status), and the return rate as a percentage (returned / sold * 100, rounded to 1 decimal). Include categories with zero returns. Sort by return rate descending.",
        ground_truth_query="""
            SELECT
                c.name AS category,
                COALESCE(SUM(oi.quantity), 0) AS total_sold,
                COALESCE(returned.total_returned, 0) AS total_returned,
                ROUND(
                    COALESCE(returned.total_returned, 0) * 100.0 /
                    CASE WHEN SUM(oi.quantity) = 0 THEN 1 ELSE SUM(oi.quantity) END,
                    1
                ) AS return_rate_pct
            FROM categories c
            JOIN products p ON c.id = p.category_id
            JOIN order_items oi ON p.id = oi.product_id
            JOIN orders o ON oi.order_id = o.id
            LEFT JOIN (
                SELECT c2.id AS cat_id, COUNT(r.id) AS total_returned
                FROM returns r
                JOIN order_items oi2 ON r.order_item_id = oi2.id
                JOIN products p2 ON oi2.product_id = p2.id
                JOIN categories c2 ON p2.category_id = c2.id
                GROUP BY c2.id
            ) returned ON c.id = returned.cat_id
            WHERE o.status = 'delivered'
            GROUP BY c.id, c.name, returned.total_returned
            ORDER BY return_rate_pct DESC
        """,
        expected_columns=["category", "total_sold", "total_returned", "return_rate_pct"],
        description="Return rate analysis — subquery + LEFT JOIN + COALESCE + division-by-zero handling",
        hints=[
            "You need to count items sold per category AND items returned per category",
            "Use a subquery or LEFT JOIN for returns (some categories have zero returns)",
            "Handle division by zero with CASE WHEN",
            "Use COALESCE for NULL return counts",
        ],
        max_steps=10,
        challenge_type="subquery_with_edge_cases",
    ),
]


# ---------------------------------------------------------------------------
# Additional hard tasks — one per domain, each built around a classic pattern
# ---------------------------------------------------------------------------

EXPERT_TASKS = [
    # Self-join: employees vs their managers (company)
    Task(
        id="company_hard_2",
        difficulty="hard",
        schema_id="company",
        question="Find employees who earn more than their direct manager. Show the employee name, employee salary, manager name, and manager salary. Only include active employees with active managers. Sort by the salary difference (employee salary minus manager salary) descending.",
        ground_truth_query="""
            SELECT
                e.name AS employee_name,
                e.salary AS employee_salary,
                m.name AS manager_name,
                m.salary AS manager_salary
            FROM employees e
            JOIN employees m ON e.manager_id = m.id
            WHERE e.is_active = 1 AND m.is_active = 1
              AND e.salary > m.salary
            ORDER BY (e.salary - m.salary) DESC
        """,
        expected_columns=["employee_name", "employee_salary", "manager_name", "manager_salary"],
        description="Self-join with comparison across hierarchical relationship",
        hints=[
            "You need to join the employees table with itself",
            "Alias one as 'e' (employee) and the other as 'm' (manager)",
            "The manager_id column links employee to manager",
            "Compare salaries between the employee row and the manager row",
        ],
        max_steps=8,
        challenge_type="self_join",
    ),

    # Repeat visits: patient-doctor pairs with several completed appointments (hospital)
    Task(
        id="hospital_hard_2",
        difficulty="hard",
        schema_id="hospital",
        question="Find patients who had multiple appointments with the same doctor. Show the patient name, doctor name, number of appointments together, and the date range (earliest to latest appointment date). Only count completed appointments. Sort by number of appointments descending.",
        ground_truth_query="""
            SELECT
                p.name AS patient_name,
                d.name AS doctor_name,
                COUNT(a.id) AS visit_count,
                MIN(a.appointment_date) AS first_visit,
                MAX(a.appointment_date) AS last_visit
            FROM appointments a
            JOIN patients p ON a.patient_id = p.id
            JOIN doctors d ON a.doctor_id = d.id
            WHERE a.status = 'completed'
            GROUP BY p.id, p.name, d.id, d.name
            HAVING COUNT(a.id) > 1
            ORDER BY visit_count DESC
        """,
        expected_columns=["patient_name", "doctor_name", "visit_count", "first_visit", "last_visit"],
        description="Pairwise grouping with HAVING and MIN/MAX date range",
        hints=[
            "Join appointments with patients and doctors",
            "Group by patient-doctor pairs",
            "Use COUNT to find pairs with more than one appointment",
            "Use MIN/MAX for date range",
        ],
        max_steps=8,
        challenge_type="temporal_grouping",
    ),

    # Anti-join: products in stock but never ordered (ecommerce)
    Task(
        id="ecommerce_hard_2",
        difficulty="hard",
        schema_id="ecommerce",
        question="Find products that are currently in stock (stock > 0) but have never been ordered. Show the product name, category name, seller name, price, and stock count. Sort by stock count descending. This helps identify inventory that isn't moving.",
        ground_truth_query="""
            SELECT
                p.name AS product_name,
                c.name AS category_name,
                s.name AS seller_name,
                p.price,
                p.stock
            FROM products p
            JOIN categories c ON p.category_id = c.id
            JOIN sellers s ON p.seller_id = s.id
            LEFT JOIN order_items oi ON p.id = oi.product_id
            WHERE oi.id IS NULL AND p.stock > 0
            ORDER BY p.stock DESC
        """,
        expected_columns=["product_name", "category_name", "seller_name", "price", "stock"],
        description="LEFT JOIN with IS NULL to find non-matching rows",
        hints=[
            "Use LEFT JOIN between products and order_items",
            "A product with no orders will have NULL in the order_items columns",
            "Filter with WHERE oi.id IS NULL to find products never ordered",
            "Also filter for stock > 0",
        ],
        max_steps=8,
        challenge_type="anti_join",
    ),
]


# ---------------------------------------------------------------------------
# All tasks combined
# ---------------------------------------------------------------------------

ALL_TASKS_LIST = COMPANY_TASKS + HOSPITAL_TASKS + ECOMMERCE_TASKS + EXPERT_TASKS

ALL_TASKS = {
    "easy": [t for t in ALL_TASKS_LIST if t.difficulty == "easy"],
    "medium": [t for t in ALL_TASKS_LIST if t.difficulty == "medium"],
    "hard": [t for t in ALL_TASKS_LIST if t.difficulty == "hard"],
}

TASK_MAP: Dict[str, Task] = {t.id: t for t in ALL_TASKS_LIST}

