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
