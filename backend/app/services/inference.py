"""
Inference service that runs the parking lot detection model.
Adapted from the parking-lot-mapping-tool codebase.
Uses UTEL-UIUC/SegFormer-large-parking model.
"""
import os
import asyncio
import json
import logging
import shutil
from typing import Callable, List, Optional, Tuple
import numpy as np
import cv2
from PIL import Image, ImageFilter
import torch
from torch import nn
from torch.utils.data import Dataset, DataLoader
from sqlalchemy.orm import Session
from sqlalchemy import func
from shapely.geometry import Polygon, MultiPolygon, shape, box
from shapely.ops import unary_union
import pytorch_lightning as pl
from transformers import SegformerImageProcessor, SegformerForSemanticSegmentation
from huggingface_hub import hf_hub_download

from app.database import SessionLocal
from app.models.project import Project
from app.models.polygon import Polygon as PolygonModel
from app.services.tiles import fetch_tiles_for_bounds, calculate_optimal_zoom
from app.services.osm import fetch_osm_roads, fetch_osm_buildings, subtract_features, simplify_polygons
from app.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
settings = get_settings()

# Model will be loaded lazily
_model = None
_feature_extractor = None

# Label mapping for parking lot detection
ID2LABEL = {"0": "background", "1": "parking_lot"}


class SegformerFinetuner(pl.LightningModule):
    """
    PyTorch Lightning module for SegFormer fine-tuning.
    Adapted from parking-lot-mapping-tool/inference.py
    """

    def __init__(self, id2label, train_dataloader=None, val_dataloader=None,
                 test_dataloader=None, metrics_interval=100):
        super(SegformerFinetuner, self).__init__()
        self.id2label = id2label
        self.metrics_interval = metrics_interval
        self.train_dl = train_dataloader
        self.val_dl = val_dataloader
        self.test_dl = test_dataloader

        self.num_classes = len(id2label.keys())
        self.label2id = {v: k for k, v in self.id2label.items()}

        self.model = SegformerForSemanticSegmentation.from_pretrained(
            "nvidia/segformer-b5-finetuned-cityscapes-1024-1024",
            return_dict=False,
            num_labels=self.num_classes,
            id2label=self.id2label,
            label2id=self.label2id,
            ignore_mismatched_sizes=True,
        )

    def forward(self, images, masks):
        outputs = self.model(pixel_values=images, labels=masks)
        return outputs

    def configure_optimizers(self):
        return torch.optim.Adam(
            [p for p in self.parameters() if p.requires_grad],
            lr=2e-05, eps=1e-08
        )


def get_model():
    """Load the parking lot detection model lazily."""
    global _model, _feature_extractor

    if _model is None:
        try:
            print("[MODEL] Loading SegformerImageProcessor...", flush=True)

            # Load image processor with size=512 (as per notebook)
            _feature_extractor = SegformerImageProcessor.from_pretrained(
                "nvidia/segformer-b5-finetuned-cityscapes-1024-1024"
            )
            _feature_extractor.do_reduce_labels = False
            _feature_extractor.size = 512
            print("[MODEL] Image processor loaded (size=512)", flush=True)

            # Download the parking lot model from HuggingFace
            print("[MODEL] Downloading UTEL-UIUC/SegFormer-large-parking model...", flush=True)
            repo_id = "UTEL-UIUC/SegFormer-large-parking"
            model_path = hf_hub_download(repo_id=repo_id, filename="best_model.ckpt")
            print(f"[MODEL] Model downloaded to: {model_path}", flush=True)

            # Determine device
            if torch.cuda.is_available():
                device = torch.device("cuda")
                print("[MODEL] Using CUDA", flush=True)
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                device = torch.device("mps")
                print("[MODEL] Using MPS (Apple Silicon)", flush=True)
            else:
                device = torch.device("cpu")
                print("[MODEL] Using CPU", flush=True)

            # Load the fine-tuned model from checkpoint
            print("[MODEL] Loading model from checkpoint...", flush=True)
            _model = SegformerFinetuner.load_from_checkpoint(
                model_path,
                id2label=ID2LABEL,
                map_location=device,
            )
            _model.model.to(device)
            _model.model.eval()
            print("[MODEL] Parking lot model loaded successfully!", flush=True)

        except Exception as e:
            print(f"[MODEL ERROR] Failed to load model: {e}", flush=True)
            import traceback
            traceback.print_exc()
            raise

    return _model, _feature_extractor


