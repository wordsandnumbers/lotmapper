# Parking Lot Mapping Tool

A web application for detecting and editing parking lot polygons from satellite imagery using AI.

## Features

- **AI-Powered Detection**: Uses a SegFormer model to detect parking lots from satellite imagery
- **Interactive Map Editor**: Edit, add, delete, and split parking lot polygons
- **Multi-User Support**: Role-based access control (Admin, Reviewer)
- **Project Management**: Create projects for different areas, track status through workflow
- **Satellite Imagery**: Uses ESRI World Imagery tiles

## Tech Stack

- **Backend**: FastAPI (Python)
- **Frontend**: React + TypeScript + Vite
- **Database**: PostgreSQL + PostGIS
- **Maps**: Leaflet + React-Leaflet
- **Auth**: JWT-based authentication

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Node.js 20+ (for local frontend development)
- Python 3.11+ (for local backend development)

### Quick Start with Docker

1. Clone the repository:
   ```bash
   cd /Users/justin/git/parking-lot-app
   ```

2. Start the services:
   ```bash
   docker-compose up -d
   ```

3. Create an admin user:
   ```bash
   docker-compose exec backend python scripts/create_admin.py admin@example.com yourpassword
   ```

4. Access the application:
   - Frontend: http://localhost:5173
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

### Local Development

#### Backend

1. Create a virtual environment:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # or `venv\Scripts\activate` on Windows
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up the database (requires PostgreSQL with PostGIS):
   ```bash
   # Create database
   createdb parking_lots
   psql parking_lots -c "CREATE EXTENSION postgis;"

   # Run migrations
   alembic upgrade head
   ```

4. Create an admin user:
   ```bash
   python scripts/create_admin.py admin@example.com yourpassword
   ```

5. Start the server:
   ```bash
   uvicorn app.main:app --reload
   ```

#### Frontend

1. Install dependencies:
   ```bash
   cd frontend
   npm install
   ```

2. Start the development server:
   ```bash
   npm run dev
   ```

## Usage

### Workflow

1. **Create a Project**: Click "New Project" on the dashboard and draw a bounding box on the map
2. **Run Detection**: Click "Run Detection" to start the AI model
3. **Edit Results**: Use the map tools to edit, add, delete, or split polygons
4. **Submit for Review**: When editing is complete, submit for admin review
5. **Approve**: Admins can approve the final results

### Map Editing Tools

- **Draw**: Add new polygons
- **Edit**: Modify existing polygon vertices
- **Delete**: Remove polygons
- **Split**: Click on a polygon, then draw a line to split it

### User Roles

- **Admin**: Full access, can approve projects and manage users
- **Reviewer**: Can create projects, run detection, and edit polygons

## Project Structure

```
parking-lot-app/
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI routes
│   │   ├── core/          # Security & permissions
│   │   ├── models/        # SQLAlchemy models
│   │   ├── schemas/       # Pydantic schemas
│   │   └── services/      # Business logic
│   ├── alembic/           # Database migrations
│   └── scripts/           # Utility scripts
├── frontend/
│   └── src/
│       ├── components/    # React components
│       ├── pages/         # Page components
│       ├── services/      # API client
│       └── store/         # State management
└── docker-compose.yml
```

## Configuration

### Environment Variables

Backend (`.env`):
```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/parking_lots
SECRET_KEY=your-secret-key
CORS_ORIGINS=["http://localhost:5173"]
MODEL_PATH=../model/parking_lot_model.pt
```

## Model Integration

To use your own trained model:

1. Place your model checkpoint in the `model/` directory
2. Update `MODEL_PATH` in the backend configuration
3. The model should be compatible with the SegformerFinetuner class from the original parking-lot-mapping-tool

## API Documentation

Once the backend is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## License

MIT
