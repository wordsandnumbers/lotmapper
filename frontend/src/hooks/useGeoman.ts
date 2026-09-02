import { useEffect, useRef } from 'react'
import L from 'leaflet'
import '@geoman-io/leaflet-geoman-free'
import '@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css'
import type { EditorMode } from '../components/MapToolbar'

interface GeomanCallbacks {
  onPolygonCreated: (geometry: object) => void
  onPolygonUpdated: (polygonId: string, geometry: object) => void
  onSplitLine: (start: [number, number], end: [number, number]) => void
  onBoundaryUpdated: (geometry: object) => void
  onBoundaryRedrawn: (geometry: object) => void
}

interface DragLayerEntry {
  layer: L.Layer
  polygonId: string
}

interface MoveUpdate {
  polygonId: string
  geometry: object
}

function centroidOf(geo: ReturnType<L.Polygon['toGeoJSON']>): [number, number] {
  const coords = (geo.geometry as GeoJSON.Polygon).coordinates[0]
  const lng = coords.reduce((s, c) => s + c[0], 0) / coords.length
  const lat = coords.reduce((s, c) => s + c[1], 0) / coords.length
  return [lng, lat]
}

export function useGeoman(
  map: L.Map | null,
  mode: EditorMode,
  selectedPolygonId: string | null,
  callbacks: GeomanCallbacks,
) {
  const cbRef = useRef(callbacks)
  cbRef.current = callbacks
  const modeRef = useRef(mode)
  modeRef.current = mode

  // Register pm:create once on map mount
  useEffect(() => {
    if (!map) return

    const onPmCreate = (e: unknown) => {
      const ev = e as { shape: string; layer: L.Layer }
      const currentMode = modeRef.current
      if (ev.shape === 'Line') {
        const pts = (ev.layer as L.Polyline).getLatLngs() as L.LatLng[]
        if (pts.length >= 2) {
          cbRef.current.onSplitLine(
            [pts[0].lng, pts[0].lat],
            [pts[pts.length - 1].lng, pts[pts.length - 1].lat],
          )
        }
      } else if (currentMode === 'redrawBoundary') {
        cbRef.current.onBoundaryRedrawn((ev.layer as L.Polygon).toGeoJSON().geometry)
      } else if (currentMode === 'draw') {
        cbRef.current.onPolygonCreated((ev.layer as L.Polygon).toGeoJSON().geometry)
      }
      map.removeLayer(ev.layer)
    }

    map.on('pm:create', onPmCreate)
    return () => { map.off('pm:create', onPmCreate) }
  }, [map])

  // Switch geoman draw mode when mode changes
  useEffect(() => {
    if (!map) return
    map.pm.disableDraw()
    if (mode === 'draw') {
      map.pm.enableDraw('Polygon', { snappable: true, snapDistance: 15 })
    } else if (mode === 'split' && selectedPolygonId) {
      map.pm.enableDraw('Line', {
        snappable: true,
        snapDistance: 15,
        templineStyle: { color: '#ef4444', weight: 2, dashArray: '6 4' } as L.PathOptions,
        hintlineStyle: { color: '#ef4444', weight: 2, dashArray: '6 4' } as L.PathOptions,
      } as Parameters<typeof map.pm.enableDraw>[1])
    } else if (mode === 'redrawBoundary') {
      map.pm.enableDraw('Polygon', { snappable: true, snapDistance: 15 })
    }
  }, [map, mode, selectedPolygonId])

  /** Enable vertex editing on a single parking polygon layer. */
  const enableLayerEdit = (layer: L.Layer, polygonId: string): (() => void) => {
    const pm = (layer as unknown as { pm?: { enable: (o?: object) => void; disable: () => void } }).pm
    if (!pm) return () => {}
    pm.enable({ allowSelfIntersection: false })
    const onUpdate = (e: unknown) => {
      const ev = e as { layer: L.Layer }
      cbRef.current.onPolygonUpdated(polygonId, (ev.layer as L.Polygon).toGeoJSON().geometry)
    }
    layer.on('pm:update', onUpdate)
    return () => { pm.disable(); layer.off('pm:update', onUpdate) }
  }

  /** Enable vertex editing on the boundary layer. pm:update fires on each drag commit. */
  const enableBoundaryEdit = (layer: L.Layer): (() => void) => {
    const pm = (layer as unknown as { pm?: { enable: (o?: object) => void; disable: () => void } }).pm
    if (!pm) return () => {}
    pm.enable({ allowSelfIntersection: false })
    const onUpdate = (e: unknown) => {
      const ev = e as { layer: L.Layer }
      cbRef.current.onBoundaryUpdated((ev.layer as L.Polygon).toGeoJSON().geometry)
    }
    layer.on('pm:update', onUpdate)
    return () => { pm.disable(); layer.off('pm:update', onUpdate) }
  }

  /**
   * Enable drag-to-move on a set of polygon layers (used in Select mode).
   * Dragging any one polygon moves all others by the same delta simultaneously.
   * Returns cleanup that disables drag mode and removes listeners.
   */
  const enableLayersDrag = (
    layersWithIds: DragLayerEntry[],
    onMoveEnd: (updates: MoveUpdate[]) => void,
  ): (() => void) => {
    if (!map || layersWithIds.length === 0) return () => {}
    map.pm.enableGlobalDragMode()

    const startCoords = new Map<string, number[][][]>()
    let anchorId: string | null = null
    let anchorStart: [number, number] | null = null

    layersWithIds.forEach(({ layer, polygonId }) => {
      layer.on('pm:dragstart', () => {
        anchorId = polygonId
        const geo = (layer as L.Polygon).toGeoJSON()
        anchorStart = centroidOf(geo)
        layersWithIds.forEach(({ layer: l, polygonId: pid }) => {
          startCoords.set(pid, (l as L.Polygon).toGeoJSON().geometry.coordinates as number[][][])
        })
      })

      layer.on('pm:drag', () => {
        if (anchorId !== polygonId || !anchorStart) return
        const geo = (layer as L.Polygon).toGeoJSON()
        const cur = centroidOf(geo)
        const dLng = cur[0] - anchorStart[0]
        const dLat = cur[1] - anchorStart[1]
        layersWithIds
          .filter(({ polygonId: pid }) => pid !== polygonId)
          .forEach(({ layer: l, polygonId: pid }) => {
            const orig = startCoords.get(pid)
            if (!orig) return
            const shifted = orig.map(ring => ring.map(([x, y]) => [x + dLng, y + dLat]))
            ;(l as L.Polygon).setLatLngs(
              shifted.map(ring => ring.map(([x, y]) => L.latLng(y, x))),
            )
          })
      })

      layer.on('pm:dragend', () => {
        if (anchorId !== polygonId) return
        const updates = layersWithIds.map(({ layer: l, polygonId: pid }) => ({
          polygonId: pid,
          geometry: (l as L.Polygon).toGeoJSON().geometry,
        }))
        onMoveEnd(updates)
        anchorId = null
        anchorStart = null
        startCoords.clear()
      })
    })

    return () => {
      map.pm.disableGlobalDragMode()
      layersWithIds.forEach(({ layer }) => {
        layer.off('pm:dragstart')
        layer.off('pm:drag')
        layer.off('pm:dragend')
      })
    }
  }

  return { enableLayerEdit, enableBoundaryEdit, enableLayersDrag }
}
