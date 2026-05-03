import { useState, useRef, useEffect, useCallback } from 'react'
import { MapContainer, TileLayer, GeoJSON, useMap, useMapEvents } from 'react-leaflet'
import L from 'leaflet'

interface DrawAreaTabProps {
  onBoundsChange: (bounds: { min_lat: number; min_lng: number; max_lat: number; max_lng: number } | null) => void
}

const statesStyle = {
  color: '#ffffff',
  weight: 1,
  fillOpacity: 0,
  opacity: 0.5,
}

function RectangleDrawer({
  onBoundsSelected
}: {
  onBoundsSelected: (bounds: { min_lat: number; min_lng: number; max_lat: number; max_lng: number } | null) => void
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

      if (previewRef.current) {
        map.removeLayer(previewRef.current)
        previewRef.current = null
      }

      if (rectangleRef.current) {
        map.removeLayer(rectangleRef.current)
      }

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
    onBoundsSelected(null)
  }, [map, onBoundsSelected])

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

  useEffect(() => {
    const container = map.getContainer()
    container.style.cursor = isDrawing ? 'crosshair' : ''
  }, [isDrawing, map])

  return null
}

export default function DrawAreaTab({ onBoundsChange }: DrawAreaTabProps) {
  const [bounds, setBounds] = useState<{
    min_lat: number
    min_lng: number
    max_lat: number
    max_lng: number
  } | null>(null)
  const [statesGeoJson, setStatesGeoJson] = useState<GeoJSON.FeatureCollection | null>(null)

  useEffect(() => {
    fetch('https://raw.githubusercontent.com/PublicaMundi/MappingAPI/master/data/geojson/us-states.json')
      .then(res => res.json())
      .then(data => setStatesGeoJson(data))
      .catch(err => console.error('Failed to load states:', err))
  }, [])

  const handleBoundsSelected = (newBounds: { min_lat: number; min_lng: number; max_lat: number; max_lng: number } | null) => {
    setBounds(newBounds)
    onBoundsChange(newBounds)
  }

  return (
    <>
      <p className="text-sm text-gray-500 mb-2">
        Click the rectangle button, then click and drag on the map to select an area.
      </p>
      <div className="h-[20rem] sm:h-[32rem] border border-gray-300 rounded-md overflow-hidden">
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
          <RectangleDrawer onBoundsSelected={handleBoundsSelected} />
        </MapContainer>
      </div>
      {bounds && (
        <p className="text-sm text-green-600 mt-2">
          Bounding box selected: {bounds.min_lat.toFixed(4)}, {bounds.min_lng.toFixed(4)} to{' '}
          {bounds.max_lat.toFixed(4)}, {bounds.max_lng.toFixed(4)}
        </p>
      )}
    </>
  )
}
