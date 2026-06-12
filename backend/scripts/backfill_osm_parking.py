"""
One-time script to fetch and store OSM parking polygons for all projects
that don't currently have any (i.e., projects run before the OSM step was added).
Run inside the backend container:
  python scripts/backfill_osm_parking.py
"""
import asyncio
import json
import logging
import sys
import os

sys.path.insert(0, '/app')
os.chdir('/app')

from sqlalchemy import func
from shapely.geometry import shape, MultiPolygon

from app.database import SessionLocal
from app.models.project import Project
from app.models.polygon import Polygon as PolygonModel
from app.services.osm import fetch_osm_parking

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


async def backfill_project(db, project: Project) -> int:
    bounds_geojson = db.execute(func.ST_AsGeoJSON(project.bounds)).scalar()
    bounds = json.loads(bounds_geojson)

    if bounds["type"] == "MultiPolygon":
        all_points = [pt for poly in bounds["coordinates"] for ring in poly for pt in ring]
    else:
        all_points = [pt for ring in bounds["coordinates"] for pt in ring]

    lngs = [c[0] for c in all_points]
    lats = [c[1] for c in all_points]
    min_lng, max_lng = min(lngs), max(lngs)
    min_lat, max_lat = min(lats), max(lats)

    boundary_shape = shape(bounds)

    osm_lots = await fetch_osm_parking(min_lat, min_lng, max_lat, max_lng)
    saved = 0
    for p in osm_lots:
        if not p.intersects(boundary_shape):
            continue
        try:
            clipped = p.intersection(boundary_shape)
            if clipped.is_empty:
                continue
            geoms = list(clipped.geoms) if isinstance(clipped, MultiPolygon) else [clipped]
            for g in geoms:
                if g.geom_type == "Polygon" and not g.is_empty:
                    db.add(PolygonModel(
                        project_id=project.id,
                        geometry=f"SRID=4326;{g.wkt}",
                        properties={"source": "osm"},
                        status="detected",
                    ))
                    saved += 1
        except Exception as e:
            logger.warning(f"  Skipping polygon: {e}")
            continue

    db.commit()
    return saved


async def main():
    db = SessionLocal()
    try:
        # Find projects with no OSM polygons
        projects = db.query(Project).filter(
            Project.status.in_(["review", "approved"])
        ).all()

        to_backfill = []
        for p in projects:
            osm_count = db.query(PolygonModel).filter(
                PolygonModel.project_id == p.id,
                PolygonModel.properties["source"].astext == "osm",
            ).count()
            if osm_count == 0:
                to_backfill.append(p)

        logger.info(f"Found {len(to_backfill)} projects without OSM data (of {len(projects)} total)")

        for i, p in enumerate(to_backfill):
            logger.info(f"  [{i+1}/{len(to_backfill)}] {p.name} ({p.id}) ...")
            try:
                n = await backfill_project(db, p)
                logger.info(f"    → saved {n} OSM polygons")
            except Exception as e:
                logger.error(f"    → FAILED: {e}")
                db.rollback()
            # Respect Overpass rate limits — 5s between requests
            if i < len(to_backfill) - 1:
                await asyncio.sleep(5)

    finally:
        db.close()

    logger.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())
