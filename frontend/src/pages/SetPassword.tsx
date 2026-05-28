import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import AuthLayout from '../components/AuthLayout'
import { authApi } from '../services/api'
import { useAuthStore } from '../store/auth'

export default function SetPassword() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') || ''
  const navigate = useNavigate()
  const { setAuth } = useAuthStore()

  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  if (!token) {
    return (
      <AuthLayout title="Invalid link" subtitle="This account setup link is invalid or expired.">
        <div className="space-y-6 text-center">
          <div className="rounded border border-red-300 bg-red-50 px-4 py-3 text-red-700">
            <h2 className="font-bold">Invalid link</h2>
            <p className="mt-2">This link is invalid or expired.</p>
          </div>
          <Link to="/login" className="font-medium text-brand-primary hover:text-brand-primaryHover">
            Back to sign in
          </Link>
        </div>
      </AuthLayout>
    )
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (password !== confirmPassword) {
      setError('Passwords do not match')
      return
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }

    setLoading(true)
    try {
      const { access_token } = await authApi.setPassword(token, password)
      useAuthStore.setState({ token: access_token })
      const user = await authApi.getMe()
      setAuth(access_token, user)
      navigate('/dashboard')
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      setError(error.response?.data?.detail || 'This link is invalid or expired')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout title="Create your account" subtitle="Set a password to finish creating your account.">
      <form className="space-y-6" onSubmit={handleSubmit}>
        {error && (
          <div className="rounded border border-red-300 bg-red-50 px-4 py-3 text-red-700">
            {error}
          </div>
        )}
        <div className="rounded-md shadow-sm -space-y-px">
          <div>
            <label htmlFor="password" className="sr-only">
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="new-password"
              required
              className="relative block w-full rounded-none rounded-t-md border border-gray-300 px-3 py-2.5 text-gray-950 placeholder-gray-500 shadow-sm focus:z-10 focus:border-brand-primary focus:outline-none focus:ring-2 focus:ring-brand-primary/25 sm:text-sm"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="confirm-password" className="sr-only">
              Confirm Password
            </label>
            <input
              id="confirm-password"
              name="confirm-password"
              type="password"
              autoComplete="new-password"
              required
              className="relative block w-full rounded-none rounded-b-md border border-gray-300 px-3 py-2.5 text-gray-950 placeholder-gray-500 shadow-sm focus:z-10 focus:border-brand-primary focus:outline-none focus:ring-2 focus:ring-brand-primary/25 sm:text-sm"
              placeholder="Confirm password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
            />
          </div>
        </div>

        <div>
          <button
            type="submit"
            disabled={loading}
            className="flex w-full justify-center rounded-md border border-transparent bg-brand-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-brand-primaryHover focus:outline-none focus:ring-2 focus:ring-brand-accent focus:ring-offset-2 disabled:opacity-50"
          >
            {loading ? 'Creating account…' : 'Create account'}
          </button>
        </div>
      </form>
    </AuthLayout>
  )
}
