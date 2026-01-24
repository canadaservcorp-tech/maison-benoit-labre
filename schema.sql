-- La Maison Benoit Labre Maintenance Database Schema

-- Users table (admin and staff)
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  password TEXT NOT NULL,
  phone TEXT,
  role TEXT DEFAULT 'staff' CHECK(role IN ('admin', 'staff')),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Apartments (36 units)
CREATE TABLE IF NOT EXISTS apartments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  unit_number TEXT UNIQUE NOT NULL,
  floor INTEGER,
  area_type TEXT DEFAULT 'apartment' CHECK(area_type IN ('apartment', 'common', 'service')),
  description TEXT,
  notes TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Areas (common/service)
CREATE TABLE IF NOT EXISTS areas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  type TEXT NOT NULL CHECK(type IN ('common', 'service')),
  floor INTEGER,
  category TEXT,
  notes TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Categories for maintenance
CREATE TABLE IF NOT EXISTS categories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL,
  code TEXT UNIQUE NOT NULL,
  description TEXT
);

-- Contractors
CREATE TABLE IF NOT EXISTS contractors (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  company TEXT,
  email TEXT,
  phone TEXT NOT NULL,
  specialty TEXT,
  rating REAL DEFAULT 0 CHECK(rating >= 0 AND rating <= 5),
  notes TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Contractor reviews
CREATE TABLE IF NOT EXISTS contractor_reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  contractor_id INTEGER NOT NULL,
  reviewer_id INTEGER,
  rating REAL DEFAULT 0 CHECK(rating >= 0 AND rating <= 5),
  comment TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (contractor_id) REFERENCES contractors(id),
  FOREIGN KEY (reviewer_id) REFERENCES users(id)
);

-- Assets / equipment
CREATE TABLE IF NOT EXISTS assets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  category TEXT,
  area_type TEXT CHECK(area_type IN ('area', 'apartment')),
  serial_number TEXT,
  area_id INTEGER,
  apartment_id INTEGER,
  contractor_id INTEGER,
  interval_days INTEGER,
  next_due_date DATE,
  status TEXT DEFAULT 'active',
  notes TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (area_id) REFERENCES areas(id),
  FOREIGN KEY (apartment_id) REFERENCES apartments(id),
  FOREIGN KEY (contractor_id) REFERENCES contractors(id)
);

-- Maintenance expenses
CREATE TABLE IF NOT EXISTS expenses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  apartment_id INTEGER,
  area_id INTEGER,
  contractor_id INTEGER,
  amount REAL NOT NULL,
  description TEXT,
  spent_on DATE,
  created_by INTEGER,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (apartment_id) REFERENCES apartments(id),
  FOREIGN KEY (area_id) REFERENCES areas(id),
  FOREIGN KEY (contractor_id) REFERENCES contractors(id),
  FOREIGN KEY (created_by) REFERENCES users(id)
);

-- Tasks
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  description TEXT,
  category_id INTEGER,
  apartment_id INTEGER,
  assigned_to INTEGER,
  contractor_id INTEGER,
  status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'in_progress', 'completed', 'cancelled')),
  priority TEXT DEFAULT 'medium' CHECK(priority IN ('low', 'medium', 'high', 'urgent')),
  task_type TEXT DEFAULT 'reactive' CHECK(task_type IN ('reactive', 'preventive')),
  due_date DATE,
  completed_date DATE,
  estimated_cost REAL DEFAULT 0,
  actual_cost REAL DEFAULT 0,
  hours_spent REAL DEFAULT 0,
  remarks TEXT,
  created_by INTEGER,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (category_id) REFERENCES categories(id),
  FOREIGN KEY (apartment_id) REFERENCES apartments(id),
  FOREIGN KEY (assigned_to) REFERENCES users(id),
  FOREIGN KEY (contractor_id) REFERENCES contractors(id),
  FOREIGN KEY (created_by) REFERENCES users(id)
);

-- Task remarks
CREATE TABLE IF NOT EXISTS task_remarks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL,
  author_id INTEGER,
  message TEXT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (task_id) REFERENCES tasks(id),
  FOREIGN KEY (author_id) REFERENCES users(id)
);

-- Preventive maintenance schedules
CREATE TABLE IF NOT EXISTS preventive_schedules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  description TEXT,
  category_id INTEGER,
  apartment_id INTEGER,
  frequency TEXT NOT NULL CHECK(frequency IN ('daily', 'weekly', 'monthly', 'quarterly', 'yearly')),
  next_due_date DATE NOT NULL,
  last_completed_date DATE,
  assigned_to INTEGER,
  active INTEGER DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (category_id) REFERENCES categories(id),
  FOREIGN KEY (apartment_id) REFERENCES apartments(id),
  FOREIGN KEY (assigned_to) REFERENCES users(id)
);

