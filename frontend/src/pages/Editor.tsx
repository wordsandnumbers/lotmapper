import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { MapContainer, TileLayer, GeoJSON, FeatureGroup, useMap } from 'react-leaflet'
import { EditControl } from 'react-leaflet-draw'
import L from 'leaflet'
import { projectsApi, polygonsApi, inferenceApi } from '../services/api'
import { useAuthStore } from '../store/auth'

interface Project {
  id: string
  name: string
  description: string | null
  status: string
  bounds: {
    type: string
    coordinates: number[][][]
  }
}

interface GeoJSONFeatureCollection {
  type: 'FeatureCollection'
  features: Array<{
    type: 'Feature'
    id: string
    geometry: {
      type: string
      coordinates: number[][][]
    }
    properties: Record<string, unknown>
  }>
}

// Component to fit map to bounds
function FitBounds({ bounds }: { bounds: L.LatLngBoundsExpression }) {
  const map = useMap()
  useEffect(() => {
    map.fitBounds(bounds)
  }, [map, bounds])
  return null
}

export default function Editor() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const { user } = useAuthStore()

  const [project, setProject] = useState<Project | null>(null)
  const [polygons, setPolygons] = useState<GeoJSONFeatureCollection | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [running, setRunning] = useState(false)
  const [selectedPolygonId, setSelectedPolygonId] = useState<string | null>(null)
  const [splitMode, setSplitMode] = useState(false)
  const [splitStart, setSplitStart] = useState<[number, number] | null>(null)

  const featureGroupRef = useRef<L.FeatureGroup>(null)
  const geoJsonRef = useRef<L.GeoJSON>(null)

  const loadData = useCallback(async () => {
    if (!projectId) return

    try {
      const [projectData, polygonData] = await Promise.all([
        projectsApi.get(projectId),
        polygonsApi.getForProject(projectId),
      ])
      setProject(projectData)
      setPolygons(polygonData)
    } catch (error) {
      console.error('Failed to load data:', error)
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    loadData()
  }, [loadData])

  // Polling for processing status
  useEffect(() => {
    if (project?.status !== 'processing') return

    const interval = setInterval(async () => {
      if (!projectId) return
      const status = await inferenceApi.status(projectId)
      if (status.status !== 'processing') {
        loadData()
      }
    }, 3000)

    return () => clearInterval(interval)
  }, [project?.status, projectId, loadData])

  const handleRunInference = async () => {
    if (!projectId) return
    setRunning(true)
    try {
      await inferenceApi.run(projectId)
      loadData()
    } catch (error) {
      console.error('Failed to start inference:', error)
    } finally {
      setRunning(false)
    }
  }

  const handlePolygonCreated = async (e: L.DrawEvents.Created) => {
    if (!projectId) return
    setSaving(true)
    try {
      const layer = e.layer as L.Polygon
      const geoJson = layer.toGeoJSON()
      await polygonsApi.create(projectId, geoJson.geometry)
      loadData()
    } catch (error) {
      console.error('Failed to create polygon:', error)
    } finally {
      setSaving(false)
    }
  }

  const handlePolygonEdited = async (e: L.DrawEvents.Edited) => {
    setSaving(true)
    try {
      const layers = e.layers
      const updates: Promise<unknown>[] = []

      layers.eachLayer((layer: L.Layer) => {
        const polygon = layer as L.Polygon & { feature?: { properties?: { polygon_id?: string } } }
        const polygonId = polygon.feature?.properties?.polygon_id
        if (polygonId) {
          const geoJson = polygon.toGeoJSON()
          updates.push(polygonsApi.update(polygonId, { geometry: geoJson.geometry }))
        }
      })

      await Promise.all(updates)
      loadData()
    } catch (error) {
      console.error('Failed to update polygons:', error)
    } finally {
      setSaving(false)
    }
  }

  const handlePolygonDeleted = async (e: L.DrawEvents.Deleted) => {
    setSaving(true)
    try {
      const layers = e.layers
      const deletes: Promise<unknown>[] = []

      layers.eachLayer((layer: L.Layer) => {
        const polygon = layer as L.Polygon & { feature?: { properties?: { polygon_id?: string } } }
        const polygonId = polygon.feature?.properties?.polygon_id
        if (polygonId) {
          deletes.push(polygonsApi.delete(polygonId))
        }
      })

      await Promise.all(deletes)
      loadData()
    } catch (error) {
      console.error('Failed to delete polygons:', error)
    } finally {
      setSaving(false)
    }
  }

  const handleMapClick = async (e: L.LeafletMouseEvent) => {
    if (!splitMode || !selectedPolygonId) return

    const point: [number, number] = [e.latlng.lng, e.latlng.lat]

    if (!splitStart) {
      setSplitStart(point)
    } else {
      // Perform split
      setSaving(true)
      try {
        await polygonsApi.split(selectedPolygonId, splitStart, point)
        loadData()
      } catch (error) {
        console.error('Failed to split polygon:', error)
      } finally {
        setSaving(false)
        setSplitMode(false)
        setSplitStart(null)
        setSelectedPolygonId(null)
      }
    }
  }

  const handleApprove = async () => {
    if (!projectId) return
    setSaving(true)
    try {
      await projectsApi.update(projectId, { status: 'approved' })
      loadData()
    } catch (error) {
      console.error('Failed to approve:', error)
    } finally {
      setSaving(false)
    }
  }

  const handleSubmitForReview = async () => {
    if (!projectId) return
    setSaving(true)
    try {
      await projectsApi.update(projectId, { status: 'review' })
      loadData()
    } catch (error) {
      console.error('Failed to submit:', error)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-screen">Loading...</div>
  }

  if (!project) {
    return <div className="flex items-center justify-center h-screen">Project not found</div>
  }

  // Calculate bounds for map fitting
  const coords = project.bounds.coordinates[0]
  const lngs = coords.map((c) => c[0])
  const lats = coords.map((c) => c[1])
  const mapBounds: L.LatLngBoundsExpression = [
    [Math.min(...lats), Math.min(...lngs)],
    [Math.max(...lats), Math.max(...lngs)],
  ]

  const onEachFeature = (feature: GeoJSON.Feature, layer: L.Layer) => {
    layer.on({
      click: () => {
        const polygonId = feature.properties?.polygon_id as string
        setSelectedPolygonId(polygonId)
      },
    })
  }

  const polygonStyle = (feature: GeoJSON.Feature | undefined) => {
    const isSelected = feature?.properties?.polygon_id === selectedPolygonId
    return {
      color: isSelected ? '#ff0000' : '#3388ff',
      weight: isSelected ? 3 : 2,
      fillOpacity: 0.3,
    }
  }

  return (
    <div className="h-[calc(100vh-64px)] flex">
      {/* Sidebar */}
      <div className="w-80 bg-white shadow-lg p-4 overflow-y-auto">
        <button
          onClick={() => navigate('/dashboard')}
          className="text-blue-600 hover:text-blue-800 mb-4 flex items-center"
        >
          &larr; Back to Dashboard
        </button>

        <h2 className="text-xl font-semibold mb-2">{project.name}</h2>
        <p className="text-gray-500 text-sm mb-4">{project.description}</p>

        <div className="mb-4">
          <span
            className={`px-2 py-1 text-xs font-semibold rounded-full ${
              project.status === 'approved'
                ? 'bg-green-100 text-green-800'
                : project.status === 'review'
                ? 'bg-blue-100 text-blue-800'
                : project.status === 'processing'
                ? 'bg-yellow-100 text-yellow-800'
                : 'bg-gray-100 text-gray-800'
            }`}
          >
            {project.status}
          </span>
        </div>

        {/* Actions */}
        <div className="space-y-3">
          {project.status === 'pending' && (
            <button
              onClick={handleRunInference}
              disabled={running}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-md disabled:opacity-50"
            >
              {running ? 'Starting...' : 'Run Detection'}
            </button>
          )}

          {project.status === 'processing' && (
            <div className="text-center py-4">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-2"></div>
              <p className="text-sm text-gray-500">Processing...</p>
            </div>
          )}

          {(project.status === 'review' || project.status === 'pending') && (
            <>
              <div className="border-t pt-3">
                <h3 className="font-medium mb-2">Edit Tools</h3>
                <p className="text-xs text-gray-500 mb-2">
                  Use the drawing tools on the map to edit polygons.
                </p>
              </div>

              {selectedPolygonId && (
                <div className="border-t pt-3">
                  <h3 className="font-medium mb-2">Selected Polygon</h3>
                  <button
                    onClick={() => {
                      setSplitMode(!splitMode)
                      setSplitStart(null)
                    }}
                    className={`w-full px-4 py-2 rounded-md text-sm ${
                      splitMode
                        ? 'bg-red-600 hover:bg-red-700 text-white'
                        : 'bg-gray-200 hover:bg-gray-300 text-gray-700'
                    }`}
                  >
                    {splitMode ? 'Cancel Split' : 'Split Polygon'}
                  </button>
                  {splitMode && (
                    <p className="text-xs text-gray-500 mt-2">
                      {splitStart
                        ? 'Click to set the end point of the split line'
                        : 'Click on the map to set the start point of the split line'}
                    </p>
                  )}
                </div>
              )}
            </>
          )}

          {project.status === 'review' && user?.role === 'admin' && (
            <button
              onClick={handleApprove}
              disabled={saving}
              className="w-full bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-md disabled:opacity-50"
            >
              Approve Project
            </button>
          )}

          {project.status === 'pending' && polygons && polygons.features.length > 0 && (
            <button
              onClick={handleSubmitForReview}
              disabled={saving}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-md disabled:opacity-50"
            >
              Submit for Review
            </button>
          )}
        </div>

        {/* Polygon count */}
        <div className="mt-6 text-sm text-gray-500">
          {polygons?.features.length || 0} polygons detected
        </div>

        {saving && (
          <div className="mt-4 text-sm text-blue-600">Saving changes...</div>
        )}
      </div>

      {/* Map */}
      <div className="flex-1">
        <MapContainer
          center={[0, 0]}
          zoom={2}
          style={{ height: '100%', width: '100%' }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.esri.com/">Esri</a>'
            url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
          />
          <FitBounds bounds={mapBounds} />

          {/* Editable polygons */}
          <FeatureGroup ref={featureGroupRef}>
            <EditControl
              position="topright"
              onCreated={handlePolygonCreated}
              onEdited={handlePolygonEdited}
              onDeleted={handlePolygonDeleted}
              draw={{
                rectangle: false,
                polygon: true,
                circle: false,
                circlemarker: false,
                marker: false,
                polyline: false,
              }}
            />
            {polygons && (
              <GeoJSON
                key={JSON.stringify(polygons)}
                ref={geoJsonRef}
                data={polygons}
                style={polygonStyle}
                onEachFeature={onEachFeature}
              />
            )}
          </FeatureGroup>

          {/* Handle split mode clicks */}
          {splitMode && <MapClickHandler onClick={handleMapClick} />}
        </MapContainer>
      </div>
    </div>
  )
}

// Component to handle map clicks for split mode
function MapClickHandler({ onClick }: { onClick: (e: L.LeafletMouseEvent) => void }) {
  const map = useMap()

  useEffect(() => {
    map.on('click', onClick)
    return () => {
      map.off('click', onClick)
    }
  }, [map, onClick])

  return null
}
