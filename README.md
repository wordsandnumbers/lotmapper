# Parking Lot Mapping Tool

A web application for detecting and editing parking lot polygons from satellite imagery using AI.

## Features

- **AI-Powered Detection**: Uses a SegFormer model (UTEL-UIUC/SegFormer-large-parking) to detect parking lots from Google Maps satellite imagery
- **Worker Queue**: Inference jobs run in a dedicated RabbitMQ-backed worker container, keeping the API responsive
- **Live Progress**: SSE-based progress streaming so the browser shows real-time inference status
- **Interactive Map Editor**: Edit, add, delete, and split parking lot polygons on a Leaflet map
- **City Boundary Search**: Look up official downtown/city boundaries by name (via ArcGIS Hub) to use as project bounds
- **Multi-User Support**: Role-based access control (Admin, Owner, Reviewer)
- **Email-First Signup**: Public "Request Access" flow + Owner-initiated invites, both completed via a signed signup link
- **Project Management**: Create projects for different areas, track status through a review workflow

## Tech Stack

- **Backend**: FastAPI (Python 3.11+)
- **Worker**: Same backend image, runs RabbitMQ consumer for inference jobs
- **Frontend**: React + TypeScript, served via nginx
- **Database**: PostgreSQL 15 + PostGIS
- **Message Queue**: RabbitMQ 3.13
- **Maps**: Google Maps satellite tiles (proxied + cached by backend)
- **Auth**: JWT-based authentication
- **Email**: Resend (transactional sends for signup links + Owner notifications)

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

3. Create the first admin user (only needed once, to bootstrap):
   ```bash
   docker compose exec backend python scripts/create_admin.py admin@example.com yourpassword
   ```
   Subsequent users go through the email signup flow — see [Access & Signup](#access--signup).

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

# Email — needed for the signup flow
RESEND_API_KEY=re_your_resend_api_key   # optional in dev; emails log to stdout if unset
EMAIL_FROM=onboarding@resend.dev        # in prod, must be an address on a verified Resend domain
APP_BASE_URL=http://localhost:5173      # in prod, your public URL — used to build signup links
```

In production, `EMAIL_FROM` must be on a domain you've verified at [resend.com/domains](https://resend.com/domains); `onboarding@resend.dev` only delivers to your own Resend account email. `APP_BASE_URL` is embedded in outbound emails, so it must be the public frontend URL, not `localhost`.

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

- **Admin**: Manages user roles and creates users directly. Can approve projects.
- **Owner**: Approves access requests and sends invites. Receives email notifications when someone requests access.
- **Reviewer**: Can create projects, run detection, and edit polygons. The default role assigned to new signups.

### Access & Signup

There are two paths into the app, both ending at a "Set Password" page reached via a signed link:

**Public "Request Access"** — anyone can submit their email at `/register`:

1. Request creates a pending user row and emails all active Owners.
2. An Owner opens the Admin page and activates the request.
3. Activation emails the requester a single-use signup link (~32-char token, 72h TTL).
4. The requester clicks the link, sets a password, and is logged in.

**Owner-initiated invite** — Owners can skip the request step from the Admin page:

1. Owner enters an email in the "Invite by Email" section.
2. Recipient is emailed a signup link directly (no approval step).
3. Duplicate invites / existing requests / existing accounts surface a clear 409 error.

Admins keep the ability to create users directly via `POST /auth/users` (used by `scripts/create_admin.py` for bootstrapping) and to change roles. Only Owners can activate pending requests.

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
│   ├── alembic/           # Database migrations (001–008)
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
