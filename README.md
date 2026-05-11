# Parking Lot Mapping Tool

A web application for detecting and editing parking lot polygons from satellite imagery using AI.

## Features

- **AI-Powered Detection**: Uses a SegFormer model (UTEL-UIUC/SegFormer-large-parking) to detect parking lots from Google Maps satellite imagery
- **Worker Queue**: Inference jobs run in a dedicated RabbitMQ-backed worker container, keeping the API responsive
- **Live Progress**: SSE-based progress streaming so the browser shows real-time inference status
- **Interactive Map Editor**: Edit, add, delete, and split parking lot polygons on a Leaflet map
- **City Boundary Search**: Look up official downtown/city boundaries by name (via ArcGIS Hub) to use as project bounds
- **Multi-User Support**: Role-based access control (Admin, Reviewer)
- **Project Management**: Create projects for different areas, track status through a review workflow

## Tech Stack

- **Backend**: FastAPI (Python 3.11+)
- **Worker**: Same backend image, runs RabbitMQ consumer for inference jobs
- **Frontend**: React + TypeScript, served via nginx
- **Database**: PostgreSQL 15 + PostGIS
- **Message Queue**: RabbitMQ 3.13
- **Maps**: Google Maps satellite tiles (proxied + cached by backend)
- **Auth**: JWT-based authentication

## Getting Started

### Prerequisites

- Docker and Docker Compose
- A Google Maps API key (set in `.env`)

### Quick Start

1. Clone the repository and set up your environment:
   ```bash
   cp .env.example .env
   # Edit .env and set GOOGLE_MAPS_API_KEY and SECRET_KEY
   ```

2. Start all services:
   ```bash
   docker compose up -d
   ```

3. Create an admin user:
   ```bash
   docker compose exec backend python scripts/create_admin.py admin@example.com yourpassword
   ```

4. Access the application:
   - Frontend: http://localhost:5173
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs
   - RabbitMQ Management: http://localhost:15672 (user: `parking` / `parking`)

### Environment Variables

Backend (`.env`):
```
DATABASE_URL=postgresql://postgres:postgres@db:5432/parking_lots
SECRET_KEY=your-secret-key
GOOGLE_MAPS_API_KEY=your-google-maps-key
CORS_ORIGINS=["http://localhost:5173"]
RABBITMQ_URL=amqp://parking:parking@rabbitmq:5672/
```

## Usage

### Workflow

1. **Create a Project**: Click "New Project" on the dashboard, then either draw a boundary on the map or search for a city/downtown boundary by name
2. **Run Detection**: Click "Run Detection" — the job is queued and progress streams to the UI in real time
3. **Edit Results**: Use the map tools to edit, add, delete, or split polygons
4. **Submit for Review**: When editing is complete, submit for admin review
5. **Approve**: Admins can approve the final results

### Map Editing Tools

- **Draw**: Add new polygons
- **Edit**: Modify existing polygon vertices
- **Delete**: Remove polygons
- **Split**: Click on a polygon, then draw a line to split it

### User Roles

- **Admin**: Full access — can approve projects and manage users
- **Reviewer**: Can create projects, run detection, and edit polygons

## Project Structure

```
parking-lot-app/
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI routes (auth, projects, polygons, inference, cities, maps)
│   │   ├── core/          # Security & permissions
│   │   ├── models/        # SQLAlchemy models
│   │   ├── schemas/       # Pydantic schemas
│   │   ├── services/      # Business logic (inference, city_resolver, queue, sse, tiles, osm)
│   │   └── worker_main.py # RabbitMQ inference worker entry point
│   ├── alembic/           # Database migrations (001–004)
│   └── scripts/           # Utility scripts
├── frontend/
│   └── src/
│       ├── components/    # React components
│       ├── pages/         # Page components
│       ├── services/      # API client
│       └── store/         # State management (zustand)
├── model/                 # Custom model checkpoint (volume-mounted, not committed)
└── docker-compose.yml
```

