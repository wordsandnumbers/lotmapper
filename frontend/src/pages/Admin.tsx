import { useState, useEffect } from 'react'
import { authApi } from '../services/api'

interface User {
  id: string
  email: string
  role: string
  is_active: boolean
  created_at: string
}

export default function Admin() {
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [updating, setUpdating] = useState<string | null>(null)

  const loadUsers = async () => {
    try {
      const data = await authApi.getUsers()
      setUsers(data)
    } catch (error) {
      console.error('Failed to load users:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadUsers()
  }, [])

  const handleToggleActive = async (userId: string, currentActive: boolean) => {
    setUpdating(userId)
    try {
      await authApi.updateUser(userId, { is_active: !currentActive })
      loadUsers()
    } catch (error) {
      console.error('Failed to update user:', error)
    } finally {
      setUpdating(null)
    }
  }

  const handleChangeRole = async (userId: string, newRole: string) => {
    setUpdating(userId)
    try {
      await authApi.updateUser(userId, { role: newRole })
      loadUsers()
    } catch (error) {
      console.error('Failed to update user:', error)
    } finally {
      setUpdating(null)
    }
  }

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="text-center py-12">Loading...</div>
      </div>
    )
  }

  return (
    <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
      <div className="px-4 py-6 sm:px-0">
        <h1 className="text-2xl font-semibold text-gray-900 mb-6">User Management</h1>

        <div className="bg-white shadow overflow-hidden sm:rounded-md">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Email
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Role
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Created
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {users.map((user) => (
                <tr key={user.id}>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium text-gray-900">{user.email}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <select
                      value={user.role}
                      onChange={(e) => handleChangeRole(user.id, e.target.value)}
                      disabled={updating === user.id}
                      className="text-sm border border-gray-300 rounded px-2 py-1"
                    >
                      <option value="reviewer">Reviewer</option>
                      <option value="admin">Admin</option>
                    </select>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span
                      className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${
                        user.is_active
                          ? 'bg-green-100 text-green-800'
                          : 'bg-red-100 text-red-800'
                      }`}
                    >
                      {user.is_active ? 'Active' : 'Pending'}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {new Date(user.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                    <button
                      onClick={() => handleToggleActive(user.id, user.is_active)}
                      disabled={updating === user.id}
                      className={`${
                        user.is_active
                          ? 'text-red-600 hover:text-red-900'
                          : 'text-green-600 hover:text-green-900'
                      } disabled:opacity-50`}
                    >
                      {updating === user.id
                        ? 'Updating...'
                        : user.is_active
                        ? 'Deactivate'
                        : 'Activate'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {users.filter((u) => !u.is_active).length > 0 && (
          <div className="mt-4 bg-yellow-50 border border-yellow-400 text-yellow-700 px-4 py-3 rounded">
            {users.filter((u) => !u.is_active).length} user(s) pending approval
          </div>
        )}
      </div>
    </div>
  )
}
