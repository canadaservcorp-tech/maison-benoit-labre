import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import dotenv from 'dotenv';
import Database from 'better-sqlite3';
import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import nodemailer from 'nodemailer';
import cron from 'node-cron';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.PORT || 4000;
const JWT_SECRET = process.env.JWT_SECRET || 'change-me-in-production';
const BOOTSTRAP_KEY = process.env.BOOTSTRAP_KEY || 'bootstrap-secret-key';

// Database setup
const dbPath = process.env.DB_PATH || path.join(__dirname, 'data', 'maintenance.db');
const dbDir = path.dirname(dbPath);
if (!fs.existsSync(dbDir)) {
  fs.mkdirSync(dbDir, { recursive: true });
}

const db = new Database(dbPath);

// Initialize database with schema
const schemaPath = path.join(__dirname, 'schema.sql');
if (fs.existsSync(schemaPath)) {
  const schema = fs.readFileSync(schemaPath, 'utf8');
  db.exec(schema);
  console.log('✅ Database schema initialized');
}

// Simple migrations for new columns
const ensureColumn = (table, column, definition) => {
  const info = db.prepare(`PRAGMA table_info(${table})`).all();
  const exists = info.some(col => col.name === column);
  if (!exists) {
    db.exec(`ALTER TABLE ${table} ADD COLUMN ${column} ${definition}`);
  }
};

// Ensure optional columns exist
try {
  ensureColumn('tasks', 'area_id', 'INTEGER');
  ensureColumn('tasks', 'hours_spent', 'REAL');
  ensureColumn('areas', 'category', 'TEXT');
  ensureColumn('assets', 'category', 'TEXT');
  ensureColumn('assets', 'area_type', "TEXT");
  ensureColumn('assets', 'serial_number', 'TEXT');
  ensureColumn('assets', 'interval_days', 'INTEGER');
  ensureColumn('assets', 'next_due_date', 'DATE');
} catch (error) {
  console.warn('Migration warning:', error.message);
}

// Rename Lobby -> Drop-in if present
try {
  db.prepare("UPDATE areas SET name = 'Drop-in' WHERE name = 'Lobby'").run();
} catch (error) {
  // ignore if table not available yet
}

// Email transporter (optional)
let transporter = null;
if (process.env.SMTP_HOST) {
  transporter = nodemailer.createTransport({
    host: process.env.SMTP_HOST,
    port: parseInt(process.env.SMTP_PORT || '587'),
    secure: false,
    auth: {
      user: process.env.SMTP_USER,
      pass: process.env.SMTP_PASS,
    },
  });
  console.log('✅ Email transporter configured');
}

// Middleware
app.use(helmet());
app.use(cors({
  origin: process.env.CLIENT_URL || process.env.CLIENT_URLS?.split(',') || 'http://localhost:5173',
  credentials: true,
}));
app.use(express.json());

// Auth middleware
const authMiddleware = (req, res, next) => {
  const token = req.headers.authorization?.split(' ')[1];
  if (!token) {
    return res.status(401).json({ error: 'Authentication required' });
  }
  try {
    const decoded = jwt.verify(token, JWT_SECRET);
    req.user = decoded;
    next();
  } catch (error) {
    return res.status(401).json({ error: 'Invalid token' });
  }
};

// Admin-only middleware
const adminOnly = (req, res, next) => {
  if (req.user.role !== 'admin') {
    return res.status(403).json({ error: 'Admin access required' });
  }
  next();
};

// ============ AUTH ROUTES ============

// Bootstrap first admin
app.post('/api/auth/bootstrap', (req, res) => {
  const bootstrapKey = req.headers['x-bootstrap-key'];
  if (bootstrapKey !== BOOTSTRAP_KEY) {
    return res.status(403).json({ error: 'Invalid bootstrap key' });
  }

  const { name, email, password, phone } = req.body;
  if (!name || !email || !password) {
    return res.status(400).json({ error: 'Name, email, and password required' });
  }

  try {
    const hashedPassword = bcrypt.hashSync(password, 10);
    const stmt = db.prepare('INSERT INTO users (name, email, password, phone, role) VALUES (?, ?, ?, ?, ?)');
    const result = stmt.run(name, email, hashedPassword, phone || null, 'admin');
    
    res.json({ message: 'Admin user created', userId: result.lastInsertRowid });
  } catch (error) {
    if (error.message.includes('UNIQUE')) {
      return res.status(400).json({ error: 'Email already exists' });
    }
    res.status(500).json({ error: error.message });
  }
});

