"""
Filesystem cache for map tiles.
Tiles are stored at CACHE_DIR/{z}/{x}/{y}.img and served on cache hit.
"""
from pathlib import Path

CACHE_DIR = Path("/app/tile_cache")


def get_cached_tile(z: int, x: int, y: int) -> bytes | None:
    path = CACHE_DIR / str(z) / str(x) / f"{y}.img"
    if path.exists():
        return path.read_bytes()
    return None


def cache_tile(z: int, x: int, y: int, data: bytes) -> None:
    path = CACHE_DIR / str(z) / str(x) / f"{y}.img"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
