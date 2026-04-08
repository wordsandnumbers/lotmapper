# Parking Lot Mapping Tool - Implementation Plan

## Overview
A multi-user web application for generating and editing parking lot GeoJSON from satellite imagery using an AI model.

## Tech Stack
- **Backend**: FastAPI (Python 3.11+)
- **Frontend**: React 18 + TypeScript + Vite (served via nginx in production)
- **Database**: PostgreSQL 15 + PostGIS
- **Maps**: Google Maps satellite tiles (proxied via backend, with local file cache)
- **Auth**: JWT tokens + RBAC
- **Message Queue**: RabbitMQ (inference job queue)
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
│   │   ├── worker_main.py       # RabbitMQ inference worker entry
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py          # Login, register, user mgmt
│   │   │   ├── cities.py        # City boundary search
│   │   │   ├── deps.py          # Shared dependencies
│   │   │   ├── inference.py     # Trigger inference endpoint
│   │   │   ├── maps.py          # Google Maps tile proxy
│   │   │   ├── polygons.py      # CRUD for GeoJSON polygons
│   │   │   ├── projects.py      # Area/project management
│   │   │   └── tiles.py         # Tile serving
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── user.py          # User + roles
│   │   │   ├── project.py       # Project/area definitions
│   │   │   └── polygon.py       # Parking lot polygons
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   └── *.py             # Pydantic schemas
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── city_resolver.py # City boundary lookup (ArcGIS Hub + AGOL)
│   │       ├── inference.py     # Model inference logic
│   │       ├── osm.py           # OSM road/building subtraction
│   │       ├── queue.py         # RabbitMQ publish/consume helpers
│   │       ├── sse.py           # SSE event streaming
│   │       ├── stream.py        # Progress streaming helpers
│   │       ├── tile_cache.py    # Tile caching service
│   │       └── tiles.py         # Satellite tile fetching
│   ├── alembic/                 # DB migrations (001–004)
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
│   └── Dockerfile               # nginx production build
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
    bounds GEOMETRY(GEOMETRY, 4326) NOT NULL,  -- polygon or multipolygon boundary
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
- [x] Initialize FastAPI project with proper structure
- [x] Configure PostgreSQL + PostGIS connection (GeoAlchemy2)
- [x] Set up Alembic for migrations
- [x] Environment configuration (.env)

### 2.2 Authentication & Authorization
- [x] User registration endpoint
- [x] Login endpoint (returns JWT)
- [x] JWT validation middleware
- [x] RBAC permission decorators
- [x] Admin endpoints for user management (activate, change role)

### 2.3 Project Management
- [x] Create project (define boundary polygon or multipolygon)
- [x] List projects (with status filters)
- [x] Get project details
- [x] Update project status
- [x] Delete project (admin only)

### 2.4 Model Inference
- [x] Adapt existing inference code from parking-lot-mapping-tool (UTEL-UIUC/SegFormer-large-parking)
- [x] Endpoint to trigger inference for a project
- [x] Fetch Google Maps satellite tiles for bounding box (with local file cache)
- [x] Run model and save results to DB
- [x] RabbitMQ worker queue — inference jobs published by API, consumed by dedicated worker container
- [x] SSE progress streaming — client subscribes to `/inference/{project_id}/progress` for live updates
- [x] Pre-filter tiles to skip those outside project boundary (efficiency)
- [x] Post-clip detected polygons to project boundary (correctness)
- [x] OSM road/building subtraction post-processing
- [x] Polygon simplification

### 2.5 Polygon CRUD
- [x] Get all polygons for a project (as GeoJSON)
- [x] Update polygon geometry (edit)
- [x] Delete polygon (soft delete)
- [x] Create new polygon (manual add)
- [x] Split polygon into two
- [ ] Polygon history/audit trail

### 2.6 City Boundary Search
- [x] `/cities/search` endpoint — look up official city/downtown boundaries by name
- [x] Primary source: ArcGIS Hub API (hub.arcgis.com) — fast city open data queries
- [x] Fallback: ArcGIS Online search + org-ID discovery
- [x] Geographic filter: results must be within 0.3° of city centroid
- [x] Scoring: prefer layers whose titles contain downtown + boundary keywords
- [x] Minimum area filter (1e-5 deg²) to exclude parcel-level noise
- [x] Returns GeoJSON boundary ready to use as project bounds

---

## Phase 3: Frontend Implementation

### 3.1 Core Setup
- [x] Initialize React + TypeScript + Vite project
- [x] Configure routing (React Router)
- [x] Set up API client (fetch)
- [x] Auth state management (zustand)
- [x] Protected route wrapper

### 3.2 Authentication UI
- [x] Login page
- [x] Registration page
- [x] "Awaiting approval" state handling

### 3.3 Dashboard
- [x] Project list view
- [x] Create new project (draw polygon/multipolygon on Google Maps, or search for a city boundary)
- [x] Project status indicators
- [ ] Filter/search projects

### 3.4 Map Editor
- [x] Leaflet map with Google Maps satellite tiles
- [x] Display polygons from GeoJSON
- [x] Project boundary outline overlay
- [x] Leaflet.draw integration for editing:
  - [x] Select and edit polygon vertices
  - [x] Delete selected polygon
  - [x] Draw new polygon
  - [x] Split polygon (draw line through existing)
- [x] Save changes to backend
- [ ] Undo/redo support
- [x] Submit for approval button
- [x] SSE-based progress indicator during inference

### 3.5 Admin Panel
- [x] User list
- [x] Activate/deactivate users
- [x] Change user roles
- [x] Create new users

---

## Phase 4: Integration & Polish

### 4.1 Model Integration
- [x] Adapt model from parking-lot-mapping-tool (UTEL-UIUC/SegFormer-large-parking)
- [x] Test inference pipeline end-to-end
- [x] Handle large areas (512px tile chunking)

### 4.2 Docker Setup
- [x] Backend Dockerfile
- [x] Frontend Dockerfile (nginx for production)
- [x] Worker Dockerfile (shares backend image, runs worker_main.py)
- [x] RabbitMQ service (rabbitmq:3.13-management)
- [x] docker-compose.yml with all services (db, rabbitmq, backend, worker, frontend)
- [x] Volume mounts for model files, HuggingFace cache, tile cache, debug output

### 4.3 Production Readiness
- [x] Environment variable configuration
- [x] CORS configuration
- [x] Error handling & logging
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
10. **Worker queue** - RabbitMQ + SSE progress streaming
11. **City boundary search** - ArcGIS Hub integration

---

## Questions/Decisions Made
- Google Maps satellite tiles via backend proxy (with local file cache)
- JWT-based auth (stateless, scales well)
- PostGIS for spatial data (industry standard)
- Soft deletes for polygons (audit trail)
- Admin approval required for new user accounts
- Project bounds stored as `GEOMETRY` to support both Polygon and MultiPolygon
- Inference moved from thread pool executor to RabbitMQ worker queue (dedicated worker container)
- SSE used for real-time progress updates from worker back to browser
- Tile pre-filter skips model inference on tiles outside project boundary
- Detected polygons post-clipped to project boundary for correctness
- City boundary search uses ArcGIS Hub as primary source (fast, city-focused), AGOL as fallback
