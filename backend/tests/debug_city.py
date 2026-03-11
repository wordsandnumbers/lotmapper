"""Debug script: print what ArcGIS returns for a city at each stage."""
import asyncio
import sys
import httpx
import re

sys.path.insert(0, "/app")
from app.services.city_resolver import _arcgis_search, _query_service_for_candidates, _get_city_centroid, _is_near_city

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

    print("\n--- Querying each result's layer 0 ---")
    for i, r in enumerate(results[:3]):
        url = r.get("url", "")
        if not url:
            continue
        print(f"\n[{i}] {r.get('title')!r} — {url}")
        batch = await _query_service_for_candidates(url)
        print(f"  Raw candidates: {len(batch)}")
        for c in batch[:5]:
            near = _is_near_city(c["geometry"], centroid) if centroid else "?"
            print(f"    name={c['name']!r}  score={c['score']}  near={near}")
        if len(batch) > 5:
            print(f"    ... and {len(batch)-5} more")

    # Check what field names the features have (raw fetch for first result)
    if results:
        url = results[0].get("url", "").rstrip("/")
        query_url = (url + "/query") if re.search(r"/\d+$", url) else (url + "/0/query")
        print(f"\n--- Raw feature properties from {query_url} ---")
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.get(
                    query_url,
                    params={"where": "1=1", "outFields": "*", "returnGeometry": "false", "f": "geojson", "resultRecordCount": 1},
                )
                fc = r.json()
            features = fc.get("features", [])
            if features:
                print(f"  Fields: {list(features[0].get('properties', {}).keys())}")
            else:
                print("  No features returned")
        except Exception as e:
            print(f"  Error: {e}")


asyncio.run(main())
