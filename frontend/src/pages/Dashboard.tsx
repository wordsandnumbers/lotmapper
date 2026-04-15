import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { projectsApi } from '../services/api'
import { useAuthStore } from '../store/auth'
import CreateProjectModal from '../components/CreateProjectModal'

interface Project {
  id: string
  name: string
  description: string | null
  status: string
  polygon_count: number
  created_at: string
}

export default function Dashboard() {
  const PAGE_SIZE = 10

  const [projects, setProjects] = useState<Project[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [deleteProjectId, setDeleteProjectId] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  const navigate = useNavigate()
  const { user } = useAuthStore()

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const loadProjects = async (currentPage = page) => {
    try {
      const data = await projectsApi.list(statusFilter || undefined, currentPage, PAGE_SIZE)
      setProjects(data.projects)
      setTotal(data.total)
    } catch (error) {
      console.error('Failed to load projects:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setPage(1)
    loadProjects(1)
  }, [statusFilter])

  useEffect(() => {
    loadProjects(page)
    window.scrollTo(0, 0)
  }, [page])

  const handleProjectCreated = () => {
    setShowCreateModal(false)
    loadProjects()
  }

  const handleDelete = async (projectId: string) => {
    setDeleting(true)
    try {
      await projectsApi.delete(projectId)
      setDeleteProjectId(null)
      loadProjects()
    } catch (error) {
      console.error('Failed to delete project:', error)
      alert('Failed to delete project. Please try again.')
    } finally {
      setDeleting(false)
    }
  }

  const getStatusBadgeClass = (status: string) => {
    switch (status) {
      case 'pending':
        return 'bg-gray-100 text-gray-800'
      case 'processing':
        return 'bg-yellow-100 text-yellow-800'
      case 'review':
        return 'bg-blue-100 text-blue-800'
      case 'approved':
        return 'bg-green-100 text-green-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }

  return (
    <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
      <div className="px-4 py-6 sm:px-0">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-2xl font-semibold text-gray-900">Projects</h1>
          <button
            onClick={() => setShowCreateModal(true)}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-md text-sm font-medium"
          >
            New Project
          </button>
        </div>

        <div className="mb-4">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="border border-gray-300 rounded-md px-3 py-2 text-sm"
          >
            <option value="">All Statuses</option>
            <option value="pending">Pending</option>
            <option value="processing">Processing</option>
            <option value="review">Review</option>
            <option value="approved">Approved</option>
          </select>
        </div>

        {loading ? (
          <div className="text-center py-12">Loading...</div>
        ) : projects.length === 0 ? (
          <div className="text-center py-12 bg-white rounded-lg shadow">
            <p className="text-gray-500">No projects yet. Create one to get started!</p>
          </div>
        ) : (
          <>
            <div className="bg-white shadow overflow-hidden sm:rounded-md">
              <ul className="divide-y divide-gray-200">
                {projects.map((project) => (
                  <li key={project.id}>
                    <div className="flex items-center hover:bg-gray-50">
                      <button
                        onClick={() => navigate(`/project/${project.id}`)}
                        className="flex-1 text-left"
                      >
                        <div className="px-4 py-4 sm:px-6">
                          <div className="flex items-center justify-between">
                            <p className="text-sm font-medium text-blue-600 truncate">
                              {project.name}
                            </p>
                            <div className="ml-2 flex-shrink-0 flex">
                              <span
                                className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${getStatusBadgeClass(
                                  project.status
                                )}`}
                              >
                                {project.status}
                              </span>
                            </div>
                          </div>
                          <div className="mt-2 sm:flex sm:justify-between">
                            <div className="sm:flex">
                              <p className="flex items-center text-sm text-gray-500">
                                {project.description || 'No description'}
                              </p>
                            </div>
                            <div className="mt-2 flex items-center text-sm text-gray-500 sm:mt-0">
                              <span>{project.polygon_count} polygons</span>
                              <span className="mx-2">|</span>
                              <span>
                                {new Date(project.created_at).toLocaleDateString()}
                              </span>
                            </div>
                          </div>
                        </div>
                      </button>
                      {user?.role === 'admin' && (
                        <div className="px-4">
                          {deleteProjectId === project.id ? (
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => handleDelete(project.id)}
                                disabled={deleting}
                                className="text-red-600 hover:text-red-800 text-sm font-medium disabled:opacity-50"
                              >
                                {deleting ? 'Deleting...' : 'Confirm'}
                              </button>
                              <button
                                onClick={() => setDeleteProjectId(null)}
                                disabled={deleting}
                                className="text-gray-500 hover:text-gray-700 text-sm"
                              >
                                Cancel
                              </button>
                            </div>
                          ) : (
                            <button
                              onClick={() => setDeleteProjectId(project.id)}
                              className="text-red-600 hover:text-red-800 text-sm font-medium"
                            >
                              Delete
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </div>

            <div className="mt-4 flex items-center justify-between">
              <p className="text-sm text-gray-500">
                Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} of {total}
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => p - 1)}
                  disabled={page === 1}
                  className="px-3 py-1 text-sm border border-gray-300 rounded-md disabled:opacity-40 hover:bg-gray-50"
                >
                  Previous
                </button>
                <span className="px-3 py-1 text-sm text-gray-700">
                  {page} / {totalPages}
                </span>
                <button
                  onClick={() => setPage((p) => p + 1)}
                  disabled={page === totalPages}
                  className="px-3 py-1 text-sm border border-gray-300 rounded-md disabled:opacity-40 hover:bg-gray-50"
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      {showCreateModal && (
        <CreateProjectModal
          onClose={() => setShowCreateModal(false)}
          onCreated={handleProjectCreated}
        />
      )}
    </div>
  )
}
