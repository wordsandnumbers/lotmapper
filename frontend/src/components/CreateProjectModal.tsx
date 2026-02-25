import { useState, useRef, useEffect, useCallback } from 'react'
import { MapContainer, TileLayer, GeoJSON, useMap, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import { projectsApi } from '../services/api'

interface Props {
  onClose: () => void
  onCreated: () => void
}

// Component to handle rectangle drawing manually (more reliable than EditControl for rectangles)
function RectangleDrawer({
  onBoundsSelected
}: {
  onBoundsSelected: (bounds: { min_lat: number; min_lng: number; max_lat: number; max_lng: number }) => void
}) {
  const map = useMap()
  const [isDrawing, setIsDrawing] = useState(false)
  const [startPoint, setStartPoint] = useState<L.LatLng | null>(null)
  const rectangleRef = useRef<L.Rectangle | null>(null)
  const previewRef = useRef<L.Rectangle | null>(null)

  useMapEvents({
    mousedown(e) {
      if (!isDrawing) return
      setStartPoint(e.latlng)
      // Create preview rectangle
      const startLatLng: L.LatLngTuple = [e.latlng.lat, e.latlng.lng]
      previewRef.current = L.rectangle([startLatLng, startLatLng], {
        color: '#3388ff',
        weight: 2,
        fillOpacity: 0.2,
        dashArray: '5, 5',
      }).addTo(map)
    },
    mousemove(e) {
      if (!isDrawing || !startPoint || !previewRef.current) return
      previewRef.current.setBounds(L.latLngBounds(startPoint, e.latlng))
    },
    mouseup(e) {
      if (!isDrawing || !startPoint) return

      // Remove preview
      if (previewRef.current) {
        map.removeLayer(previewRef.current)
        previewRef.current = null
      }

      // Remove old rectangle
      if (rectangleRef.current) {
        map.removeLayer(rectangleRef.current)
      }

      // Create final rectangle
      const bounds = L.latLngBounds(startPoint, e.latlng)
      rectangleRef.current = L.rectangle(bounds, {
        color: '#3388ff',
        weight: 2,
        fillOpacity: 0.3,
      }).addTo(map)

      onBoundsSelected({
        min_lat: bounds.getSouth(),
        min_lng: bounds.getWest(),
        max_lat: bounds.getNorth(),
        max_lng: bounds.getEast(),
      })

      setIsDrawing(false)
      setStartPoint(null)
      map.dragging.enable()
    },
  })

  const startDrawing = useCallback(() => {
    setIsDrawing(true)
    map.dragging.disable()
  }, [map])

  const clearRectangle = useCallback(() => {
    if (rectangleRef.current) {
      map.removeLayer(rectangleRef.current)
      rectangleRef.current = null
    }
    onBoundsSelected(null as unknown as { min_lat: number; min_lng: number; max_lat: number; max_lng: number })
  }, [map, onBoundsSelected])

  // Add custom control
  useEffect(() => {
    const DrawControl = L.Control.extend({
      onAdd() {
        const container = L.DomUtil.create('div', 'leaflet-bar leaflet-control')

        const drawBtn = L.DomUtil.create('a', '', container)
        drawBtn.innerHTML = '▢'
        drawBtn.href = '#'
        drawBtn.title = 'Draw rectangle'
        drawBtn.style.cssText = 'font-size: 18px; font-weight: bold; display: flex; align-items: center; justify-content: center; width: 30px; height: 30px;'
        L.DomEvent.on(drawBtn, 'click', (e) => {
          L.DomEvent.preventDefault(e)
          startDrawing()
        })

        const clearBtn = L.DomUtil.create('a', '', container)
        clearBtn.innerHTML = '✕'
        clearBtn.href = '#'
        clearBtn.title = 'Clear rectangle'
        clearBtn.style.cssText = 'font-size: 14px; font-weight: bold; display: flex; align-items: center; justify-content: center; width: 30px; height: 30px;'
        L.DomEvent.on(clearBtn, 'click', (e) => {
          L.DomEvent.preventDefault(e)
          clearRectangle()
        })

        return container
      },
    })

    const control = new DrawControl({ position: 'topright' })
    map.addControl(control)

    return () => {
      map.removeControl(control)
    }
  }, [map, startDrawing, clearRectangle])

  // Show cursor change when drawing
  useEffect(() => {
    const container = map.getContainer()
    if (isDrawing) {
      container.style.cursor = 'crosshair'
    } else {
      container.style.cursor = ''
    }
  }, [isDrawing, map])

  return null
}

// US States outline style
const statesStyle = {
  color: '#ffffff',
  weight: 1,
  fillOpacity: 0,
  opacity: 0.5,
}

export default function CreateProjectModal({ onClose, onCreated }: Props) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [bounds, setBounds] = useState<{
    min_lat: number
    min_lng: number
    max_lat: number
    max_lng: number
  } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [statesGeoJson, setStatesGeoJson] = useState<GeoJSON.FeatureCollection | null>(null)

  // Load US states GeoJSON
  useEffect(() => {
    fetch('https://raw.githubusercontent.com/PublicaMundi/MappingAPI/master/data/geojson/us-states.json')
      .then(res => res.json())
      .then(data => setStatesGeoJson(data))
      .catch(err => console.error('Failed to load states:', err))
  }, [])

  const handleBoundsSelected = (newBounds: { min_lat: number; min_lng: number; max_lat: number; max_lng: number } | null) => {
    setBounds(newBounds)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (!name.trim()) {
      setError('Project name is required')
      return
    }

    if (!bounds) {
      setError('Please draw a bounding box on the map')
      return
    }

    setLoading(true)

    try {
      await projectsApi.create({
        name: name.trim(),
        description: description.trim() || undefined,
        bounds,
      })
      onCreated()
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      setError(error.response?.data?.detail || 'Failed to create project')
    } finally {
      setLoading(false)
    }
  }

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose()
    }
  }

  return (
    <div
      className="fixed inset-0 bg-gray-600 bg-opacity-50 flex items-center justify-center z-50"
      onClick={handleBackdropClick}
    >
      <div className="bg-white rounded-lg shadow-xl w-full max-w-4xl max-h-[90vh] overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center">
          <h2 className="text-xl font-semibold text-gray-900">Create New Project</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-2xl leading-none"
            aria-label="Close"
          >
            &times;
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="p-6 space-y-4 overflow-y-auto max-h-[calc(90vh-140px)]">
            {error && (
              <div className="bg-red-50 border border-red-400 text-red-700 px-4 py-3 rounded">
                {error}
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-gray-700">
                Project Name
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                placeholder="Downtown Area 1"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">
                Description (optional)
              </label>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                placeholder="Parking lots in the downtown business district"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Draw Bounding Box
              </label>
              <p className="text-sm text-gray-500 mb-2">
                Click the rectangle button, then click and drag on the map to select an area.
              </p>
              <div className="h-96 border border-gray-300 rounded-md overflow-hidden">
                <MapContainer
                  center={[39.8283, -98.5795]}
                  zoom={4}
                  style={{ height: '100%', width: '100%' }}
                >
                  <TileLayer
                    attribution='&copy; <a href="https://www.esri.com/">Esri</a>'
                    url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
                  />
                  {statesGeoJson && (
                    <GeoJSON data={statesGeoJson} style={statesStyle} />
                  )}
                  <RectangleDrawer onBoundsSelected={handleBoundsSelected} />
                </MapContainer>
              </div>
              {bounds && (
                <p className="text-sm text-green-600 mt-2">
                  Bounding box selected: {bounds.min_lat.toFixed(4)}, {bounds.min_lng.toFixed(4)} to{' '}
                  {bounds.max_lat.toFixed(4)}, {bounds.max_lng.toFixed(4)}
                </p>
              )}
            </div>
          </div>

          <div className="px-6 py-4 border-t border-gray-200 flex justify-end space-x-3">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !bounds}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium disabled:opacity-50"
            >
              {loading ? 'Creating...' : 'Create Project'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