def split_image(img: np.ndarray, tile_size: int = 512) -> Tuple[List[np.ndarray], int, int, int, int]:
    """Split image into tiles for inference."""
    h, w = img.shape[:2]
    tiles = []

    for i in range(0, h, tile_size):
        for j in range(0, w, tile_size):
            tile = img[i:i + tile_size, j:j + tile_size]
            th, tw = tile.shape[:2]

            # Pad if needed
            if th < tile_size or tw < tile_size:
                padded = np.zeros((tile_size, tile_size, 3), dtype=img.dtype)
                padded[:th, :tw] = tile
                tile = padded

            tiles.append(tile)

    rows = (h + tile_size - 1) // tile_size
    cols = (w + tile_size - 1) // tile_size

    # Calculate actual image dimensions after tiling
    img_h = rows * tile_size
    img_w = cols * tile_size

    return tiles, rows, cols, img_h, img_w


def run_model_on_tiles(
    tiles: List[np.ndarray],
    tile_progress_fn: Optional[Callable] = None,
) -> List[np.ndarray]:
    """Run inference on a list of image tiles using the parking lot model."""
    print("[INFERENCE] Getting model...", flush=True)
    model, feature_extractor = get_model()
    print("[INFERENCE] Model ready", flush=True)
    predictions = []

    # Determine device
    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")

    print(f"[INFERENCE] Running on {device.type.upper()}", flush=True)

    total_tiles = len(tiles)
    print(f"[INFERENCE] Processing {total_tiles} tiles...", flush=True)

    for idx, tile in enumerate(tiles):
        print(f"[INFERENCE] Tile {idx + 1}/{total_tiles} ({((idx + 1) / total_tiles * 100):.1f}%)", flush=True)

        # Convert to PIL Image
        pil_image = Image.fromarray(tile)

        # Prepare input using feature extractor
        encoded = feature_extractor(pil_image, return_tensors="pt")
        pixel_values = encoded["pixel_values"].to(device)

        # Create dummy mask for forward pass (required by model but not used for inference)
        dummy_mask = torch.zeros((1, 512, 512), dtype=torch.long).to(device)

        # Run inference
        with torch.no_grad():
            outputs = model.model(pixel_values, dummy_mask)
            logits = outputs[1]  # outputs is (loss, logits)

            # Upsample to original tile size
            upsampled = nn.functional.interpolate(
                logits,
                size=(512, 512),
                mode="bilinear",
                align_corners=False,
            )
            pred = upsampled.argmax(dim=1).cpu().numpy()[0]
            predictions.append(pred)
            if tile_progress_fn:
                tile_progress_fn(idx + 1, total_tiles)

    logger.info(f"Completed inference on all {total_tiles} tiles")
    return predictions


def stitch_predictions(
    predictions: List[np.ndarray],
    rows: int,
    cols: int,
    original_h: int,
    original_w: int,
    tile_size: int = 512,
) -> np.ndarray:
    """Stitch tile predictions back into a single mask."""
    full_h = rows * tile_size
    full_w = cols * tile_size
    stitched = np.zeros((full_h, full_w), dtype=np.uint8)

    idx = 0
    for i in range(rows):
        for j in range(cols):
            y_start = i * tile_size
            x_start = j * tile_size
            stitched[y_start:y_start + tile_size, x_start:x_start + tile_size] = predictions[idx]
            idx += 1

    # Crop to original size
    return stitched[:original_h, :original_w]