-- Task history/logs
CREATE TABLE IF NOT EXISTS task_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL,
  user_id INTEGER,
  action TEXT NOT NULL,
  details TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (task_id) REFERENCES tasks(id),
  FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Insert default categories
INSERT OR IGNORE INTO categories (name, code, description) VALUES
  ('MEP (Mechanical, Electrical, Plumbing)', 'MEP', 'Heating, cooling, electrical, plumbing systems'),
  ('Architecture', 'ARCH', 'Structural, walls, doors, windows'),
  ('Civil', 'CIVIL', 'Foundation, drainage, exterior'),
  ('FFS (Furniture, Fixtures, Signage)', 'FFS', 'Fixed furniture and fixtures'),
  ('FAS (Furniture and Services)', 'FAS', 'Movable furniture and services');

-- Insert 36 apartments (floors 2-4, units 201-212)
INSERT OR IGNORE INTO apartments (unit_number, floor, area_type, description) VALUES
  ('201', 2, 'apartment', 'Apartment 201'),
  ('202', 2, 'apartment', 'Apartment 202'),
  ('203', 2, 'apartment', 'Apartment 203'),
  ('204', 2, 'apartment', 'Apartment 204'),
  ('205', 2, 'apartment', 'Apartment 205'),
  ('206', 2, 'apartment', 'Apartment 206'),
  ('207', 2, 'apartment', 'Apartment 207'),
  ('208', 2, 'apartment', 'Apartment 208'),
  ('209', 2, 'apartment', 'Apartment 209'),
  ('210', 2, 'apartment', 'Apartment 210'),
  ('211', 2, 'apartment', 'Apartment 211'),
  ('212', 2, 'apartment', 'Apartment 212'),
  ('301', 3, 'apartment', 'Apartment 301'),
  ('302', 3, 'apartment', 'Apartment 302'),
  ('303', 3, 'apartment', 'Apartment 303'),
  ('304', 3, 'apartment', 'Apartment 304'),
  ('305', 3, 'apartment', 'Apartment 305'),
  ('306', 3, 'apartment', 'Apartment 306'),
  ('307', 3, 'apartment', 'Apartment 307'),
  ('308', 3, 'apartment', 'Apartment 308'),
  ('309', 3, 'apartment', 'Apartment 309'),
  ('310', 3, 'apartment', 'Apartment 310'),
  ('311', 3, 'apartment', 'Apartment 311'),
  ('312', 3, 'apartment', 'Apartment 312'),
  ('401', 4, 'apartment', 'Apartment 401'),
  ('402', 4, 'apartment', 'Apartment 402'),
  ('403', 4, 'apartment', 'Apartment 403'),
  ('404', 4, 'apartment', 'Apartment 404'),
  ('405', 4, 'apartment', 'Apartment 405'),
  ('406', 4, 'apartment', 'Apartment 406'),
  ('407', 4, 'apartment', 'Apartment 407'),
  ('408', 4, 'apartment', 'Apartment 408'),
  ('409', 4, 'apartment', 'Apartment 409'),
  ('410', 4, 'apartment', 'Apartment 410'),
  ('411', 4, 'apartment', 'Apartment 411'),
  ('412', 4, 'apartment', 'Apartment 412');

-- Insert default areas
INSERT OR IGNORE INTO areas (name, type, floor, notes) VALUES
  ('Drop-in', 'common', 1, 'Main drop-in area'),
  ('Corridors', 'common', NULL, 'All corridors'),
  ('Mechanical Room', 'service', 1, NULL),
  ('Electrical Room', 'service', 1, NULL),
  ('Elevators', 'service', NULL, NULL),
  ('Stairwells', 'common', NULL, NULL);

-- Insert common and service areas
INSERT OR IGNORE INTO apartments (unit_number, floor, area_type, description) VALUES
  ('LOBBY', 1, 'common', 'Main lobby entrance'),
  ('CORRIDOR-1', 1, 'common', 'First floor corridor'),
  ('CORRIDOR-2', 2, 'common', 'Second floor corridor'),
  ('CORRIDOR-3', 3, 'common', 'Third floor corridor'),
  ('CORRIDOR-4', 4, 'common', 'Fourth floor corridor'),
  ('CORRIDOR-5', 5, 'common', 'Fifth floor corridor'),
  ('CORRIDOR-6', 6, 'common', 'Sixth floor corridor'),
  ('BASEMENT', 0, 'service', 'Basement storage and mechanical'),
  ('LAUNDRY', 0, 'service', 'Laundry room'),
  ('BOILER-ROOM', 0, 'service', 'Boiler and heating system'),
  ('ROOF', 7, 'service', 'Roof and rooftop equipment'),
  ('PARKING', 0, 'common', 'Parking area'),
  ('GARDEN', 0, 'common', 'Garden and exterior grounds');
