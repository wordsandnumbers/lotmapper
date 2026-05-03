import { useState } from 'react'
import type { Geometry } from 'geojson'
import { projectsApi } from '../services/api'
import CitySearchTab from './CitySearchTab'
import DrawAreaTab from './DrawAreaTab'

interface Props {
  onClose: () => void
  onCreated: () => void
}

type Tab = 'city' | 'draw'

export default function CreateProjectModal({ onClose, onCreated }: Props) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [activeTab, setActiveTab] = useState<Tab>('city')
  const [bounds, setBounds] = useState<{
    min_lat: number
    min_lng: number
    max_lat: number
    max_lng: number
  } | null>(null)
  const [boundsPolygon, setBoundsPolygon] = useState<Geometry | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleTabChange = (tab: Tab) => {
    setActiveTab(tab)
    if (tab === 'city') {
      setBounds(null)
    } else {
      setBoundsPolygon(null)
    }
    setError('')
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (!name.trim()) {
      setError('Project name is required')
      return
    }

    if (activeTab === 'draw' && !bounds) {
      setError('Please draw a bounding box on the map')
      return
    }

    if (activeTab === 'city' && !boundsPolygon) {
      setError('Please find and confirm a city boundary')
      return
    }

    setLoading(true)

    try {
      if (activeTab === 'city' && boundsPolygon) {
        await projectsApi.create({
          name: name.trim(),
          description: description.trim() || undefined,
          bounds_polygon: boundsPolygon,
        })
      } else {
        await projectsApi.create({
          name: name.trim(),
          description: description.trim() || undefined,
          bounds: bounds!,
        })
      }
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

  const submitDisabled = loading || (activeTab === 'draw' ? !bounds : !boundsPolygon)

  return (
    <div
      className="fixed inset-0 bg-gray-600 bg-opacity-50 flex items-center justify-center z-50"
      onClick={handleBackdropClick}
    >
      <div className="flex flex-col bg-white w-full h-full sm:rounded-lg sm:shadow-xl sm:max-w-6xl sm:h-auto sm:max-h-[95vh] overflow-hidden">
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

        <form onSubmit={handleSubmit} className="flex flex-col flex-1 min-h-0">
          <div className="p-4 sm:p-6 space-y-4 overflow-y-auto flex-1 min-h-0">
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

              {activeTab === 'city' && (
                <CitySearchTab onBoundarySelected={setBoundsPolygon} />
              )}
              {activeTab === 'draw' && (
                <DrawAreaTab onBoundsChange={setBounds} />
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