def find_polygons(mask: np.ndarray) -> Tuple[List[Polygon], List[Polygon]]:
    """
    Extract polygons from a binary segmentation mask.
    Adapted from parking-lot-mapping-tool/functions.py
    Returns (outer_polygons, inner_polygons).
    """
    # Apply mode filter to clean up noise
    mask_img = Image.fromarray((mask * 255).astype(np.uint8))
    mask_img = mask_img.filter(ImageFilter.ModeFilter(size=13))
    mask_clean = np.array(mask_img.convert("L"))

    # Find contours
    contours, _ = cv2.findContours(mask_clean, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    polygons = []
    for contour in contours:
        if contour.shape[0] > 4:
            poly = Polygon(np.squeeze(contour))
            if poly.area > 1000:  # Filter small polygons
                # Fix invalid polygons
                if not poly.is_valid:
                    poly = poly.buffer(0)
                polygons.append(poly)

    # Find and handle nested polygons (inner polygons)
    inner_polygons = []
    for i, polygon in enumerate(polygons):
        for j, other in enumerate(polygons):
            if i != j and polygon.is_valid and other.is_valid:
                if other.within(polygon):
                    inner_polygons.append(other)

    # Remove inner polygons from main list
    outer_polygons = [p for p in polygons if p not in inner_polygons]

    return outer_polygons, inner_polygons


def pixels_to_coordinates(
    polygons: List[Polygon],
    lons: np.ndarray,
    lats: np.ndarray,
) -> List[Polygon]:
    """
    Convert pixel-based polygons to geographic coordinates.
    Adapted from parking-lot-mapping-tool/functions.py
    """
    coord_polygons = []

    for poly in polygons:
        if isinstance(poly, MultiPolygon):
            for geom in poly.geoms:
                coord_poly = _convert_single_polygon(geom, lons, lats)
                if coord_poly:
                    coord_polygons.append(coord_poly)
        else:
            coord_poly = _convert_single_polygon(poly, lons, lats)
            if coord_poly:
                coord_polygons.append(coord_poly)

    return coord_polygons


def _convert_single_polygon(
    poly: Polygon,
    lons: np.ndarray,
    lats: np.ndarray,
) -> Polygon:
    """Convert a single polygon from pixels to coordinates."""
    try:
        x, y = poly.exterior.coords.xy
        h, w = lons.shape

        coords = []
        for px, py in zip(x, y):
            # Clamp to image bounds
            ix = min(max(int(px), 0), w - 1)
            iy = min(max(int(py), 0), h - 1)
            coords.append((lons[iy, ix], lats[iy, ix]))

        if len(coords) >= 3:
            return Polygon(coords)
    except Exception as e:
        logger.warning(f"Failed to convert polygon: {e}")

    return None


async def run_inference_for_project(
    project_id: str,
    user_id: str,
    progress_callback: Optional[Callable] = None,
):
    """
    Run the full inference pipeline for a project.
    Called as a background task or from the worker.
    progress_callback(step, total, progress_pct, message) is awaited after each step.
    """
    async def _cb(step: int, total: int, pct: int, msg: str) -> None:
        if progress_callback:
            await progress_callback(step, total, pct, msg)

    import time
    start_time = time.time()

    # Debug output directory
    debug_dir = "/app/debug"
    os.makedirs(debug_dir, exist_ok=True)

    db = SessionLocal()
    try:
        logger.info(f"=" * 50)
        logger.info(f"STARTING INFERENCE FOR PROJECT {project_id}")
        logger.info(f"Using UTEL-UIUC/SegFormer-large-parking model")
        logger.info(f"=" * 50)

        # Get project
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            logger.error(f"Project {project_id} not found")
            return

        # Get bounds from project geometry
        bounds_geojson = db.execute(func.ST_AsGeoJSON(project.bounds)).scalar()
        bounds = json.loads(bounds_geojson)

        # Extract all points regardless of Polygon vs MultiPolygon
        if bounds["type"] == "MultiPolygon":
            all_points = [pt for poly in bounds["coordinates"] for ring in poly for pt in ring]
        else:
            all_points = [pt for ring in bounds["coordinates"] for pt in ring]
        lngs = [c[0] for c in all_points]
        lats = [c[1] for c in all_points]
        min_lng, max_lng = min(lngs), max(lngs)
        min_lat, max_lat = min(lats), max(lats)

        logger.info(f"[Step 1/8] Fetching satellite tiles...")
        logger.info(f"  Bounds: {min_lat:.4f}, {min_lng:.4f} to {max_lat:.4f}, {max_lng:.4f}")
        await _cb(1, 8, 5, "Fetching satellite tiles...")

        # Calculate optimal zoom
        zoom = calculate_optimal_zoom(min_lat, min_lng, max_lat, max_lng)
        logger.info(f"  Using zoom level {zoom}")

        # Fetch tiles
        fetch_start = time.time()
        image_array, lons, lats_array = await fetch_tiles_for_bounds(
            min_lat, min_lng, max_lat, max_lng, zoom
        )
        logger.info(f"  Fetched image: {image_array.shape[1]}x{image_array.shape[0]} pixels in {time.time() - fetch_start:.1f}s")
        await _cb(1, 8, 10, "Satellite tiles fetched")

        # Debug: save stitched image and log coordinate grid corners
        debug_img = Image.fromarray(image_array)
        debug_img.save(f"{debug_dir}/stitched_{project_id}.png")
        logger.info(f"  DEBUG: Saved stitched image to {debug_dir}/stitched_{project_id}.png")
        logger.info(f"  DEBUG: Coord grid corners:")
        logger.info(f"    Top-left (0,0): lon={lons[0,0]:.6f}, lat={lats_array[0,0]:.6f}")
        logger.info(f"    Top-right (0,w): lon={lons[0,-1]:.6f}, lat={lats_array[0,-1]:.6f}")
        logger.info(f"    Bottom-left (h,0): lon={lons[-1,0]:.6f}, lat={lats_array[-1,0]:.6f}")
        logger.info(f"    Bottom-right (h,w): lon={lons[-1,-1]:.6f}, lat={lats_array[-1,-1]:.6f}")

        # Split into tiles
        logger.info(f"[Step 2/8] Splitting image into 512x512 tiles...")
        tiles, rows, cols, img_h, img_w = split_image(image_array)
        logger.info(f"  Split into {len(tiles)} tiles ({rows}x{cols} grid)")
        await _cb(2, 8, 15, f"Split into {len(tiles)} tiles")

        # Pre-filter: skip inference on tiles that don't intersect the project boundary.
        boundary_shape = shape(bounds)
        h_px, w_px = lons.shape
        tile_size = 512

        tiles_active = []
        for idx in range(len(tiles)):
            row_idx = idx // cols
            col_idx = idx % cols
            y0 = row_idx * tile_size
            x0 = col_idx * tile_size
            y1 = min(y0 + tile_size, h_px) - 1
            x1 = min(x0 + tile_size, w_px) - 1
            corner_lons = [lons[y0, x0], lons[y0, x1], lons[y1, x0], lons[y1, x1]]
            corner_lats = [lats_array[y0, x0], lats_array[y0, x1],
                           lats_array[y1, x0], lats_array[y1, x1]]
            tile_box = box(min(corner_lons), min(corner_lats),
                           max(corner_lons), max(corner_lats))
            tiles_active.append(boundary_shape.intersects(tile_box))

        active_indices = [i for i, a in enumerate(tiles_active) if a]
        active_tiles = [tiles[i] for i in active_indices]
        skipped = len(tiles) - len(active_tiles)
        logger.info(f"  Tile pre-filter: {len(active_tiles)}/{len(tiles)} tiles intersect boundary "
                    f"({skipped} skipped)")

        # Run inference in a thread pool so the event loop stays free for other requests
        logger.info(f"[Step 3/8] Running model inference on {len(active_tiles)} tiles...")
        inference_start = time.time()
        await _cb(3, 8, 15, f"Running model on {len(active_tiles)} tiles...")

        loop = asyncio.get_running_loop()
        if progress_callback and active_tiles:
            def tile_progress_sync(tile_idx: int, total_tiles: int) -> None:
                pct = 15 + int((tile_idx / total_tiles) * 45)
                asyncio.run_coroutine_threadsafe(
                    progress_callback(3, 8, pct, f"Running model on tile {tile_idx}/{total_tiles}"),
                    loop,
                )
            active_predictions = await loop.run_in_executor(
                None, lambda: run_model_on_tiles(active_tiles, tile_progress_fn=tile_progress_sync)
            )
        else:
            active_predictions = await loop.run_in_executor(None, run_model_on_tiles, active_tiles)
        logger.info(f"  Inference completed in {time.time() - inference_start:.1f}s")

        # Reconstruct full predictions list (zero mask for skipped tiles)
        predictions = [np.zeros((tile_size, tile_size), dtype=np.uint8)] * len(tiles)
        for i, pred in zip(active_indices, active_predictions):
            predictions[i] = pred

        # Stitch predictions
        logger.info(f"[Step 4/8] Stitching predictions...")
        h, w = image_array.shape[:2]
        mask = stitch_predictions(predictions, rows, cols, h, w)
        logger.info(f"  Created mask of size {mask.shape}")
        await _cb(4, 8, 65, "Stitching predictions...")

        # Debug: save mask image
        mask_img = Image.fromarray((mask * 255).astype(np.uint8))
        mask_img.save(f"{debug_dir}/mask_{project_id}.png")
        logger.info(f"  DEBUG: Saved mask to {debug_dir}/mask_{project_id}.png")

        # Find polygons
        logger.info(f"[Step 5/8] Extracting polygons from mask...")
        outer_polygons, inner_polygons = find_polygons(mask)
        logger.info(f"  Found {len(outer_polygons)} outer polygons, {len(inner_polygons)} inner polygons")
        await _cb(5, 8, 70, f"Extracted {len(outer_polygons)} polygons")

        # Convert to coordinates
        logger.info(f"[Step 6/8] Converting to geographic coordinates...")
        coord_polygons = pixels_to_coordinates(outer_polygons, lons, lats_array)
        inner_coord_polygons = pixels_to_coordinates(inner_polygons, lons, lats_array)

        # Subtract inner polygons from outer
        if inner_coord_polygons:
            inner_union = unary_union(inner_coord_polygons)
            coord_polygons = [
                p.difference(inner_union) if p.is_valid else p
                for p in coord_polygons
            ]

        logger.info(f"  Converted {len(coord_polygons)} polygons to coordinates")
        await _cb(6, 8, 75, "Converting to geographic coordinates...")

        # Step 7/8: Remove roads and buildings (OSM post-processing)
        logger.info(f"[Step 7/8] Fetching OSM roads and buildings for post-processing...")
        await _cb(7, 8, 80, "Fetching OSM data...")
        roads, buildings = await asyncio.gather(
            fetch_osm_roads(min_lat, min_lng, max_lat, max_lng),
            fetch_osm_buildings(min_lat, min_lng, max_lat, max_lng),
        )
        logger.info(f"  Got {len(roads)} road segments, {len(buildings)} buildings from OSM")
        coord_polygons = subtract_features(coord_polygons, roads, "roads")
        coord_polygons = subtract_features(coord_polygons, buildings, "buildings")
        await _cb(7, 8, 85, f"Removed roads and buildings ({len(roads)} + {len(buildings)} features)")

        # Step 8/8: Simplify polygon edges (equivalent to mapshaper -simplify 20%)
        logger.info(f"[Step 8/8] Simplifying polygon edges...")
        await _cb(8, 8, 90, "Simplifying polygons...")
        coord_polygons = simplify_polygons(coord_polygons, tolerance_meters=1.5)
        logger.info(f"  Simplified {len(coord_polygons)} polygons")

        # Clip to project boundary — tiles cover the bounding box, so detected
        # parking lots outside the actual boundary must be excluded.
        clipped = []
        for poly in coord_polygons:
            try:
                clipped_poly = poly.intersection(boundary_shape)
                if not clipped_poly.is_empty:
                    clipped.append(clipped_poly)
            except Exception as e:
                logger.warning(f"  Boundary clip failed for polygon: {e}")
        logger.info(f"  Clipped to boundary: {len(clipped)}/{len(coord_polygons)} polygons retained")
        coord_polygons = clipped

        # Debug: log first polygon coordinates
        if coord_polygons:
            first_poly = coord_polygons[0]
            coords = list(first_poly.exterior.coords)[:5]
            logger.info(f"  DEBUG: First polygon coords (first 5): {coords}")

        # Refresh database connection (may have timed out during long inference)
        db.close()
        db = SessionLocal()
        project = db.query(Project).filter(Project.id == project_id).first()

        # Save polygons to database
        saved_count = 0
        for poly in coord_polygons:
            if poly.is_empty:
                continue

            # Flatten any MultiPolygons that slipped through (e.g. from simplification)
            parts = list(poly.geoms) if isinstance(poly, MultiPolygon) else [poly]
            for part in parts:
                if part.is_empty:
                    continue
                wkt = f"SRID=4326;{part.wkt}"
                db_polygon = PolygonModel(
                    project_id=project_id,
                    geometry=wkt,
                    status="detected",
                    properties={},
                )
                db.add(db_polygon)
                saved_count += 1

        # Update project status
        project.status = "review"
        db.commit()

        total_time = time.time() - start_time
        logger.info(f"=" * 50)
        logger.info(f"INFERENCE COMPLETE")
        logger.info(f"  Project: {project_id}")
        logger.info(f"  Polygons saved: {saved_count}")
        logger.info(f"  Total time: {total_time:.1f}s")
        logger.info(f"=" * 50)

    except Exception as e:
        logger.error(f"Inference failed for project {project_id}: {e}")
        import traceback
        traceback.print_exc()

        # Reset project status so user can retry
        try:
            project = db.query(Project).filter(Project.id == project_id).first()
            if project:
                project.status = "pending"
                db.commit()
        except Exception:
            pass
        raise

    finally:
        db.close()