// Reset or create user password with bootstrap key
app.post('/api/auth/reset-user', (req, res) => {
  const bootstrapKey = req.headers['x-bootstrap-key'];
  if (bootstrapKey !== BOOTSTRAP_KEY) {
    return res.status(403).json({ error: 'Invalid bootstrap key' });
  }

  const { email, password, name, phone, role } = req.body;
  if (!email || !password) {
    return res.status(400).json({ error: 'Email and password required' });
  }

  try {
    const hashedPassword = bcrypt.hashSync(password, 10);
    const existing = db.prepare('SELECT id FROM users WHERE email = ?').get(email);
    if (existing) {
      const stmt = db.prepare(
        'UPDATE users SET password = ?, updated_at = CURRENT_TIMESTAMP WHERE email = ?'
      );
      stmt.run(hashedPassword, email);
      return res.json({ message: 'Password updated' });
    }

    const stmt = db.prepare('INSERT INTO users (name, email, password, phone, role) VALUES (?, ?, ?, ?, ?)');
    const result = stmt.run(name || email, email, hashedPassword, phone || null, role || 'staff');
    return res.json({ message: 'User created', userId: result.lastInsertRowid });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Login
app.post('/api/auth/login', (req, res) => {
  const { email, password } = req.body;
  if (!email || !password) {
    return res.status(400).json({ error: 'Email and password required' });
  }

  try {
    const user = db.prepare('SELECT * FROM users WHERE email = ?').get(email);
    if (!user || !bcrypt.compareSync(password, user.password)) {
      return res.status(401).json({ error: 'Invalid credentials' });
    }

    const token = jwt.sign(
      { id: user.id, email: user.email, role: user.role },
      JWT_SECRET,
      { expiresIn: '7d' }
    );

    res.json({
      token,
      user: {
        id: user.id,
        name: user.name,
        email: user.email,
        role: user.role,
        phone: user.phone,
      },
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Get current user
app.get('/api/auth/me', authMiddleware, (req, res) => {
  try {
    const user = db.prepare('SELECT id, name, email, phone, role FROM users WHERE id = ?').get(req.user.id);
    if (!user) {
      return res.status(404).json({ error: 'User not found' });
    }
    res.json(user);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Alias for frontend: /api/users/me
app.get('/api/users/me', authMiddleware, (req, res) => {
  try {
    const user = db.prepare('SELECT id, name, email, phone, role FROM users WHERE id = ?').get(req.user.id);
    if (!user) {
      return res.status(404).json({ error: 'User not found' });
    }
    res.json({ user });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// ============ USER ROUTES ============

// List all users (admin only)
app.get('/api/users', authMiddleware, adminOnly, (req, res) => {
  try {
    const users = db.prepare('SELECT id, name, email, phone, role, created_at FROM users ORDER BY name').all();
    res.json({ users });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Create user (admin only)
app.post('/api/users', authMiddleware, adminOnly, (req, res) => {
  const { name, email, password, phone, role } = req.body;
  if (!name || !email || !password) {
    return res.status(400).json({ error: 'Name, email, and password required' });
  }

  try {
    const hashedPassword = bcrypt.hashSync(password, 10);
    const stmt = db.prepare('INSERT INTO users (name, email, password, phone, role) VALUES (?, ?, ?, ?, ?)');
    const result = stmt.run(name, email, hashedPassword, phone || null, role || 'staff');
    res.json({ message: 'User created', userId: result.lastInsertRowid });
  } catch (error) {
    if (error.message.includes('UNIQUE')) {
      return res.status(400).json({ error: 'Email already exists' });
    }
    res.status(500).json({ error: error.message });
  }
});

// Reset user password (admin only)
app.post('/api/users/reset-password', authMiddleware, adminOnly, (req, res) => {
  const { email, password } = req.body;
  if (!email || !password) {
    return res.status(400).json({ error: 'Email and password required' });
  }

  try {
    const hashedPassword = bcrypt.hashSync(password, 10);
    const stmt = db.prepare(
      'UPDATE users SET password = ?, updated_at = CURRENT_TIMESTAMP WHERE email = ?'
    );
    const result = stmt.run(hashedPassword, email);
    if (result.changes === 0) {
      return res.status(404).json({ error: 'User not found' });
    }
    res.json({ message: 'Password updated' });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// ============ APARTMENT ROUTES ============

app.get('/api/apartments', authMiddleware, (req, res) => {
  try {
    const apartments = db.prepare('SELECT * FROM apartments ORDER BY area_type, floor, unit_number').all();
    const mapped = apartments.map((apt) => ({
      ...apt,
      label: apt.unit_number,
    }));
    res.json({ apartments: mapped });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Reset apartments to standard list (admin only)
app.post('/api/apartments/reset', authMiddleware, adminOnly, (req, res) => {
  try {
    const units = [];
    for (const floor of [2, 3, 4]) {
      for (let num = 1; num <= 12; num += 1) {
        const unit = `${floor}${String(num).padStart(2, '0')}`;
        units.push([unit, floor, 'apartment', `Apartment ${unit}`]);
      }
    }

    const insert = db.prepare(`
      INSERT OR IGNORE INTO apartments (unit_number, floor, area_type, description)
      VALUES (?, ?, ?, ?)
    `);
    const tx = db.transaction(() => {
      db.prepare('DELETE FROM apartments').run();
      units.forEach(row => insert.run(...row));
    });
    tx();
    res.json({ message: 'Apartments reset', count: units.length });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// ============ CATEGORY ROUTES ============

app.get('/api/categories', authMiddleware, (req, res) => {
  try {
    const categories = db.prepare('SELECT * FROM categories ORDER BY name').all();
    res.json({ categories });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// ============ AREA ROUTES ============
app.get('/api/areas', authMiddleware, (req, res) => {
  try {
    const areas = db.prepare('SELECT * FROM areas ORDER BY name').all();
    res.json({ areas });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/areas', authMiddleware, adminOnly, (req, res) => {
  const { name, type, floor, category, notes } = req.body;
  if (!name || !type) {
    return res.status(400).json({ error: 'Name and type required' });
  }
  try {
    const stmt = db.prepare(
      'INSERT INTO areas (name, type, floor, category, notes) VALUES (?, ?, ?, ?, ?)'
    );
    const result = stmt.run(name, type, floor || null, category || null, notes || null);
    res.json({ message: 'Area created', areaId: result.lastInsertRowid });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.put('/api/areas/:id', authMiddleware, adminOnly, (req, res) => {
  const { name, type, floor, category, notes } = req.body;
  try {
    const stmt = db.prepare(
      'UPDATE areas SET name = ?, type = ?, floor = ?, category = ?, notes = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?'
    );
    stmt.run(name, type, floor || null, category || null, notes || null, req.params.id);
    res.json({ message: 'Area updated' });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// ============ CONTRACTOR ROUTES ============

app.get('/api/contractors', authMiddleware, (req, res) => {
  try {
    const contractors = db.prepare('SELECT * FROM contractors ORDER BY name').all();
    res.json({ contractors });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/contractors', authMiddleware, adminOnly, (req, res) => {
  const { name, company, email, phone, specialty, specialties, rating, notes } = req.body;
  if (!name || !phone) {
    return res.status(400).json({ error: 'Name and phone required' });
  }

  try {
    const stmt = db.prepare(
      'INSERT INTO contractors (name, company, email, phone, specialty, rating, notes) VALUES (?, ?, ?, ?, ?, ?, ?)'
    );
    const result = stmt.run(
      name,
      company || null,
      email || null,
      phone,
      specialty || specialties || null,
      rating || 0,
      notes || null
    );
    res.json({ message: 'Contractor created', contractorId: result.lastInsertRowid });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.put('/api/contractors/:id', authMiddleware, adminOnly, (req, res) => {
  const { name, company, email, phone, specialty, specialties, rating, notes } = req.body;
  
  try {
    const stmt = db.prepare(
      'UPDATE contractors SET name = ?, company = ?, email = ?, phone = ?, specialty = ?, rating = ?, notes = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?'
    );
    stmt.run(name, company, email, phone, specialty || specialties || null, rating, notes, req.params.id);
    res.json({ message: 'Contractor updated' });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Contractor reviews
app.get('/api/contractors/:id/reviews', authMiddleware, (req, res) => {
  try {
    const reviews = db.prepare(`
      SELECT r.*, u.name as reviewer_name
      FROM contractor_reviews r
      LEFT JOIN users u ON r.reviewer_id = u.id
      WHERE r.contractor_id = ?
      ORDER BY r.created_at DESC
    `).all(req.params.id);
    res.json({ reviews });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/contractors/:id/reviews', authMiddleware, adminOnly, (req, res) => {
  const { rating, comment } = req.body;
  if (!rating) {
    return res.status(400).json({ error: 'Rating required' });
  }
  try {
    const stmt = db.prepare(
      'INSERT INTO contractor_reviews (contractor_id, reviewer_id, rating, comment) VALUES (?, ?, ?, ?)'
    );
    const result = stmt.run(req.params.id, req.user.id, rating, comment || null);
    res.json({ message: 'Review added', reviewId: result.lastInsertRowid });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// ============ ASSET ROUTES ============
app.get('/api/assets', authMiddleware, (req, res) => {
  try {
    const assets = db.prepare(`
      SELECT 
        a.*,
        c.name as contractor_name,
        ap.unit_number as apartment_label,
        ar.name as area_name
      FROM assets a
      LEFT JOIN contractors c ON a.contractor_id = c.id
      LEFT JOIN apartments ap ON a.apartment_id = ap.id
      LEFT JOIN areas ar ON a.area_id = ar.id
      ORDER BY a.name
    `).all();
    res.json({ assets });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/assets', authMiddleware, adminOnly, (req, res) => {
  const { name, category, area_type, area_id, apartment_id, serial_number, next_due_date, interval_days, notes } = req.body;
  if (!name || !category || !area_type) {
    return res.status(400).json({ error: 'Name, category, and area_type required' });
  }
  try {
    const stmt = db.prepare(`
      INSERT INTO assets (
        name, category, area_type, serial_number, area_id, apartment_id,
        interval_days, next_due_date, status, notes, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    `);
    const result = stmt.run(
      name,
      category,
      area_type,
      serial_number || null,
      area_id || null,
      apartment_id || null,
      interval_days || null,
      next_due_date || null,
      notes || null
    );
    res.json({ message: 'Asset created', assetId: result.lastInsertRowid });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.put('/api/assets/:id', authMiddleware, adminOnly, (req, res) => {
  const { name, category, area_type, serial_number, area_id, apartment_id, interval_days, next_due_date, status, notes } = req.body;
  try {
    const stmt = db.prepare(`
      UPDATE assets SET
        name = ?, category = ?, area_type = ?, serial_number = ?, area_id = ?, apartment_id = ?,
        interval_days = ?, next_due_date = ?, status = ?, notes = ?,
        updated_at = CURRENT_TIMESTAMP
      WHERE id = ?
    `);
    stmt.run(
      name,
      category,
      area_type,
      serial_number || null,
      area_id || null,
      apartment_id || null,
      interval_days || null,
      next_due_date || null,
      status || 'active',
      notes || null,
      req.params.id
    );
    res.json({ message: 'Asset updated' });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// ============ EXPENSE ROUTES ============
app.get('/api/expenses', authMiddleware, (req, res) => {
  try {
    const expenses = db.prepare(`
      SELECT 
        e.*,
        ap.unit_number as apartment_label,
        ar.name as area_name,
        c.name as contractor_name,
        u.name as created_by_name
      FROM expenses e
      LEFT JOIN apartments ap ON e.apartment_id = ap.id
      LEFT JOIN areas ar ON e.area_id = ar.id
      LEFT JOIN contractors c ON e.contractor_id = c.id
      LEFT JOIN users u ON e.created_by = u.id
      ORDER BY e.spent_on DESC, e.created_at DESC
    `).all();
    res.json({ expenses });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/expenses', authMiddleware, adminOnly, (req, res) => {
  const { apartment_id, area_id, contractor_id, amount, description, spent_on } = req.body;
  if (!amount) {
    return res.status(400).json({ error: 'Amount required' });
  }
  try {
    const stmt = db.prepare(`
      INSERT INTO expenses (apartment_id, area_id, contractor_id, amount, description, spent_on, created_by)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `);
    const result = stmt.run(
      apartment_id || null,
      area_id || null,
      contractor_id || null,
      amount,
      description || null,
      spent_on || null,
      req.user.id
    );
    res.json({ message: 'Expense added', expenseId: result.lastInsertRowid });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.get('/api/expenses/summary', authMiddleware, (req, res) => {
  try {
    const total = db.prepare('SELECT SUM(amount) as total FROM expenses').get();
    const apartmentTotal = db.prepare('SELECT SUM(amount) as total FROM expenses WHERE apartment_id IS NOT NULL').get();
    const commonTotal = db.prepare(`
      SELECT SUM(e.amount) as total
      FROM expenses e
      JOIN areas ar ON e.area_id = ar.id
      WHERE ar.type = 'common'
    `).get();
    const serviceTotal = db.prepare(`
      SELECT SUM(e.amount) as total
      FROM expenses e
      JOIN areas ar ON e.area_id = ar.id
      WHERE ar.type = 'service'
    `).get();

    const byApartment = db.prepare(`
      SELECT ap.unit_number as label, SUM(e.amount) as total
      FROM expenses e
      JOIN apartments ap ON e.apartment_id = ap.id
      GROUP BY ap.unit_number
      ORDER BY ap.unit_number
    `).all();

    const byArea = db.prepare(`
      SELECT ar.name as name, ar.type as type, SUM(e.amount) as total
      FROM expenses e
      JOIN areas ar ON e.area_id = ar.id
      GROUP BY ar.name, ar.type
      ORDER BY ar.name
    `).all();

    res.json({
      total_building: total.total || 0,
      total_apartments: apartmentTotal.total || 0,
      total_common_areas: commonTotal.total || 0,
      total_service_areas: serviceTotal.total || 0,
      by_apartment: byApartment,
      by_area: byArea,
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// ============ TASK ROUTES ============

app.get('/api/tasks', authMiddleware, (req, res) => {
  try {
    const tasks = db.prepare(`
      SELECT 
        t.*,
        c.name as category_name,
        a.unit_number as apartment_label,
        u.name as assigned_name,
        ct.name as contractor_name,
        cr.name as created_by_name,
        ar.name as area_name
      FROM tasks t
      LEFT JOIN categories c ON t.category_id = c.id
      LEFT JOIN apartments a ON t.apartment_id = a.id
      LEFT JOIN users u ON t.assigned_to = u.id
      LEFT JOIN contractors ct ON t.contractor_id = ct.id
      LEFT JOIN users cr ON t.created_by = cr.id
      LEFT JOIN areas ar ON t.area_id = ar.id
      ORDER BY t.due_date DESC, t.priority DESC
    `).all();
    res.json({ tasks });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/tasks', authMiddleware, (req, res) => {
  const {
    title, description, category_id, apartment_id, area_id, assigned_to,
    contractor_id, status, priority, task_type, due_date,
    estimated_cost, actual_cost, cost_amount, hours_spent, remarks
  } = req.body;

  if (!title) {
    return res.status(400).json({ error: 'Title required' });
  }

  try {
    const stmt = db.prepare(`
      INSERT INTO tasks (
        title, description, category_id, apartment_id, area_id, assigned_to,
        contractor_id, status, priority, task_type, due_date,
        estimated_cost, actual_cost, hours_spent, remarks, created_by
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);
    const actual = actual_cost ?? cost_amount ?? 0;
    const result = stmt.run(
      title, description || null, category_id || null, apartment_id || null,
      area_id || null, assigned_to || null, contractor_id || null, status || 'pending',
      priority || 'medium', task_type || 'reactive', due_date || null,
      estimated_cost || 0, actual, hours_spent || 0, remarks || null, req.user.id
    );
    res.json({ message: 'Task created', taskId: result.lastInsertRowid });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.put('/api/tasks/:id', authMiddleware, (req, res) => {
  const {
    title, description, category_id, apartment_id, area_id, assigned_to,
    contractor_id, status, priority, due_date, completed_date,
    estimated_cost, actual_cost, cost_amount, hours_spent, remarks
  } = req.body;

  try {
    const actual = actual_cost ?? cost_amount ?? 0;
    const stmt = db.prepare(`
      UPDATE tasks SET
        title = ?, description = ?, category_id = ?, apartment_id = ?,
        area_id = ?, assigned_to = ?, contractor_id = ?, status = ?, priority = ?,
        due_date = ?, completed_date = ?, estimated_cost = ?,
        actual_cost = ?, hours_spent = ?, remarks = ?, updated_at = CURRENT_TIMESTAMP
      WHERE id = ?
    `);
    stmt.run(
      title, description, category_id, apartment_id, area_id, assigned_to,
      contractor_id, status, priority, due_date, completed_date,
      estimated_cost, actual, hours_spent || 0, remarks, req.params.id
    );
    res.json({ message: 'Task updated' });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// ============ PREVENTIVE SCHEDULES ============

app.get('/api/preventive', authMiddleware, (req, res) => {
  try {
    const schedules = db.prepare(`
      SELECT 
        p.*,
        c.name as category_name,
        a.unit_number as apartment_unit,
        u.name as assigned_to_name
      FROM preventive_schedules p
      LEFT JOIN categories c ON p.category_id = c.id
      LEFT JOIN apartments a ON p.apartment_id = a.id
      LEFT JOIN users u ON p.assigned_to = u.id
      WHERE p.active = 1
      ORDER BY p.next_due_date
    `).all();
    res.json(schedules);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/preventive', authMiddleware, (req, res) => {
  const {
    title, description, category_id, apartment_id,
    frequency, next_due_date, assigned_to
  } = req.body;

  if (!title || !frequency || !next_due_date) {
    return res.status(400).json({ error: 'Title, frequency, and next_due_date required' });
  }

  try {
    const stmt = db.prepare(`
      INSERT INTO preventive_schedules (
        title, description, category_id, apartment_id,
        frequency, next_due_date, assigned_to
      ) VALUES (?, ?, ?, ?, ?, ?, ?)
    `);
    const result = stmt.run(
      title, description || null, category_id || null, apartment_id || null,
      frequency, next_due_date, assigned_to || null
    );
    res.json({ message: 'Preventive schedule created', scheduleId: result.lastInsertRowid });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// ============ EMAIL REMINDERS (CRON JOB) ============

if (transporter) {
  const cronSchedule = process.env.REMINDER_CRON || '0 8 * * *'; // Default: 8 AM daily
  
  cron.schedule(cronSchedule, async () => {
    console.log('🔔 Running maintenance reminder check...');
    
    try {
      // Find tasks due tomorrow
      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      const tomorrowStr = tomorrow.toISOString().split('T')[0];
      
      const tasks = db.prepare(`
        SELECT 
          t.*,
          u.email as assignee_email,
          u.name as assignee_name,
          a.unit_number
        FROM tasks t
        LEFT JOIN users u ON t.assigned_to = u.id
        LEFT JOIN apartments a ON t.apartment_id = a.id
        WHERE t.due_date = ? AND t.status != 'completed' AND u.email IS NOT NULL
      `).all(tomorrowStr);
      
      for (const task of tasks) {
        await transporter.sendMail({
          from: process.env.SMTP_FROM || 'maintenance@lmb.local',
          to: task.assignee_email,
          subject: `Reminder: Task due tomorrow - ${task.title}`,
          html: `
            <h2>Maintenance Task Reminder</h2>
            <p>Hello ${task.assignee_name},</p>
            <p>This is a reminder that the following task is due <strong>tomorrow</strong>:</p>
            <ul>
              <li><strong>Title:</strong> ${task.title}</li>
              <li><strong>Unit:</strong> ${task.unit_number || 'N/A'}</li>
              <li><strong>Priority:</strong> ${task.priority}</li>
              <li><strong>Due Date:</strong> ${task.due_date}</li>
            </ul>
            <p>${task.description || ''}</p>
            <p>Please log in to the maintenance app to view details.</p>
            <hr>
            <p><small>La Maison Benoit Labre Maintenance System</small></p>
          `,
        });
      }
      
      console.log(`✅ Sent ${tasks.length} reminder emails`);
    } catch (error) {
      console.error('❌ Error sending reminders:', error);
    }
  });
  
  console.log(`✅ Reminder cron job scheduled: ${cronSchedule}`);
}

// Overview summary
app.get('/api/overview', authMiddleware, adminOnly, (req, res) => {
  try {
    const totals = db.prepare(`
      SELECT
        SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as open_count,
        SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) as in_progress_count,
        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_count,
        SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) as blocked_count
      FROM tasks
    `).get();
    const cost = db.prepare('SELECT SUM(amount) as total FROM expenses').get();
    const apartmentCost = db.prepare('SELECT SUM(amount) as total FROM expenses WHERE apartment_id IS NOT NULL').get();
    const commonCost = db.prepare(`
      SELECT SUM(e.amount) as total
      FROM expenses e
      JOIN areas ar ON e.area_id = ar.id
      WHERE ar.type = 'common'
    `).get();
    res.json({
      totals,
      total_cost: cost.total || 0,
      apartments_cost: apartmentCost.total || 0,
      common_areas_cost: commonCost.total || 0,
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Health check
app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Start server
app.listen(PORT, () => {
  console.log(`🚀 LMB Maintenance API running on http://localhost:${PORT}`);
});
