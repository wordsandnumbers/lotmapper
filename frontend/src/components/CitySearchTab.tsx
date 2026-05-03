import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { MapContainer, TileLayer, GeoJSON, useMap } from 'react-leaflet'
import L from 'leaflet'
import { citySearchStreamUrl } from '../services/api'
import { useAuthStore } from '../store/auth'

interface CitySearchTabProps {
  onBoundarySelected: (polygon: GeoJSON.Geometry | null) => void
}

const STATE_NAME_TO_ABBR: Record<string, string> = {
  'Alabama': 'AL', 'Alaska': 'AK', 'Arizona': 'AZ', 'Arkansas': 'AR',
  'California': 'CA', 'Colorado': 'CO', 'Connecticut': 'CT', 'Delaware': 'DE',
  'Florida': 'FL', 'Georgia': 'GA', 'Hawaii': 'HI', 'Idaho': 'ID',
  'Illinois': 'IL', 'Indiana': 'IN', 'Iowa': 'IA', 'Kansas': 'KS',
  'Kentucky': 'KY', 'Louisiana': 'LA', 'Maine': 'ME', 'Maryland': 'MD',
  'Massachusetts': 'MA', 'Michigan': 'MI', 'Minnesota': 'MN', 'Mississippi': 'MS',
  'Missouri': 'MO', 'Montana': 'MT', 'Nebraska': 'NE', 'Nevada': 'NV',
  'New Hampshire': 'NH', 'New Jersey': 'NJ', 'New Mexico': 'NM', 'New York': 'NY',
  'North Carolina': 'NC', 'North Dakota': 'ND', 'Ohio': 'OH', 'Oklahoma': 'OK',
  'Oregon': 'OR', 'Pennsylvania': 'PA', 'Rhode Island': 'RI', 'South Carolina': 'SC',
  'South Dakota': 'SD', 'Tennessee': 'TN', 'Texas': 'TX', 'Utah': 'UT',
  'Vermont': 'VT', 'Virginia': 'VA', 'Washington': 'WA', 'West Virginia': 'WV',
  'Wisconsin': 'WI', 'Wyoming': 'WY', 'District of Columbia': 'DC',
}

interface CitySuggestion {
  city: string
  stateAbbr: string
  label: string
}

function sourceLabel(source: string): string {
  switch (source) {
    case 'arcgis_hub': return 'ArcGIS Hub'
    case 'arcgis_online': return 'ArcGIS Online'
    case 'fallback': return 'Estimated'
    default: return source
  }
}

function combineGeometries(geometries: GeoJSON.Geometry[]): GeoJSON.Geometry {
  if (geometries.length === 1) return geometries[0]
  const polygons: GeoJSON.Position[][][] = []
  for (const geom of geometries) {
    if (geom.type === 'Polygon') polygons.push(geom.coordinates)
    else if (geom.type === 'MultiPolygon') polygons.push(...geom.coordinates)
  }
  return { type: 'MultiPolygon', coordinates: polygons }
}

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

const resolvedPolygonStyle = {
  color: '#0d9488',
  weight: 2,
  fillColor: '#0d9488',
  fillOpacity: 0.2,
}

