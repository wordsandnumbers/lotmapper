"""Debug script: print what ArcGIS returns for a city at each stage."""
import asyncio
import sys

sys.path.insert(0, "/app")
from app.services.city_resolver import (
    _arcgis_search,
    _query_service_for_downtown,
    _get_city_centroid,
    _is_near_city,
)

CITY = sys.argv[1] if len(sys.argv) > 1 else "Denver"
STATE = sys.argv[2] if len(sys.argv) > 2 else "CO"


async def main():
    print(f"\n=== Debugging {CITY}, {STATE} ===\n")

    # Stage 1: direct search
    query = f"{CITY} {STATE} neighborhood boundary"
    print(f"Stage 1 query: {query!r}")
    results = await _arcgis_search(query, num=5)
    print(f"  {len(results)} ArcGIS results")
    for i, r in enumerate(results[:5]):
        print(f"  [{i}] title={r.get('title')!r}  url={r.get('url')!r}")

    centroid = await _get_city_centroid(CITY, STATE)
    print(f"\nCity centroid: {centroid}")

    print("\n--- Querying each result's layer 0 (merged union) ---")
    for i, r in enumerate(results[:3]):
        url = r.get("url", "")
        if not url:
            continue
        title = r.get("title", "")
        print(f"\n[{i}] {title!r} — {url}")

        # Try as boundary layer (no keyword filter)
        candidate = await _query_service_for_downtown(url, service_title=title, filter_by_zone_keywords=False)
        if candidate:
            near = _is_near_city(candidate["geometry"], centroid) if centroid else "?"
            print(f"  Boundary candidate: name={candidate['name']!r}  score={candidate['score']}  area={candidate['_area']:.6f}  near={near}")
        else:
            print(f"  No boundary candidate (filter_by_zone_keywords=False)")

        # Try as zoning layer (keyword filter)
        candidate = await _query_service_for_downtown(url, service_title=title, filter_by_zone_keywords=True)
        if candidate:
            near = _is_near_city(candidate["geometry"], centroid) if centroid else "?"
            print(f"  Zoning candidate:   name={candidate['name']!r}  score={candidate['score']}  area={candidate['_area']:.6f}  near={near}")
        else:
            print(f"  No zoning candidate (filter_by_zone_keywords=True)")


asyncio.run(main())
