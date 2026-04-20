import { useState, useRef, useEffect, useCallback } from 'react'
import { MapContainer, TileLayer, GeoJSON, useMap, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import { projectsApi, citySearchStreamUrl } from '../services/api'
import { useAuthStore } from '../store/auth'

interface Props {
  onClose: () => void
  onCreated: () => void
}

function sourceLabel(source: string): string {
  switch (source) {
    case 'arcgis_hub': return 'ArcGIS Hub'
    case 'arcgis_online': return 'ArcGIS Online'
    case 'fallback': return 'Estimated'
    default: return source
  }
}

// Freehand polygon drawing tool
// Click to add vertices, double-click to finish (3+ points required)
function PolygonDrawer({
  onPolygonSelected
}: {
  onPolygonSelected: (polygon: GeoJSON.Geometry | null) => void
}) {
  const map = useMap()
  const isDrawingRef = useRef(false)
  const [isDrawing, setIsDrawing] = useState(false)
  const pointsRef = useRef<L.LatLng[]>([])
  const previewLayerRef = useRef<L.Polyline | null>(null)
  const finishedLayerRef = useRef<L.Polygon | null>(null)

  const updatePreview = useCallback(() => {
    if (previewLayerRef.current) {
      map.removeLayer(previewLayerRef.current)
      previewLayerRef.current = null
    }
    const pts = pointsRef.current
    if (pts.length >= 2) {
      previewLayerRef.current = L.polyline(pts, {
        color: '#3388ff',
        weight: 2,
        dashArray: '5, 5',
      }).addTo(map)
    }
  }, [map])

  useMapEvents({
    click(e) {
      if (!isDrawingRef.current) return
      pointsRef.current = [...pointsRef.current, e.latlng]
      updatePreview()
    },
    dblclick() {
      if (!isDrawingRef.current) return
      // Leaflet fires click before dblclick — remove the last point (added by that click)
      const pts = pointsRef.current.slice(0, -1)
      if (pts.length < 3) return

      if (previewLayerRef.current) {
        map.removeLayer(previewLayerRef.current)
        previewLayerRef.current = null
      }
      if (finishedLayerRef.current) {
        map.removeLayer(finishedLayerRef.current)
      }

      finishedLayerRef.current = L.polygon(pts, {
        color: '#3388ff',
        weight: 2,
        fillOpacity: 0.3,
      }).addTo(map)

      const coords = pts.map(p => [p.lng, p.lat])
      coords.push(coords[0]) // close the ring
      onPolygonSelected({ type: 'Polygon', coordinates: [coords] })

      pointsRef.current = []
      isDrawingRef.current = false
      setIsDrawing(false)
      map.dragging.enable()
    },
  })

  const startDrawing = useCallback(() => {
    if (finishedLayerRef.current) {
      map.removeLayer(finishedLayerRef.current)
      finishedLayerRef.current = null
    }
    if (previewLayerRef.current) {
      map.removeLayer(previewLayerRef.current)
      previewLayerRef.current = null
    }
    pointsRef.current = []
    onPolygonSelected(null)
    isDrawingRef.current = true
    setIsDrawing(true)
    map.dragging.disable()
  }, [map, onPolygonSelected])

  const clearPolygon = useCallback(() => {
    if (finishedLayerRef.current) {
      map.removeLayer(finishedLayerRef.current)
      finishedLayerRef.current = null
    }
    if (previewLayerRef.current) {
      map.removeLayer(previewLayerRef.current)
      previewLayerRef.current = null
    }
    pointsRef.current = []
    isDrawingRef.current = false
    setIsDrawing(false)
    onPolygonSelected(null)
    map.dragging.enable()
  }, [map, onPolygonSelected])

  // Add custom control
  useEffect(() => {
    const DrawControl = L.Control.extend({
      onAdd() {
        const container = L.DomUtil.create('div', 'leaflet-bar leaflet-control')

        const drawBtn = L.DomUtil.create('a', '', container)
        drawBtn.innerHTML = '⬠'
        drawBtn.href = '#'
        drawBtn.title = 'Draw polygon — click to add points, double-click to finish'
        drawBtn.style.cssText = 'font-size: 16px; font-weight: bold; display: flex; align-items: center; justify-content: center; width: 30px; height: 30px;'
        L.DomEvent.on(drawBtn, 'click', (e) => {
          L.DomEvent.preventDefault(e)
          startDrawing()
        })

        const clearBtn = L.DomUtil.create('a', '', container)
        clearBtn.innerHTML = '✕'
        clearBtn.href = '#'
        clearBtn.title = 'Clear polygon'
        clearBtn.style.cssText = 'font-size: 14px; font-weight: bold; display: flex; align-items: center; justify-content: center; width: 30px; height: 30px;'
        L.DomEvent.on(clearBtn, 'click', (e) => {
          L.DomEvent.preventDefault(e)
          clearPolygon()
        })

        return container
      },
    })

    const control = new DrawControl({ position: 'topright' })
    map.addControl(control)

    return () => {
      map.removeControl(control)
    }
  }, [map, startDrawing, clearPolygon])

  // Cursor change when drawing
  useEffect(() => {
    const container = map.getContainer()
    container.style.cursor = isDrawing ? 'crosshair' : ''
  }, [isDrawing, map])

  return null
}

// Component to fit map to a GeoJSON polygon's bounds
function FitToPolygon({ geojson }: { geojson: GeoJSON.Geometry }) {
  const map = useMap()
  useEffect(() => {
    try {
      const layer = L.geoJSON(geojson)
      map.fitBounds(layer.getBounds(), { padding: [20, 20] })
    } catch {
      // ignore invalid geometries
    }
  }, [map, geojson])
  return null
}

// US States outline style
const statesStyle = {
  color: '#ffffff',
  weight: 1,
  fillOpacity: 0,
  opacity: 0.5,
}

const resolvedPolygonStyle = {
  color: '#0d9488',
  weight: 2,
  fillColor: '#0d9488',
  fillOpacity: 0.2,
}

type Tab = 'city' | 'draw'

export default function CreateProjectModal({ onClose, onCreated }: Props) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [activeTab, setActiveTab] = useState<Tab>('city')

  // Draw tab state — uses GeoJSON polygon (same as city tab's bounds_polygon)
  const [drawnPolygon, setDrawnPolygon] = useState<GeoJSON.Geometry | null>(null)

  // City search tab state
  const [city, setCity] = useState('')
  const [stateAbbr, setStateAbbr] = useState('')
  const [resolving, setResolving] = useState(false)
  const [resolveMessage, setResolveMessage] = useState('')
  const [resolveError, setResolveError] = useState('')
  const [candidates, setCandidates] = useState<Array<{ name: string; geometry: GeoJSON.Geometry; score: number; source: string }> | null>(null)
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null)
  const [boundsPolygon, setBoundsPolygon] = useState<GeoJSON.Geometry | null>(null)
  const [selectedCandidateName, setSelectedCandidateName] = useState<string | null>(null)

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

  const handleTabChange = (tab: Tab) => {
    setActiveTab(tab)
    if (tab === 'city') {
      setDrawnPolygon(null)
    } else {
      setBoundsPolygon(null)
      setCandidates(null)
      setSelectedCandidateName(null)
    }
    setError('')
  }

  const handleResolveCity = () => {
    if (!city.trim() || !stateAbbr.trim()) {
      setResolveError('Please enter both city and state')
      return
    }
    setResolveError('')
    setResolving(true)
    setResolveMessage('Starting search...')
    setCandidates(null)
    setBoundsPolygon(null)
    setSelectedCandidateName(null)

    const token = useAuthStore.getState().token
    const es = new EventSource(citySearchStreamUrl(city.trim(), stateAbbr.trim(), token!))

    es.onmessage = (e) => {
      const data = JSON.parse(e.data)
      if (data.message) setResolveMessage(data.message)
      if (data.status === 'completed') {
        es.close()
        setCandidates(data.candidates)
        setResolving(false)
        setResolveMessage('')
      } else if (data.status === 'failed') {
        es.close()
        setResolveError(data.error || 'Failed to find city boundaries')
        setResolving(false)
        setResolveMessage('')
      }
    }

    es.onerror = () => {
      es.close()
      setResolveError('Connection error during search')
      setResolving(false)
      setResolveMessage('')
    }
  }

  const handleUseCandidate = (index: number) => {
    if (!candidates) return
    const candidate = candidates[index]
    setBoundsPolygon(candidate.geometry)
    setSelectedCandidateName(candidate.name)
  }

  const handleSearchAgain = () => {
    setCandidates(null)
    setBoundsPolygon(null)
    setSelectedCandidateName(null)
    setCity('')
    setStateAbbr('')
    setResolveError('')
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (!name.trim()) {
      setError('Project name is required')
      return
    }

    if (activeTab === 'draw' && !drawnPolygon) {
      setError('Please draw a polygon on the map')
      return
    }

    if (activeTab === 'city' && !boundsPolygon) {
      setError('Please find and confirm a city boundary')
      return
    }

    setLoading(true)

    try {
      const polygon = activeTab === 'city' ? boundsPolygon : drawnPolygon
      await projectsApi.create({
        name: name.trim(),
        description: description.trim() || undefined,
        bounds_polygon: polygon!,
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

  const submitDisabled = loading || (activeTab === 'draw' ? !drawnPolygon : !boundsPolygon)

  const isFallbackOnly = candidates?.length === 1 && candidates[0].score === -1

  return (
    <div
      className="fixed inset-0 bg-gray-600 bg-opacity-50 flex items-center justify-center z-50"
      onClick={handleBackdropClick}
    >
      <div className="bg-white rounded-lg shadow-xl w-full max-w-6xl max-h-[95vh] overflow-hidden">
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
          <div className="p-6 space-y-4 overflow-y-auto max-h-[calc(95vh-140px)]">
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

            {/* Tabs */}
            <div>
              <div className="flex border-b border-gray-200 mb-4">
                <button
                  type="button"
                  onClick={() => handleTabChange('city')}
                  className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
                    activeTab === 'city'
                      ? 'border-blue-500 text-blue-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}
                >
                  City Search
                </button>
                <button
                  type="button"
                  onClick={() => handleTabChange('draw')}
                  className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
                    activeTab === 'draw'
                      ? 'border-blue-500 text-blue-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}
                >
                  Draw Area
                </button>
              </div>

              {/* City Search Tab */}
              {activeTab === 'city' && (
                <div className="space-y-3">
                  {!boundsPolygon ? (
                    <>
                      {/* Search inputs — always visible until a candidate is confirmed */}
                      {!candidates && (
                        <>
                          <div className="flex gap-3">
                            <div className="flex-1">
                              <label className="block text-sm font-medium text-gray-700 mb-1">City</label>
                              <input
                                type="text"
                                value={city}
                                onChange={(e) => setCity(e.target.value)}
                                onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), handleResolveCity())}
                                className="block w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                                placeholder="Portland"
                              />
                            </div>
                            <div className="w-24">
                              <label className="block text-sm font-medium text-gray-700 mb-1">State</label>
                              <input
                                type="text"
                                value={stateAbbr}
                                onChange={(e) => setStateAbbr(e.target.value.toUpperCase().slice(0, 2))}
                                onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), handleResolveCity())}
                                className="block w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                                placeholder="OR"
                                maxLength={2}
                              />
                            </div>
                            <div className="flex items-end">
                              <button
                                type="button"
                                onClick={handleResolveCity}
                                disabled={resolving}
                                className="px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-md text-sm font-medium disabled:opacity-50"
                              >
                                {resolving ? 'Searching...' : 'Search'}
                              </button>
                            </div>
                          </div>

                          {resolving && resolveMessage && (
                            <p className="text-xs text-teal-700 italic">{resolveMessage}</p>
                          )}

                          {resolveError && (
                            <p className="text-sm text-red-600">{resolveError}</p>
                          )}

                          <p className="text-sm text-gray-500">
                            Enter a US city and state abbreviation to find downtown zoning boundaries.
                          </p>
                        </>
                      )}

                      {/* Candidates phase */}
                      {candidates && (
                        <div className="space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-sm text-gray-600 font-medium">
                              {isFallbackOnly
                                ? 'No zoning data found — showing city boundary'
                                : `${candidates.length} downtown zone ${candidates.length === 1 ? 'district' : 'districts'} found — hover to preview, click "Use this" to select`
                              }
                            </span>
                            <button
                              type="button"
                              onClick={handleSearchAgain}
                              className="px-3 py-1 border border-gray-300 text-gray-700 hover:bg-gray-50 rounded text-sm"
                            >
                              Search again
                            </button>
                          </div>

                          {isFallbackOnly && (
                            <p className="text-sm text-amber-600">
                              No public zoning data found for this city. The boundary shown is the full city administrative area.
                              Use the <strong>Draw Area</strong> tab to trace a specific downtown boundary.
                            </p>
                          )}

                          <div className="flex gap-3 h-[28rem]">
                            {/* Left: candidate list */}
                            <div className="w-48 flex-shrink-0 overflow-y-auto border border-gray-200 rounded-md">
                              {candidates.map((c, i) => (
                                <div
                                  key={i}
                                  className={`flex items-start gap-2 px-3 py-2 cursor-pointer border-b border-gray-100 last:border-b-0 ${
                                    hoveredIndex === i ? 'bg-teal-50' : 'hover:bg-gray-50'
                                  }`}
                                  onMouseEnter={() => setHoveredIndex(i)}
                                  onMouseLeave={() => setHoveredIndex(null)}
                                >
                                  <span
                                    className="mt-1 flex-shrink-0 w-2.5 h-2.5 rounded-full"
                                    style={{ backgroundColor: c.score >= 1 ? '#0d9488' : '#94a3b8' }}
                                  />
                                  <div className="flex-1 min-w-0">
                                    <p className="text-xs text-gray-800 leading-tight break-words">{c.name}</p>
                                    <p className="text-xs text-gray-400 mt-0.5">{sourceLabel(c.source)}</p>
                                    <button
                                      type="button"
                                      onClick={() => handleUseCandidate(i)}
                                      className="mt-1 text-xs text-teal-700 hover:text-teal-900 font-medium"
                                    >
                                      Use this
                                    </button>
                                  </div>
                                </div>
                              ))}
                            </div>

                            {/* Right: map showing all candidates */}
                            <div className="flex-1 border border-gray-300 rounded-md overflow-hidden">
                              <MapContainer
                                center={[39.8283, -98.5795]}
                                zoom={4}
                                style={{ height: '100%', width: '100%' }}
                              >
                                <TileLayer
                                  attribution='&copy; <a href="https://maps.google.com">Google Maps</a>'
                                  url="/api/v1/tiles/{z}/{x}/{y}"
                                />
                                {candidates.map((c, i) => (
                                  <GeoJSON
                                    key={`${i}-${hoveredIndex === i}`}
                                    data={c.geometry as GeoJSON.GeoJsonObject}
                                    style={{
                                      color: '#0d9488',
                                      weight: hoveredIndex === i ? 3 : 2,
                                      fillColor: '#0d9488',
                                      fillOpacity: hoveredIndex === i ? 0.35 : 0.05,
                                      opacity: hoveredIndex === i ? 1 : 0.6,
                                    }}
                                  />
                                ))}
                                <FitToPolygon geojson={candidates[0].geometry} />
                              </MapContainer>
                            </div>
                          </div>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-green-600 font-medium">
                          Boundary confirmed: {selectedCandidateName}
                        </span>
                        <button
                          type="button"
                          onClick={handleSearchAgain}
                          className="px-3 py-1 border border-gray-300 text-gray-700 hover:bg-gray-50 rounded text-sm"
                        >
                          Change
                        </button>
                      </div>
                      <div className="h-[28rem] border border-gray-300 rounded-md overflow-hidden">
                        <MapContainer
                          center={[39.8283, -98.5795]}
                          zoom={4}
                          style={{ height: '100%', width: '100%' }}
                        >
                          <TileLayer
                            attribution='&copy; <a href="https://maps.google.com">Google Maps</a>'
                            url="/api/v1/tiles/{z}/{x}/{y}"
                          />
                          <GeoJSON
                            key={JSON.stringify(boundsPolygon)}
                            data={boundsPolygon as GeoJSON.GeoJsonObject}
                            style={resolvedPolygonStyle}
                          />
                          <FitToPolygon geojson={boundsPolygon} />
                        </MapContainer>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Draw Area Tab */}
              {activeTab === 'draw' && (
                <div>
                  <p className="text-sm text-gray-500 mb-2">
                    Click the polygon button (⬠), then click on the map to add vertices. Double-click to finish.
                  </p>
                  <div className="h-[32rem] border border-gray-300 rounded-md overflow-hidden">
                    <MapContainer
                      center={[39.8283, -98.5795]}
                      zoom={4}
                      style={{ height: '100%', width: '100%' }}
                    >
                      <TileLayer
                        attribution='&copy; <a href="https://maps.google.com">Google Maps</a>'
                        url="/api/v1/tiles/{z}/{x}/{y}"
                      />
                      {statesGeoJson && (
                        <GeoJSON data={statesGeoJson} style={statesStyle} />
                      )}
                      <PolygonDrawer onPolygonSelected={setDrawnPolygon} />
                    </MapContainer>
                  </div>
                  {drawnPolygon && (
                    <p className="text-sm text-green-600 mt-2">
                      Polygon drawn — ready to create project.
                    </p>
                  )}
                </div>
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
              disabled={submitDisabled}
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
