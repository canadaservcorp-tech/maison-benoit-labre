# La Maison Benoit Labre - Maintenance Management App

**[English](#english) | [Français](#français)**

---

## English

### Overview
Complete maintenance management system for La Maison Benoit Labre featuring:
- 36 apartments + common/service areas tracking
- Task management with costs and contractors
- Preventive maintenance scheduling with email reminders
- Admin and staff roles with JWT authentication
- Categories: MEP, Architecture, Civil, FFS, FAS

### Tech Stack
- **Frontend:** React 18 + Vite + Tailwind CSS + React Router
- **Backend:** Node.js + Express 5 + SQLite
- **Authentication:** JWT (JSON Web Tokens)
- **Email:** Nodemailer (optional)

---

## Quick Start

### 1. Install Dependencies
```bash
npm install
```

### 2. Setup Environment Variables
Create a `.env` file in the project root:
```env
PORT=4000
JWT_SECRET=your-secure-secret-key
BOOTSTRAP_KEY=your-bootstrap-key
CLIENT_URL=http://localhost:5173
DB_PATH=./data/maintenance.db
```

### 3. Start Backend Server
```bash
npm run dev:server
```
Server will run on `http://localhost:4000`

### 4. Start Frontend (in another terminal)
```bash
npm run dev
```
App will run on `http://localhost:5173`

---

## First Time Setup: Create Admin User

### Step 1: Bootstrap Your First Admin
Call the bootstrap endpoint with your chosen bootstrap key:

```bash
curl -X POST http://localhost:4000/api/auth/bootstrap \
  -H "Content-Type: application/json" \
  -H "x-bootstrap-key: your-bootstrap-key" \
  -d '{
    "name": "Admin User",
    "email": "admin@lmb.ca",
    "password": "SecurePassword123",
    "phone": "514-000-0000"
  }'
```

### Step 2: Login
Open `http://localhost:5173` and login with your admin credentials.

---

## Features

### For Admin Users
- ✅ Create and manage tasks
- ✅ Setup preventive maintenance schedules
- ✅ Add/edit contractors with ratings
- ✅ Create new staff users
- ✅ View all 36 apartments and areas
- ✅ Track costs and expenses

### For Staff Users
- ✅ View assigned tasks
- ✅ Update task status
- ✅ View preventive schedules
- ✅ Access contractor information
- ✅ View apartments/areas

---

## Email Reminders (Optional)

To enable email reminders 1 day before task due dates:

1. Add to `.env`:
```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password
SMTP_FROM=maintenance@lmb.local
REMINDER_CRON=0 8 * * *
```

2. For Gmail, create an [App Password](https://support.google.com/accounts/answer/185833)

---

## Automatic Database Backups (Recommended)

To keep data safe across deployments, enable daily backups to a persistent volume.

1. Mount persistent storage (Railway volume) and set:
```env
DB_PATH=/app/data/maintenance.db
```

2. Configure backup settings:
```env
DB_BACKUP_DIR=/app/data/backups
DB_BACKUP_CRON=0 3 * * *          # 3 AM daily (UTC on Railway)
DB_BACKUP_RETENTION_DAYS=14
```

Optional:
```env
DISABLE_DB_BACKUP=true
```

---

## Production Deployment

### Backend (Railway, Heroku, etc.)
1. Set environment variables in hosting platform
2. Ensure `DB_PATH` points to persistent storage
3. Set `CLIENT_URL` to your frontend URL
4. Deploy `server.js`

### Frontend (Netlify, Vercel, etc.)
1. Build the app: `npm run build`
2. Set `VITE_API_BASE_URL` to your backend URL
3. Deploy the `dist` folder

---

## Project Structure
```
lmb-maintenance-app/
├── server.js                 # Express backend
├── schema.sql               # Database schema
├── package.json             # Dependencies
├── vite.config.js           # Vite configuration
├── src/
│   ├── main.jsx            # React entry point
│   ├── App.jsx             # Main app with routing
│   ├── pages/              # Page components
│   │   ├── Login.jsx
│   │   ├── Dashboard.jsx
│   │   ├── Tasks.jsx
│   │   ├── Preventive.jsx
│   │   ├── Contractors.jsx
│   │   ├── Apartments.jsx
│   │   └── Users.jsx
│   └── components/         # Reusable components
│       └── Layout.jsx
└── data/
    └── maintenance.db      # SQLite database
```

---

## Support
For assistance, contact your system administrator or email: support@lmb.ca

---

# Français

## Aperçu
Système complet de gestion de maintenance pour La Maison Benoit Labre comprenant :
- Suivi de 36 appartements + espaces communs/service
- Gestion des tâches avec coûts et entrepreneurs
- Planification de maintenance préventive avec rappels par courriel
- Rôles administrateur et personnel avec authentification JWT
- Catégories : MEP, Architecture, Civil, FFS, FAS

### Technologies
- **Frontend :** React 18 + Vite + Tailwind CSS + React Router
- **Backend :** Node.js + Express 5 + SQLite
- **Authentification :** JWT (JSON Web Tokens)
- **Courriel :** Nodemailer (optionnel)

---

## Démarrage Rapide

### 1. Installer les Dépendances
```bash
npm install
```

### 2. Configurer les Variables d'Environnement
Créer un fichier `.env` à la racine du projet :
```env
PORT=4000
JWT_SECRET=votre-clé-secrète-sécurisée
BOOTSTRAP_KEY=votre-clé-bootstrap
CLIENT_URL=http://localhost:5173
DB_PATH=./data/maintenance.db
```

### 3. Démarrer le Serveur Backend
```bash
npm run dev:server
```
Le serveur sera disponible sur `http://localhost:4000`

### 4. Démarrer le Frontend (dans un autre terminal)
```bash
npm run dev
```
L'application sera disponible sur `http://localhost:5173`

---

## Configuration Initiale : Créer un Utilisateur Admin

### Étape 1 : Amorcer Votre Premier Admin
Appelez l'endpoint bootstrap avec votre clé bootstrap :

```bash
curl -X POST http://localhost:4000/api/auth/bootstrap \
  -H "Content-Type: application/json" \
  -H "x-bootstrap-key: votre-clé-bootstrap" \
  -d '{
    "name": "Utilisateur Admin",
    "email": "admin@lmb.ca",
    "password": "MotDePasseSecurise123",
    "phone": "514-000-0000"
  }'
```

### Étape 2 : Se Connecter
Ouvrir `http://localhost:5173` et se connecter avec vos identifiants admin.

---

## Fonctionnalités

### Pour les Administrateurs
- ✅ Créer et gérer les tâches
- ✅ Configurer les planifications de maintenance préventive
- ✅ Ajouter/modifier les entrepreneurs avec évaluations
- ✅ Créer de nouveaux utilisateurs du personnel
- ✅ Voir les 36 appartements et espaces
- ✅ Suivre les coûts et dépenses

### Pour le Personnel
- ✅ Voir les tâches assignées
- ✅ Mettre à jour le statut des tâches
- ✅ Voir les planifications préventives
- ✅ Accéder aux informations des entrepreneurs
- ✅ Voir les appartements/espaces

---

## Rappels par Courriel (Optionnel)

Pour activer les rappels par courriel 1 jour avant l'échéance des tâches :

1. Ajouter au `.env` :
```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=votre-courriel@gmail.com
SMTP_PASS=votre-mot-de-passe-application
SMTP_FROM=maintenance@lmb.local
REMINDER_CRON=0 8 * * *
```

2. Pour Gmail, créer un [Mot de passe d'application](https://support.google.com/accounts/answer/185833)

---

## Déploiement en Production

### Backend (Railway, Heroku, etc.)
1. Configurer les variables d'environnement sur la plateforme d'hébergement
2. S'assurer que `DB_PATH` pointe vers un stockage persistant
3. Définir `CLIENT_URL` vers l'URL de votre frontend
4. Déployer `server.js`

### Frontend (Netlify, Vercel, etc.)
1. Compiler l'application : `npm run build`
2. Définir `VITE_API_BASE_URL` vers l'URL de votre backend
3. Déployer le dossier `dist`

---

## Support
Pour assistance, contactez votre administrateur système ou courriel : support@lmb.ca