export default function CitySearchTab({ onBoundarySelected }: CitySearchTabProps) {
  const [city, setCity] = useState('')
  const [stateAbbr, setStateAbbr] = useState('')
  const [resolving, setResolving] = useState(false)
  const [resolveMessage, setResolveMessage] = useState('')
  const [resolveError, setResolveError] = useState('')
  const [candidates, setCandidates] = useState<Array<{
    name: string
    geometry: GeoJSON.Geometry
    score: number
    source: string
  }> | null>(null)
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null)
  const [selectedIndices, setSelectedIndices] = useState<Set<number>>(new Set())
  const [boundsPolygon, setBoundsPolygon] = useState<GeoJSON.Geometry | null>(null)
  const [selectedCandidateName, setSelectedCandidateName] = useState<string | null>(null)

  const [cityQuery, setCityQuery] = useState('')
  const [suggestions, setSuggestions] = useState<CitySuggestion[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [fetchingSuggestions, setFetchingSuggestions] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const suggestionsRef = useRef<HTMLDivElement>(null)
  const suppressTypeaheadRef = useRef(false)

  const combinedGeometry = useMemo(() => {
    if (!candidates || selectedIndices.size === 0) return null
    const geoms = Array.from(selectedIndices).map(i => candidates[i].geometry)
    return combineGeometries(geoms)
  }, [candidates, selectedIndices])

  useEffect(() => {
    if (suppressTypeaheadRef.current) {
      suppressTypeaheadRef.current = false
      return
    }
    if (cityQuery.length < 2) {
      setSuggestions([])
      setShowSuggestions(false)
      return
    }
    setFetchingSuggestions(true)
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(
          `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(cityQuery)}&countrycodes=us&addressdetails=1&format=json&limit=8&featuretype=city`,
          { headers: { 'Accept-Language': 'en-US' } }
        )
        const data = await res.json()
        const seen = new Set<string>()
        const items: CitySuggestion[] = []
        for (const r of data) {
          const cityName = r.address?.city || r.address?.town || r.address?.village || r.address?.municipality
          const stateName = r.address?.state
          if (!cityName || !stateName) continue
          const abbr = STATE_NAME_TO_ABBR[stateName]
          if (!abbr) continue
          const label = `${cityName}, ${abbr}`
          if (seen.has(label)) continue
          seen.add(label)
          items.push({ city: cityName, stateAbbr: abbr, label })
        }
        setSuggestions(items)
        setShowSuggestions(items.length > 0)
      } catch {
        // silently fail on network error
      } finally {
        setFetchingSuggestions(false)
      }
    }, 300)
    return () => clearTimeout(timer)
  }, [cityQuery])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (suggestionsRef.current && !suggestionsRef.current.contains(e.target as Node)) {
        setShowSuggestions(false)
        setActiveIndex(-1)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const triggerCitySearch = (searchCity: string, searchState: string) => {
    setResolveError('')
    setResolving(true)
    setResolveMessage('Starting search...')
    setCandidates(null)
    setBoundsPolygon(null)
    setSelectedCandidateName(null)
    onBoundarySelected(null)

    const token = useAuthStore.getState().token
    const es = new EventSource(citySearchStreamUrl(searchCity, searchState, token!))

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

  const handleResolveCity = () => {
    let searchCity = city.trim()
    let searchState = stateAbbr.trim()

    if (!searchCity || !searchState) {
      const match = cityQuery.trim().match(/^(.+?),?\s*([A-Za-z]{2})$/)
      if (match) {
        searchCity = match[1].trim()
        searchState = match[2].toUpperCase()
        setCity(searchCity)
        setStateAbbr(searchState)
      }
    }

    if (!searchCity || !searchState) {
      setResolveError('Please enter a city and state (e.g. Portland, OR)')
      return
    }

    triggerCitySearch(searchCity, searchState)
  }

  const handleSelectSuggestion = (s: CitySuggestion) => {
    suppressTypeaheadRef.current = true
    setCityQuery(s.label)
    setCity(s.city)
    setStateAbbr(s.stateAbbr)
    setSuggestions([])
    setShowSuggestions(false)
    setActiveIndex(-1)
    triggerCitySearch(s.city, s.stateAbbr)
  }

  const handleCityQueryKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIndex(i => Math.min(i + 1, suggestions.length - 1))
      setShowSuggestions(true)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex(i => Math.max(i - 1, -1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (showSuggestions && activeIndex >= 0 && suggestions[activeIndex]) {
        handleSelectSuggestion(suggestions[activeIndex])
      } else {
        setShowSuggestions(false)
        handleResolveCity()
      }
    } else if (e.key === 'Escape') {
      setShowSuggestions(false)
      setActiveIndex(-1)
    }
  }

  const handleToggleCandidate = useCallback((index: number) => {
    setSelectedIndices(prev => {
      const next = new Set(prev)
      if (next.has(index)) next.delete(index)
      else next.add(index)
      return next
    })
  }, [])

  const handleUseSelected = useCallback(() => {
    if (!candidates || selectedIndices.size === 0 || !combinedGeometry) return
    const names = Array.from(selectedIndices).map(i => candidates[i].name).join(' + ')
    setBoundsPolygon(combinedGeometry)
    setSelectedCandidateName(names)
    onBoundarySelected(combinedGeometry)
  }, [candidates, selectedIndices, combinedGeometry, onBoundarySelected])

  const handleSearchAgain = () => {
    setCandidates(null)
    setBoundsPolygon(null)
    setSelectedCandidateName(null)
    setSelectedIndices(new Set())
    setCityQuery('')
    setCity('')
    setStateAbbr('')
    setSuggestions([])
    setShowSuggestions(false)
    setResolveError('')
    onBoundarySelected(null)
  }

  return (
    <div className="space-y-3">
      {!boundsPolygon ? (
        <>
          {!candidates && (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">City, State</label>
                <div className="flex gap-3">
                  <div className="flex-1 relative" ref={suggestionsRef}>
                    <input
                      type="text"
                      value={cityQuery}
                      onChange={(e) => {
                        setCityQuery(e.target.value)
                        setActiveIndex(-1)
                        setCity('')
                        setStateAbbr('')
                      }}
                      onKeyDown={handleCityQueryKeyDown}
                      onFocus={() => { if (suggestions.length > 0) setShowSuggestions(true) }}
                      disabled={resolving}
                      className={`block w-full border border-gray-300 rounded-md px-3 py-2 pr-8 focus:outline-none focus:ring-blue-500 focus:border-blue-500 ${resolving ? 'bg-gray-50 text-gray-500 cursor-not-allowed' : ''}`}
                      placeholder="Portland, OR"
                      autoComplete="off"
                    />
                    {fetchingSuggestions && !resolving && (
                      <div className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 border-2 border-teal-500 border-t-transparent rounded-full animate-spin pointer-events-none" />
                    )}
                    {showSuggestions && suggestions.length > 0 && (
                      <div className="absolute z-50 w-full mt-1 bg-white border border-gray-200 rounded-md shadow-lg max-h-48 overflow-y-auto">
                        {suggestions.map((s, i) => (
                          <button
                            key={s.label}
                            type="button"
                            className={`w-full text-left px-3 py-2 text-sm ${activeIndex === i ? 'bg-teal-50' : 'hover:bg-gray-50'}`}
                            onMouseDown={(e) => { e.preventDefault(); handleSelectSuggestion(s) }}
                          >
                            {s.label}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
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
                Type a US city name to search for boundary candidates.
              </p>
            </>
          )}

          {candidates && (
            <div className="space-y-2">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <span className="text-sm text-gray-600 font-medium">
                  {candidates.length} {candidates.length === 1 ? 'option' : 'options'} found
                  {selectedIndices.size === 0
                    ? ' — check to select'
                    : ` — ${selectedIndices.size} selected`}
                </span>
                <div className="flex items-center gap-2">
                  {selectedIndices.size > 0 && (
                    <button
                      type="button"
                      onClick={handleUseSelected}
                      className="px-3 py-1 bg-teal-600 hover:bg-teal-700 text-white rounded text-sm font-medium"
                    >
                      {selectedIndices.size > 1 ? `Use ${selectedIndices.size} combined` : 'Use selected'}
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={handleSearchAgain}
                    className="px-3 py-1 border border-gray-300 text-gray-700 hover:bg-gray-50 rounded text-sm"
                  >
                    Search again
                  </button>
                </div>
              </div>
              <div className="flex flex-col h-[calc(100vh-450px)] min-h-[180px] sm:flex-row sm:h-[28rem] gap-3">
                <div className="flex-shrink-0 overflow-y-auto border border-gray-200 rounded-md max-h-[35%] sm:max-h-none sm:w-48 sm:flex-shrink-0">
                  {candidates.map((c, i) => (
                    <div
                      key={i}
                      className={`flex items-start gap-2 px-3 py-2 cursor-pointer border-b border-gray-100 last:border-b-0 ${
                        selectedIndices.has(i)
                          ? 'bg-blue-50'
                          : hoveredIndex === i
                          ? 'bg-teal-50'
                          : 'hover:bg-gray-50'
                      }`}
                      onClick={() => handleToggleCandidate(i)}
                      onMouseEnter={() => setHoveredIndex(i)}
                      onMouseLeave={() => setHoveredIndex(null)}
                    >
                      <input
                        type="checkbox"
                        checked={selectedIndices.has(i)}
                        onChange={() => handleToggleCandidate(i)}
                        onClick={e => e.stopPropagation()}
                        className="mt-1 flex-shrink-0 accent-teal-600"
                      />
                      <span
                        className="mt-1 flex-shrink-0 w-2.5 h-2.5 rounded-full"
                        style={{ backgroundColor: c.score >= 1 ? '#0d9488' : '#94a3b8' }}
                      />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-gray-800 leading-tight break-words">{c.name}</p>
                        <p className="text-xs text-gray-400 mt-0.5">{sourceLabel(c.source)}</p>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="flex-1 min-h-0 border border-gray-300 rounded-md overflow-hidden">
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
                        key={`${i}-${hoveredIndex === i}-${selectedIndices.has(i)}`}
                        data={c.geometry as GeoJSON.GeoJsonObject}
                        style={{
                          color: selectedIndices.has(i) ? '#2563eb' : '#94a3b8',
                          weight: hoveredIndex === i ? 3 : 1.5,
                          fillColor: selectedIndices.has(i) ? '#2563eb' : '#94a3b8',
                          fillOpacity: selectedIndices.has(i) ? 0.18 : hoveredIndex === i ? 0.12 : 0.03,
                          opacity: selectedIndices.has(i) ? 1 : hoveredIndex === i ? 0.8 : 0.45,
                        }}
                      />
                    ))}
                    {combinedGeometry && selectedIndices.size > 1 && (
                      <GeoJSON
                        key={`union-${Array.from(selectedIndices).sort().join(',')}`}
                        data={combinedGeometry as GeoJSON.GeoJsonObject}
                        style={{
                          color: '#0d9488',
                          weight: 3,
                          fillColor: '#0d9488',
                          fillOpacity: 0.2,
                          opacity: 1,
                        }}
                      />
                    )}
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
          <div className="h-[20rem] sm:h-[28rem] border border-gray-300 rounded-md overflow-hidden">
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
  )
}
