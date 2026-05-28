import { useState } from 'react'
import { useNavigate, useLocation, Link } from 'react-router-dom'
import AuthLayout from '../components/AuthLayout'
import { authApi } from '../services/api'
import { useAuthStore } from '../store/auth'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const { setAuth } = useAuthStore()
  const flash = (location.state as { flash?: string } | null)?.flash

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const { access_token } = await authApi.login(email, password)
      // Store token temporarily to make the getMe request
      useAuthStore.setState({ token: access_token })
      const user = await authApi.getMe()
      setAuth(access_token, user)
      navigate('/dashboard')
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      setError(error.response?.data?.detail || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout
      title="Sign in"
      subtitle="Access mapping projects, review detections, and manage parking lot boundaries."
    >
      <form className="space-y-4" onSubmit={handleSubmit}>
        {flash && !error && (
          <div className="rounded border border-green-300 bg-green-50 px-4 py-3 text-green-800">
            {flash}
          </div>
        )}
        {error && (
          <div className="rounded border border-red-300 bg-red-50 px-4 py-3 text-red-700">
            {error}
          </div>
        )}
        <div>
          <label htmlFor="email" className="sr-only">
            Email address
          </label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
            className="block w-full rounded-md border border-gray-300 px-3 py-2.5 text-gray-950 placeholder-gray-500 shadow-sm focus:border-auth-primary focus:outline-none focus:ring-2 focus:ring-auth-primary/25 sm:text-sm"
            placeholder="Email address"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="password" className="sr-only">
            Password
          </label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            className="block w-full rounded-md border border-gray-300 px-3 py-2.5 text-gray-950 placeholder-gray-500 shadow-sm focus:border-auth-primary focus:outline-none focus:ring-2 focus:ring-auth-primary/25 sm:text-sm"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          className="flex w-full justify-center rounded-md border border-transparent bg-auth-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-auth-primaryHover focus:outline-none focus:ring-2 focus:ring-auth-accent focus:ring-offset-2 disabled:opacity-50"
        >
          {loading ? 'Signing in...' : 'Sign in'}
        </button>

        <div className="text-center text-sm">
          <Link to="/forgot-password" className="font-medium text-auth-primary hover:text-auth-primaryHover">
            Forgot password?
          </Link>
        </div>

        <div className="text-center text-sm">
          <Link to="/register" className="font-medium text-auth-primary hover:text-auth-primaryHover">
            Don't have an account? Request access
          </Link>
        </div>
      </form>
    </AuthLayout>
  )
}
