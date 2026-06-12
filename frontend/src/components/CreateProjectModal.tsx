import { useState } from 'react'
import type { Geometry } from 'geojson'
import { projectsApi } from '../services/api'
import CitySearchTab from './CitySearchTab'

interface Props {
  onClose: () => void
  onCreated: () => void
}

export default function CreateProjectModal({ onClose, onCreated }: Props) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [boundsPolygon, setBoundsPolygon] = useState<Geometry | null>(null)
  const [city, setCity] = useState('')
  const [state, setState] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleBoundarySelected = (
    polygon: Geometry | null,
    selectedCity?: string,
    selectedState?: string,
    zoneName?: string,
  ) => {
    setBoundsPolygon(polygon)
    if (polygon && selectedCity && selectedState) {
      setCity(selectedCity)
      setState(selectedState)
      if (!name.trim() && zoneName) {
        setName(zoneName)
      }
    } else if (!polygon) {
      setCity('')
      setState('')
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (!name.trim()) {
      setError('Project name is required')
      return
    }
    if (!boundsPolygon) {
      setError('Please find and confirm a city boundary')
      return
    }

    setLoading(true)
    try {
      await projectsApi.create({
        name: name.trim(),
        description: description.trim() || undefined,
        bounds_polygon: boundsPolygon,
        city: city || undefined,
        state: state || undefined,
      })
      onCreated()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      setError(e.response?.data?.detail || 'Failed to create project')
    } finally {
      setLoading(false)
    }
  }

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose()
  }

  return (
    <div
      className="fixed inset-0 bg-app-canvas/70 backdrop-blur-sm flex items-center justify-center z-50"
      onClick={handleBackdropClick}
    >
      <div className="flex flex-col bg-white/95 w-full h-full sm:rounded-lg sm:shadow-xl sm:max-w-6xl sm:h-auto sm:max-h-[95vh] overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center">
          <h2 className="text-xl font-semibold text-app-heading">Create New Project</h2>
          <button
            onClick={onClose}
            className="text-app-body hover:text-app-heading text-2xl leading-none"
            aria-label="Close"
          >
            &times;
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col flex-1 min-h-0">
          <div className="p-4 sm:p-6 space-y-4 overflow-y-auto flex-1 min-h-0">
            {error && (
              <div className="bg-red-50 border border-red-400 text-red-700 px-4 py-3 rounded">
                {error}
              </div>
            )}

            {/* City search is the primary entry point */}
            <CitySearchTab onBoundarySelected={handleBoundarySelected} />

            <div>
              <label className="block text-sm font-medium text-app-heading">
                Project Name
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-primary/25 focus:border-brand-primary"
                placeholder="Portland, OR — Downtown Mixed Use"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-app-heading">
                Description (optional)
              </label>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="mt-1 block w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-primary/25 focus:border-brand-primary"
                placeholder="Parking lots in the downtown business district"
              />
            </div>
          </div>

          <div className="px-6 py-4 border-t border-gray-200 flex justify-end space-x-3">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-app-heading hover:bg-brand-primary/5"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !boundsPolygon}
              className="px-4 py-2 bg-brand-primary hover:bg-brand-primaryHover text-white rounded-md text-sm font-medium disabled:opacity-50"
            >
              {loading ? 'Creating...' : 'Create Project'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
