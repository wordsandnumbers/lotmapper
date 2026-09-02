import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { MapContainer, TileLayer, GeoJSON, useMap } from 'react-leaflet'
import L from 'leaflet'
// @ts-expect-error turf types don't resolve with moduleResolution:bundler
import { booleanIntersects, union as turfUnion } from '@turf/turf'
import { projectsApi, polygonsApi, inferenceApi, inferenceStreamUrl } from '../services/api'
import { useAuthStore } from '../store/auth'
import { useGeoman } from '../hooks/useGeoman'
import MapToolbar, { type EditorMode } from '../components/MapToolbar'

interface Project {
  id: string
  name: string
  description: string | null
  status: string
  bounds: GeoJSON.Polygon | GeoJSON.MultiPolygon
}

interface GeoJSONFeatureCollection {
  type: 'FeatureCollection'
  features: Array<{
    type: 'Feature'
    id: string
    geometry: { type: string; coordinates: number[][][] }
    properties: Record<string, unknown>
  }>
}

type CvFilter = 'all' | 'intersect' | 'difference'

// ─── Inner map components ────────────────────────────────────────────────────

function FitBounds({ bounds }: { bounds: L.LatLngBoundsExpression }) {
  const map = useMap()
  // Only fit on initial mount
  useEffect(() => { map.fitBounds(bounds) }, []) // eslint-disable-line react-hooks/exhaustive-deps
  return null
}

function MapReadyHandler({ onMapReady }: { onMapReady: (map: L.Map) => void }) {
  const map = useMap()
  useEffect(() => { onMapReady(map) }, [map, onMapReady])
  return null
}

/** Shift+drag draws a selection rectangle; releases call onComplete with the bounds. */
function LassoSelector({ onComplete }: { onComplete: (bounds: L.LatLngBounds) => void }) {
  const map = useMap()
  const onCompleteRef = useRef(onComplete)
  onCompleteRef.current = onComplete

  useEffect(() => {
    let startPt: L.Point | null = null
    let rect: L.Rectangle | null = null

    const onDown = (e: MouseEvent) => {
      if (!e.shiftKey) return
      e.preventDefault()
      startPt = map.mouseEventToContainerPoint(e)
      map.dragging.disable()
    }
    const onMove = (e: MouseEvent) => {
      if (!startPt) return
      const cur = map.mouseEventToContainerPoint(e)
      const bounds = L.latLngBounds(
        map.containerPointToLatLng(startPt),
        map.containerPointToLatLng(cur),
      )
      if (rect) { rect.setBounds(bounds) } else {
        rect = L.rectangle(bounds, { color: '#3388ff', weight: 1, fillOpacity: 0.1, dashArray: '4 4' }).addTo(map)
      }
    }
    const onUp = (e: MouseEvent) => {
      if (!startPt) return
      const cur = map.mouseEventToContainerPoint(e)
      const bounds = L.latLngBounds(
        map.containerPointToLatLng(startPt),
        map.containerPointToLatLng(cur),
      )
      if (rect) { map.removeLayer(rect); rect = null }
      startPt = null
      map.dragging.enable()
      // Only trigger if the drag had some area (not just a shift+click)
      if (bounds.getNorth() !== bounds.getSouth() || bounds.getEast() !== bounds.getWest()) {
        onCompleteRef.current(bounds)
      }
    }

    const container = map.getContainer()
    container.addEventListener('mousedown', onDown)
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      container.removeEventListener('mousedown', onDown)
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [map])
  return null
}

/** Click on empty map area (not on a polygon) clears selection.
 *  Uses a native DOM listener to bypass geoman's drag-mode event interception. */
function MapClickClearHandler({ onClear }: { onClear: () => void }) {
  const map = useMap()
  const onClearRef = useRef(onClear)
  onClearRef.current = onClear
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      const target = e.target as Element
      if (!target.closest('.leaflet-interactive')) {
        onClearRef.current()
      }
    }
    map.getContainer().addEventListener('click', handler)
    return () => map.getContainer().removeEventListener('click', handler)
  }, [map])
  return null
}

// ─── Editor ─────────────────────────────────────────────────────────────────

