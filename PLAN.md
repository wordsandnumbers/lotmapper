# Parking Lot Mapping Tool - Implementation Plan

## Overview
A multi-user web application for generating and editing parking lot GeoJSON from satellite imagery using an AI model.

## Tech Stack
- **Backend**: FastAPI (Python 3.11+)
- **Frontend**: React 18 + TypeScript + Vite
- **Database**: PostgreSQL 15 + PostGIS
- **Maps**: Leaflet + ESRI World Imagery
- **Auth**: JWT tokens + RBAC
- **Containerization**: Docker Compose

---

## Phase 1: Project Setup & Infrastructure

### 1.1 Directory Structure
```
parking-lot-app/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app entry
│   │   ├── config.py            # Settings/env vars
│   │   ├── database.py          # DB connection
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py          # Login, register, user mgmt
│   │   │   ├── projects.py      # Area/project management
│   │   │   ├── inference.py     # Run model endpoint
│   │   │   └── polygons.py      # CRUD for GeoJSON polygons
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── user.py          # User + roles
│   │   │   ├── project.py       # Project/area definitions
│   │   │   └── polygon.py       # Parking lot polygons
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   └── *.py             # Pydantic schemas
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── inference.py     # Model inference logic
│   │   │   ├── tiles.py         # Satellite tile fetching
│   │   │   └── auth.py          # Password hashing, JWT
│   │   └── core/
│   │       ├── __init__.py
│   │       ├── security.py      # JWT utilities
│   │       └── permissions.py   # RBAC decorators
│   ├── alembic/                 # DB migrations
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Map/             # Leaflet map + editing
│   │   │   ├── Auth/            # Login/register forms
│   │   │   └── Admin/           # User management
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx    # Project list
│   │   │   ├── Editor.tsx       # Map + polygon editing
│   │   │   ├── Login.tsx
│   │   │   └── Admin.tsx        # User management
│   │   ├── hooks/
│   │   ├── services/            # API client
│   │   ├── store/               # State management
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   ├── vite.config.ts
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

### 1.2 Database Schema
```sql
-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'reviewer', -- admin, reviewer
    is_active BOOLEAN DEFAULT false,  -- requires admin approval
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Projects (areas to process)
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    bounds GEOMETRY(POLYGON, 4326) NOT NULL,  -- bounding box
    status VARCHAR(50) DEFAULT 'pending',  -- pending, processing, review, approved
    created_by UUID REFERENCES users(id),
    approved_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Parking lot polygons
CREATE TABLE polygons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    geometry GEOMETRY(POLYGON, 4326) NOT NULL,
    properties JSONB DEFAULT '{}',
    status VARCHAR(50) DEFAULT 'detected',  -- detected, edited, approved, deleted
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    edited_by UUID REFERENCES users(id)
);

-- Audit log for polygon edits
CREATE TABLE polygon_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    polygon_id UUID REFERENCES polygons(id) ON DELETE CASCADE,
    action VARCHAR(50) NOT NULL,  -- create, edit, delete, split
    previous_geometry GEOMETRY(POLYGON, 4326),
    user_id UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## Phase 2: Backend Implementation

### 2.1 Core Setup
- [ ] Initialize FastAPI project with proper structure
- [ ] Configure PostgreSQL + PostGIS connection (GeoAlchemy2)
- [ ] Set up Alembic for migrations
- [ ] Environment configuration (.env)

### 2.2 Authentication & Authorization
- [ ] User registration endpoint
- [ ] Login endpoint (returns JWT)
- [ ] JWT validation middleware
- [ ] RBAC permission decorators
- [ ] Admin endpoints for user management (activate, change role)

### 2.3 Project Management
- [ ] Create project (define bounding box)
- [ ] List projects (with status filters)
- [ ] Get project details
- [ ] Update project status
- [ ] Delete project (admin only)

### 2.4 Model Inference
- [ ] Adapt existing inference code from parking-lot-mapping-tool
- [ ] Endpoint to trigger inference for a project
- [ ] Fetch ESRI tiles for bounding box
- [ ] Run model and save results to DB
- [ ] Background job support (long-running inference)

### 2.5 Polygon CRUD
- [ ] Get all polygons for a project (as GeoJSON)
- [ ] Update polygon geometry (edit)
- [ ] Delete polygon (soft delete)
- [ ] Create new polygon (manual add)
- [ ] Split polygon into two
- [ ] Polygon history/audit trail

---

## Phase 3: Frontend Implementation

### 3.1 Core Setup
- [ ] Initialize React + TypeScript + Vite project
- [ ] Configure routing (React Router)
- [ ] Set up API client (axios/fetch)
- [ ] Auth state management (context/zustand)
- [ ] Protected route wrapper

### 3.2 Authentication UI
- [ ] Login page
- [ ] Registration page
- [ ] "Awaiting approval" state handling

### 3.3 Dashboard
- [ ] Project list view
- [ ] Create new project (draw bounding box on map)
- [ ] Project status indicators
- [ ] Filter/search projects

### 3.4 Map Editor
- [ ] Leaflet map with ESRI World Imagery
- [ ] Display polygons from GeoJSON
- [ ] Leaflet.draw integration for editing:
  - [ ] Select and edit polygon vertices
  - [ ] Delete selected polygon
  - [ ] Draw new polygon
  - [ ] Split polygon (draw line through existing)
- [ ] Save changes to backend
- [ ] Undo/redo support
- [ ] Submit for approval button

### 3.5 Admin Panel
- [ ] User list
- [ ] Activate/deactivate users
- [ ] Change user roles
- [ ] Create new users

---

## Phase 4: Integration & Polish

### 4.1 Model Integration
- [ ] Copy/adapt model files from parking-lot-mapping-tool
- [ ] Test inference pipeline end-to-end
- [ ] Handle large areas (tile chunking)

### 4.2 Docker Setup
- [ ] Backend Dockerfile
- [ ] Frontend Dockerfile (nginx for production)
- [ ] docker-compose.yml with all services
- [ ] Volume mounts for model files

### 4.3 Production Readiness
- [ ] Environment variable configuration
- [ ] CORS configuration
- [ ] Error handling & logging
- [ ] Basic rate limiting
- [ ] Health check endpoints

---

## Implementation Order

1. **Backend skeleton** - FastAPI app, DB connection, basic auth
2. **Database models** - Users, Projects, Polygons with PostGIS
3. **Auth system** - JWT login, registration, RBAC
4. **Frontend skeleton** - React app, routing, auth flow
5. **Project CRUD** - Backend + frontend
6. **Map editor** - Leaflet + polygon editing
7. **Inference integration** - Adapt existing model code
8. **Admin panel** - User management
9. **Docker setup** - Containerization
10. **Testing & polish**

---

## Questions/Decisions Made
- ESRI World Imagery for satellite tiles (free, good quality)
- JWT-based auth (stateless, scales well)
- PostGIS for spatial data (industry standard)
- Soft deletes for polygons (audit trail)
- Admin approval required for new user accounts