## Model Integration

The app uses [UTEL-UIUC/SegFormer-large-parking](https://huggingface.co/UTEL-UIUC/SegFormer-large-parking) from HuggingFace, downloaded automatically on first run and cached in a Docker volume.

To use a custom-trained checkpoint:

1. Place your model file in the `model/` directory
2. Set `MODEL_PATH` in your environment configuration

## Citation

If you use this tool or its outputs in research, please cite the model it is built on:

```bibtex
@inproceedings{qiam2025pipeline,
  title={A Pipeline and NIR-Enhanced Dataset for Parking Lot Segmentation},
  author={Qiam, Shirin and Devunuri, Saipraneeth and Lehe, Lewis J},
  booktitle={2025 IEEE/CVF Winter Conference on Applications of Computer Vision (WACV)},
  pages={1227--1236},
  year={2025},
  organization={IEEE}
}
```

## Production Deployment (DigitalOcean)

The app deploys to a DigitalOcean Droplet via GitHub Actions. Images are built and pushed to GHCR on every push to `main`, then pulled onto the Droplet.

### One-time Droplet setup

```bash
# Install Docker
apt update && apt install -y docker.io docker-compose-plugin git jq
usermod -aG docker $USER && newgrp docker

# Clone repo
git clone https://github.com/wordsandnumbers/parking-lot-app /opt/parking-lot-app
cd /opt/parking-lot-app && git checkout main

# Write .env (never committed — contains real secrets)
cat > .env << EOF
SECRET_KEY=$(openssl rand -hex 32)
GOOGLE_MAPS_API_KEY=<your-key>
DOMAIN=<your-domain>
EOF

# Initial start (builds images locally before CI/CD has pushed any)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Create first admin user
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend \
  python scripts/create_admin.py admin@example.com <password>
```

### GitHub Secrets required

| Secret | Description |
|---|---|
| `DO_HOST` | Droplet public IP |
| `DO_USER` | SSH user (`root` or deploy user) |
| `DO_SSH_KEY` | Private SSH key for Droplet access |

`GITHUB_TOKEN` is automatic — no setup needed for GHCR push.

### CI/CD

Push to `main` → builds backend + frontend images → pushes to GHCR → SSHs into Droplet → `docker compose pull && up`. Takes ~3–4 minutes. `db`, `rabbitmq`, and `caddy` are not restarted on deploys.

### Rollback

Trigger the **Rollback** workflow from the GitHub Actions UI. Enter the short git SHA (e.g. `abc1234`) to roll back to. Migrations are not reversed — they are forward-only.

### Manual deploy / rollback

```bash
ssh root@<droplet-ip>
cd /opt/parking-lot-app

# Deploy a specific version
git pull origin main
sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=git-<sha>/" .env
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull backend worker frontend
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps backend worker frontend
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T backend alembic upgrade head
```

### Bumping the app version

```bash
npm version patch   # 1.0.0 → 1.0.1  (bug fix)
npm version minor   # 1.0.0 → 1.1.0  (new feature)
npm version major   # 1.0.0 → 2.0.0  (breaking change)
git push && git push --tags
```

`npm version` bumps `package.json`, commits, and creates a git tag automatically. The version is baked into every Docker image as `v1.0.0+git-<sha>` and visible at `GET /health`, in worker logs, the `/docs` page, and the browser console.

---

## Development Notes

- **Frontend changes** require a rebuild: `docker compose build frontend && docker compose up -d frontend`
- **Backend changes** must be copied in (source is not volume-mounted): `docker compose cp <file> backend:/app/<path>`
- **Migrations** must also be copied before running: `docker compose cp backend/alembic/versions/XXX.py backend:/app/alembic/versions/`
- The worker container shares the backend image — restart it after backend changes: `docker compose restart worker`

## API Documentation

Once the backend is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## License

MIT