export default function Editor() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const { user } = useAuthStore()

  const [project, setProject] = useState<Project | null>(null)
  const [polygons, setPolygons] = useState<GeoJSONFeatureCollection | null>(null)
  const [osmPolygons, setOsmPolygons] = useState<GeoJSONFeatureCollection | null>(null)
  const [showOsmLayer, setShowOsmLayer] = useState(true)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [running, setRunning] = useState(false)

  // Multi-select state
  const [selectedPolygonIds, setSelectedPolygonIds] = useState<Set<string>>(new Set())
  const [focusedPolygonId, setFocusedPolygonId] = useState<string | null>(null)

  const [activeMode, setActiveMode] = useState<EditorMode>('select')
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [inferenceProgress, setInferenceProgress] = useState(0)
  const [inferenceMessage, setInferenceMessage] = useState('')
  const [pendingBoundary, setPendingBoundary] = useState<object | null>(null)
  const [boundaryModified, setBoundaryModified] = useState(false)
  const [map, setMap] = useState<L.Map | null>(null)
  const [polygonLoadCount, setPolygonLoadCount] = useState(0)
  const [basemap, setBasemap] = useState<'satellite' | 'streets' | 'hybrid'>('satellite')
  const [cvFilter, setCvFilter] = useState<CvFilter>('all')

  // Refs
  const activeModeRef = useRef<EditorMode>('select')
  activeModeRef.current = activeMode
  const focusedPolygonIdRef = useRef<string | null>(null)
  focusedPolygonIdRef.current = focusedPolygonId
  const selectedPolygonIdsRef = useRef<Set<string>>(new Set())
  selectedPolygonIdsRef.current = selectedPolygonIds
  const activeEditCleanupRef = useRef<(() => void) | null>(null)
  const boundaryEditCleanupRef = useRef<(() => void) | null>(null)
  const boundaryLayerRef = useRef<L.GeoJSON | null>(null)
  const enableLayerEditRef = useRef<((layer: L.Layer, id: string) => () => void) | null>(null)
  const enableLayersDragRef = useRef<typeof useGeoman extends (...args: unknown[]) => infer R ? (R extends { enableLayersDrag: infer F } ? F : never) : never>(null as unknown as never)
  const layersByIdRef = useRef<Map<string, L.Layer>>(new Map())

  const canEdit = project?.status === 'review' || project?.status === 'pending'

  // Clear layer refs when polygons reload
  useEffect(() => { layersByIdRef.current.clear() }, [polygonLoadCount])

  // CV polygon IDs that intersect at least one OSM polygon
  const intersectingIds = useMemo(() => {
    if (!polygons || !osmPolygons || osmPolygons.features.length === 0) return new Set<string>()
    const result = new Set<string>()
    for (const cvF of polygons.features) {
      const id = cvF.properties?.polygon_id as string
      if (!id) continue
      for (const osmF of osmPolygons.features) {
        try {
          if (booleanIntersects(cvF as GeoJSON.Feature, osmF as GeoJSON.Feature)) {
            result.add(id); break
          }
        } catch { /* ignore invalid geometries */ }
      }
    }
    return result
  }, [polygons, osmPolygons])

  const loadData = useCallback(async () => {
    if (!projectId) return
    try {
      const [projectData, polygonData] = await Promise.all([
        projectsApi.get(projectId),
        polygonsApi.getForProject(projectId),
      ])
      setProject(projectData)
      const cvFeatures = polygonData.features.filter(
        (f: { properties: Record<string, unknown> }) => f.properties?.source !== 'osm',
      )
      const osmFeatures = polygonData.features.filter(
        (f: { properties: Record<string, unknown> }) => f.properties?.source === 'osm',
      )
      setPolygons({ ...polygonData, features: cvFeatures })
      setOsmPolygons(osmFeatures.length > 0 ? { ...polygonData, features: osmFeatures } : null)
      setPolygonLoadCount(n => n + 1)
    } catch (error) {
      console.error('Failed to load data:', error)
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => { loadData() }, [loadData])

  // SSE progress stream
  useEffect(() => {
    if (project?.status !== 'processing') return
    const token = useAuthStore.getState().token
    if (!token || !projectId) return
    setInferenceProgress(0)
    setInferenceMessage('Queued...')
    const es = new EventSource(inferenceStreamUrl(projectId, token))
    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        if (data.progress !== undefined) setInferenceProgress(data.progress)
        if (data.message) setInferenceMessage(data.message)
        if (data.status === 'completed' || data.status === 'failed' || data.status === 'cancelled') {
          es.close()
          loadData()
          if (data.status === 'completed') setTimeout(() => loadData(), 1500)
        }
      } catch { /* ignore */ }
    }
    es.onerror = () => es.close()
    return () => es.close()
  }, [project?.status, projectId, loadData])

  // Wire geoman
  const { enableLayerEdit, enableBoundaryEdit, enableLayersDrag } = useGeoman(
    map, activeMode, focusedPolygonId,
    {
      onPolygonCreated: async (geometry) => {
        if (!projectId) return
        setSaving(true)
        try {
          await polygonsApi.create(projectId, geometry as GeoJSON.Geometry)
          loadData()
        } catch (e) { console.error('Failed to create polygon:', e) }
        finally { setSaving(false); setActiveMode('select') }
      },
      onPolygonUpdated: async (polygonId, geometry) => {
        setSaving(true)
        try {
          await polygonsApi.update(polygonId, { geometry: geometry as GeoJSON.Geometry })
          loadData()
        } catch (e) { console.error('Failed to update polygon:', e) }
        finally { setSaving(false) }
      },
      onSplitLine: async (start, end) => {
        const id = focusedPolygonIdRef.current
        if (!id) return
        setSaving(true)
        try {
          await polygonsApi.split(id, start, end)
          loadData()
        } catch (e) { console.error('Failed to split polygon:', e) }
        finally {
          setSaving(false)
          setActiveMode('select')
          setFocusedPolygonId(null)
          setSelectedPolygonIds(new Set())
        }
      },
      onBoundaryUpdated: (geometry) => { setPendingBoundary(geometry); setBoundaryModified(true) },
      onBoundaryRedrawn: async (geometry) => {
        if (!projectId) return
        setSaving(true)
        try {
          await projectsApi.update(projectId, { bounds_polygon: geometry })
          setBoundaryModified(false); setPendingBoundary(null)
          loadData()
        } catch (e) { console.error('Failed to redraw boundary:', e) }
        finally { setSaving(false); setActiveMode('select') }
      },
    },
  )

  enableLayerEditRef.current = enableLayerEdit
  enableLayersDragRef.current = enableLayersDrag as typeof enableLayersDragRef.current

  // Disable vertex edit when leaving edit mode
  useEffect(() => {
    if (activeMode !== 'edit') {
      activeEditCleanupRef.current?.()
      activeEditCleanupRef.current = null
    }
  }, [activeMode])

  // Enable boundary editing
  useEffect(() => {
    if (activeMode === 'editBoundary') {
      const layers = boundaryLayerRef.current?.getLayers() ?? []
      if (layers.length > 0) boundaryEditCleanupRef.current = enableBoundaryEdit(layers[0])
    } else {
      boundaryEditCleanupRef.current?.()
      boundaryEditCleanupRef.current = null
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeMode])

  // Enable drag-to-move when in select mode with a selection
  useEffect(() => {
    if (activeMode !== 'select' || selectedPolygonIds.size === 0) return
    const layersWithIds = [...selectedPolygonIds]
      .map(id => ({ layer: layersByIdRef.current.get(id)!, polygonId: id }))
      .filter(x => x.layer)
    if (layersWithIds.length === 0) return

    return enableLayersDrag(layersWithIds, async (updates) => {
      setSaving(true)
      try {
        await Promise.all(updates.map(({ polygonId, geometry }) =>
          polygonsApi.update(polygonId, { geometry: geometry as GeoJSON.Geometry }),
        ))
        loadData()
      } catch (e) { console.error('Failed to move polygons:', e) }
      finally { setSaving(false) }
    })
  // enableLayersDrag identity is stable (closure over map via hook)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeMode, selectedPolygonIds])

  // ─── Handlers ───────────────────────────────────────────────────────────────

  const handleModeChange = (newMode: EditorMode) => {
    setActiveMode(prev => prev === newMode ? 'select' : newMode)
  }

  const handleBulkDelete = async () => {
    if (selectedPolygonIds.size === 0) return
    setSaving(true)
    try {
      await Promise.all([...selectedPolygonIds].map(id => polygonsApi.delete(id)))
      setSelectedPolygonIds(new Set())
      setFocusedPolygonId(null)
      loadData()
    } catch (e) { console.error('Failed to delete polygons:', e) }
    finally { setSaving(false) }
  }

  const handleMerge = async () => {
    if (selectedPolygonIds.size < 2 || !projectId || !polygons) return
    const features = polygons.features.filter(f =>
      selectedPolygonIds.has(f.properties?.polygon_id as string),
    )
    let merged = features[0] as GeoJSON.Feature
    for (let i = 1; i < features.length; i++) {
      try { merged = turfUnion(merged, features[i] as GeoJSON.Feature) ?? merged } catch { /* skip */ }
    }
    setSaving(true)
    try {
      await polygonsApi.create(projectId, (merged as GeoJSON.Feature).geometry)
      await Promise.all([...selectedPolygonIds].map(id => polygonsApi.delete(id)))
      setSelectedPolygonIds(new Set())
      setFocusedPolygonId(null)
      loadData()
    } catch (e) { console.error('Failed to merge polygons:', e) }
    finally { setSaving(false) }
  }

  const handleSaveBoundary = async () => {
    if (!projectId || !pendingBoundary) return
    setSaving(true)
    try {
      await projectsApi.update(projectId, { bounds_polygon: pendingBoundary })
      setBoundaryModified(false); setPendingBoundary(null)
      boundaryEditCleanupRef.current?.(); boundaryEditCleanupRef.current = null
      setActiveMode('select'); loadData()
    } catch (e) { console.error('Failed to save boundary:', e) }
    finally { setSaving(false) }
  }

  const handleDiscardBoundary = () => {
    setBoundaryModified(false); setPendingBoundary(null)
    boundaryEditCleanupRef.current?.(); boundaryEditCleanupRef.current = null
    setActiveMode('select'); loadData()
  }

  const handleRunInference = async () => {
    if (!projectId) return
    setRunning(true)
    try { await inferenceApi.run(projectId); loadData() }
    catch (e) { console.error('Failed to start inference:', e) }
    finally { setRunning(false) }
  }

  const handleCancelInference = async () => {
    if (!projectId) return
    try { await inferenceApi.cancel(projectId); loadData() }
    catch (e) { console.error('Failed to cancel inference:', e) }
  }

  const handleApprove = async () => {
    if (!projectId) return
    setSaving(true)
    try { await projectsApi.update(projectId, { status: 'approved' }); loadData() }
    catch (e) { console.error('Failed to approve:', e) }
    finally { setSaving(false) }
  }

  const handleSubmitForReview = async () => {
    if (!projectId) return
    setSaving(true)
    try { await projectsApi.update(projectId, { status: 'review' }); loadData() }
    catch (e) { console.error('Failed to submit:', e) }
    finally { setSaving(false) }
  }

  const handleDeleteProject = async () => {
    if (!projectId) return
    setDeleting(true)
    try { await projectsApi.delete(projectId); navigate('/dashboard') }
    catch (e) {
      console.error('Failed to delete project:', e)
      alert('Failed to delete project. Please try again.')
      setDeleting(false); setShowDeleteConfirm(false)
    }
  }

  const handleLassoComplete = useCallback((bounds: L.LatLngBounds) => {
    if (!polygons) return
    const boundsFeature: GeoJSON.Feature = {
      type: 'Feature',
      geometry: {
        type: 'Polygon',
        coordinates: [[
          [bounds.getWest(), bounds.getNorth()],
          [bounds.getEast(), bounds.getNorth()],
          [bounds.getEast(), bounds.getSouth()],
          [bounds.getWest(), bounds.getSouth()],
          [bounds.getWest(), bounds.getNorth()],
        ]],
      },
      properties: {},
    }
    setSelectedPolygonIds(prev => {
      const next = new Set(prev)
      for (const f of polygons.features) {
        const id = f.properties?.polygon_id as string
        if (id) {
          try { if (booleanIntersects(f, boundsFeature)) next.add(id) } catch { /* ignore */ }
        }
      }
      return next
    })
  }, [polygons])

  // ─── onEachFeature — click interaction ─────────────────────────────────────

  const onEachFeature = useCallback((feature: GeoJSON.Feature, layer: L.Layer) => {
    const id = feature.properties?.polygon_id as string
    layersByIdRef.current.set(id, layer)

    layer.on('click', (e) => {
      L.DomEvent.stopPropagation(e as L.LeafletEvent)
      const me = e as unknown as MouseEvent
      const multiKey = me.ctrlKey || me.metaKey

      if (multiKey) {
        setSelectedPolygonIds(prev => {
          const next = new Set(prev)
          next.has(id) ? next.delete(id) : next.add(id)
          return next
        })
      } else {
        setSelectedPolygonIds(new Set([id]))
        setFocusedPolygonId(id)
        if (activeModeRef.current === 'edit') {
          activeEditCleanupRef.current?.()
          activeEditCleanupRef.current = enableLayerEditRef.current?.(layer, id) ?? null
        }
      }
    })
  }, [])

  // ─── Polygon style ──────────────────────────────────────────────────────────

  const polygonStyle = (feature: GeoJSON.Feature | undefined) => {
    const id = feature?.properties?.polygon_id as string
    const isSelected = selectedPolygonIds.has(id)
    const isFocused = id === focusedPolygonId

    if (isFocused) return { color: '#ff0000', weight: 3, fillOpacity: 0.35 }
    if (isSelected) return { color: '#3388ff', weight: 3, fillOpacity: 0.45 }

    if (selectedPolygonIds.size > 0) {
      return { color: '#94a3b8', weight: 1, fillOpacity: 0.08, opacity: 0.4 }
    }

    if (cvFilter !== 'all' && osmPolygons) {
      const inIntersect = intersectingIds.has(id)
      const isActive = cvFilter === 'intersect' ? inIntersect : !inIntersect
      if (isActive) return { color: '#3388ff', weight: 2, fillOpacity: 0.35 }
      return { color: '#94a3b8', weight: 1, fillOpacity: 0.08, opacity: 0.4 }
    }

    return { color: '#3388ff', weight: 2, fillOpacity: 0.3 }
  }

  // ─── Render ─────────────────────────────────────────────────────────────────

  if (loading) return <div className="flex items-center justify-center h-screen">Loading...</div>
  if (!project) return <div className="flex items-center justify-center h-screen">Project not found</div>

  const allRings =
    project.bounds.type === 'MultiPolygon'
      ? (project.bounds.coordinates as number[][][][]).flat()
      : [(project.bounds.coordinates as number[][][])[0]]
  const allCoords = allRings.flat()
  const lngs = allCoords.map(c => c[0])
  const lats = allCoords.map(c => c[1])
  const mapBounds: L.LatLngBoundsExpression = [
    [Math.min(...lats), Math.min(...lngs)],
    [Math.max(...lats), Math.max(...lngs)],
  ]

  return (
    <div className="h-[calc(100vh-64px)] flex flex-col sm:flex-row">
      {/* Sidebar */}
      <div className="w-full sm:w-80 sm:flex-shrink-0 bg-white/95 shadow-lg ring-1 ring-black/10 p-4 overflow-y-auto max-h-[45vh] sm:max-h-none">
        <button onClick={() => navigate('/dashboard')} className="text-brand-primary hover:text-brand-primaryHover mb-4 flex items-center">
          &larr; Back to Dashboard
        </button>

        <h2 className="text-xl font-semibold mb-2">{project.name}</h2>
        <p className="text-app-body text-sm mb-4">{project.description}</p>

        <div className="mb-4">
          <span className={`px-2 py-1 text-xs font-semibold rounded-full ${
            project.status === 'approved' ? 'bg-green-100 text-green-800'
            : project.status === 'review' ? 'bg-brand-primary/10 text-brand-primary'
            : project.status === 'processing' ? 'bg-yellow-100 text-yellow-800'
            : 'bg-gray-100 text-gray-800'
          }`}>
            {project.status}
          </span>
        </div>

        <div className="space-y-3">
          {project.status === 'pending' && (
            <button onClick={handleRunInference} disabled={running}
              className="w-full bg-brand-primary hover:bg-brand-primaryHover text-white px-4 py-2 rounded-md disabled:opacity-50">
              {running ? 'Starting...' : 'Run Detection'}
            </button>
          )}

          {project.status === 'processing' && (
            <div className="py-4">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center">
                  <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-brand-primary mr-2 flex-shrink-0" />
                  <p className="text-sm text-app-heading font-medium">Processing...</p>
                </div>
                <button onClick={handleCancelInference} className="text-xs text-red-600 hover:text-red-700 font-medium">
                  Cancel
                </button>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2 mb-1">
                <div className="bg-brand-primary h-2 rounded-full transition-all duration-500" style={{ width: `${inferenceProgress}%` }} />
              </div>
              <p className="text-xs text-app-body">{inferenceMessage || 'Queued...'}</p>
            </div>
          )}

          {project.status === 'review' && (user?.role === 'admin' || user?.role === 'owner') && (
            <button onClick={handleApprove} disabled={saving}
              className="w-full bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-md disabled:opacity-50">
              Approve Project
            </button>
          )}

          {project.status === 'pending' && polygons && polygons.features.length > 0 && (
            <button onClick={handleSubmitForReview} disabled={saving}
              className="w-full bg-brand-primary hover:bg-brand-primaryHover text-white px-4 py-2 rounded-md disabled:opacity-50">
              Submit for Review
            </button>
          )}

          {(user?.role === 'admin' || user?.role === 'owner') && (
            <div className="border-t pt-3 mt-3">
              {showDeleteConfirm ? (
                <div className="space-y-2">
                  <p className="text-sm text-app-body">Delete this project and all its polygons?</p>
                  <div className="flex gap-2">
                    <button onClick={handleDeleteProject} disabled={deleting}
                      className="flex-1 bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-md text-sm disabled:opacity-50">
                      {deleting ? 'Deleting...' : 'Confirm Delete'}
                    </button>
                    <button onClick={() => setShowDeleteConfirm(false)} disabled={deleting}
                      className="flex-1 bg-gray-200 hover:bg-gray-300 text-app-heading px-4 py-2 rounded-md text-sm">
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <button onClick={() => setShowDeleteConfirm(true)}
                  className="w-full bg-red-50 hover:bg-red-100 text-red-700 px-4 py-2 rounded-md text-sm">
                  Delete Project
                </button>
              )}
            </div>
          )}
        </div>

        {/* Counts + OSM filter */}
        {(project.status === 'review' || project.status === 'approved') && (
          <div className="mt-6 text-sm text-app-body space-y-1">
            <div>
              {polygons?.features.length ?? 0} CV lots
              {selectedPolygonIds.size > 0 && (
                <span className="ml-1 text-brand-primary font-medium">({selectedPolygonIds.size} selected)</span>
              )}
            </div>
            {osmPolygons ? (
              <>
                <label className="flex items-center cursor-pointer">
                  <input type="checkbox" checked={showOsmLayer} onChange={e => setShowOsmLayer(e.target.checked)} className="mr-2" />
                  {osmPolygons.features.length} OSM reference lots
                </label>
                <div className="flex gap-1 mt-2">
                  {([
                    ['all', 'All'],
                    ['intersect', 'CV ∩ OSM'],
                    ['difference', 'CV \\ OSM'],
                  ] as [CvFilter, string][]).map(([filterMode, label]) => (
                    <button key={filterMode}
                      onClick={() => {
                        if (filterMode === 'all') {
                          setCvFilter('all')
                          setSelectedPolygonIds(new Set())
                        } else if (filterMode === 'intersect') {
                          setCvFilter('intersect')
                          setSelectedPolygonIds(new Set(intersectingIds))
                        } else {
                          setCvFilter('difference')
                          const diff = new Set(
                            polygons?.features
                              .map(f => f.properties?.polygon_id as string)
                              .filter(id => id && !intersectingIds.has(id)) ?? [],
                          )
                          setSelectedPolygonIds(diff)
                        }
                      }}
                      className={`flex-1 px-1.5 py-1 text-xs rounded transition-colors ${
                        cvFilter === filterMode ? 'bg-brand-primary text-white' : 'bg-gray-100 hover:bg-gray-200 text-app-heading'
                      }`}>
                      {label}
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <div className="text-gray-400 italic">No OSM reference data found</div>
            )}
          </div>
        )}

        {saving && <div className="mt-4 text-sm text-brand-primary">Saving changes...</div>}
      </div>

      {/* Map container */}
      <div className="flex-1 min-h-0 relative">
        {canEdit && (
          <MapToolbar
            mode={activeMode}
            onModeChange={handleModeChange}
            selectionCount={selectedPolygonIds.size}
            canEdit={canEdit}
            boundaryModified={boundaryModified}
            onSaveBoundary={handleSaveBoundary}
            onDiscardBoundary={handleDiscardBoundary}
            onDelete={handleBulkDelete}
            onMerge={handleMerge}
          />
        )}

        {/* Basemap switcher */}
        <div className="absolute bottom-6 left-3 z-[1000] flex gap-1 bg-white shadow-md rounded-lg px-1 py-1 ring-1 ring-black/10 pointer-events-auto">
          {(['satellite', 'streets', 'hybrid'] as const).map(layer => (
            <button key={layer} onClick={() => setBasemap(layer)}
              className={`px-2.5 py-1 text-xs font-medium rounded capitalize transition-colors ${
                basemap === layer ? 'bg-brand-primary text-white' : 'text-app-heading hover:bg-gray-100'
              }`}>
              {layer}
            </button>
          ))}
        </div>

        <MapContainer center={[0, 0]} zoom={2} maxZoom={21} style={{ height: '100%', width: '100%' }}>
          {basemap === 'satellite' && (
            <TileLayer key="satellite" attribution='&copy; <a href="https://maps.google.com">Google Maps</a>'
              url="/api/v1/tiles/{z}/{x}/{y}" maxZoom={21} />
          )}
          {basemap === 'streets' && (
            <TileLayer key="streets" attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={19} />
          )}
          {basemap === 'hybrid' && (
            <>
              <TileLayer key="hybrid-sat" attribution='&copy; <a href="https://maps.google.com">Google Maps</a>'
                url="/api/v1/tiles/{z}/{x}/{y}" maxZoom={21} />
              <TileLayer key="hybrid-roads"
                attribution='&copy; <a href="https://www.esri.com">Esri</a>'
                url="https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}"
                maxZoom={19} opacity={0.9} />
              <TileLayer key="hybrid-labels"
                url="https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}"
                maxZoom={19} opacity={0.9} />
            </>
          )}

          <FitBounds bounds={mapBounds} />
          <MapReadyHandler onMapReady={setMap} />
          <LassoSelector onComplete={handleLassoComplete} />
          <MapClickClearHandler onClear={() => setSelectedPolygonIds(new Set())} />

          {/* Boundary */}
          <GeoJSON
            key={`boundary-${polygonLoadCount}`}
            ref={ref => { boundaryLayerRef.current = ref }}
            data={project.bounds}
            style={{ color: '#fbbf24', weight: 3, fillOpacity: 0, dashArray: '5, 5' }}
          />

          {/* OSM reference — non-interactive */}
          {osmPolygons && showOsmLayer && (
            <GeoJSON
              key={`osm-${osmPolygons.features.length}`}
              data={osmPolygons}
              style={{ color: '#16a34a', weight: 2, fillColor: '#16a34a', fillOpacity: 0.15, dashArray: '4, 4' }}
              interactive={false}
            />
          )}

          {/* CV polygons */}
          {polygons && (
            <GeoJSON
              key={`cv-${polygonLoadCount}-${selectedPolygonIds.size}-${focusedPolygonId}-${cvFilter}`}
              data={polygons}
              style={polygonStyle}
              onEachFeature={onEachFeature}
            />
          )}
        </MapContainer>
      </div>
    </div>
  )
}
