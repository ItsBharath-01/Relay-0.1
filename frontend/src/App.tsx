import React from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { useEffect } from 'react'
import { useAuthStore } from './stores/authStore'
import { useUIStore } from './stores/uiStore'

// Lazy-load pages
const Landing = React.lazy(() => import('./pages/Landing'))
const Login = React.lazy(() => import('./pages/Login'))
const Signup = React.lazy(() => import('./pages/Signup'))
const Onboarding = React.lazy(() => import('./pages/Onboarding'))
const Dashboard = React.lazy(() => import('./pages/Dashboard'))
const NewGoal = React.lazy(() => import('./pages/NewGoal'))
const GoalUnderstand = React.lazy(() => import('./pages/GoalUnderstand'))
const PlanPreview = React.lazy(() => import('./pages/PlanPreview'))
const ExecutionWorkspace = React.lazy(() => import('./pages/ExecutionWorkspace'))
const ExecutionSummary = React.lazy(() => import('./pages/ExecutionSummary'))
const Approvals = React.lazy(() => import('./pages/Approvals'))
const Connections = React.lazy(() => import('./pages/Connections'))
const History = React.lazy(() => import('./pages/History'))
const Settings = React.lazy(() => import('./pages/Settings'))
const Help = React.lazy(() => import('./pages/Help'))

const Spinner = () => (
  <div className="min-h-screen flex items-center justify-center bg-slate-50">
    <div className="w-8 h-8 border-2 border-primary-600 border-t-transparent rounded-full animate-spin" />
  </div>
)

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuthStore()
  const location = useLocation()

  if (isLoading) return <Spinner />
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }
  return <>{children}</>
}

// Protected pages that use AppShell wrap their own layout
function ProtectedPage({ children }: { children: React.ReactNode }) {
  return <RequireAuth>{children}</RequireAuth>
}

function App() {
  const { checkAuth } = useAuthStore()
  const { checkLLMHealth } = useUIStore()

  useEffect(() => {
    checkAuth()
    checkLLMHealth()
    const interval = setInterval(checkLLMHealth, 60_000)
    return () => clearInterval(interval)
  }, [checkAuth, checkLLMHealth])

  return (
    <React.Suspense fallback={<Spinner />}>
      <Routes>
        {/* Public */}
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/onboarding" element={<RequireAuth><Onboarding /></RequireAuth>} />

        {/* Protected — each page wraps itself with AppShell */}
        <Route path="/dashboard" element={<ProtectedPage><Dashboard /></ProtectedPage>} />
        <Route path="/goal/new" element={<ProtectedPage><NewGoal /></ProtectedPage>} />
        <Route path="/goal/current/understand" element={<ProtectedPage><GoalUnderstand /></ProtectedPage>} />
        <Route path="/goal/:goalId/understand" element={<ProtectedPage><GoalUnderstand /></ProtectedPage>} />
        <Route path="/goal/current/plan" element={<ProtectedPage><PlanPreview /></ProtectedPage>} />
        <Route path="/goal/:goalId/plan" element={<ProtectedPage><PlanPreview /></ProtectedPage>} />
        <Route path="/execution/:executionId" element={<ProtectedPage><ExecutionWorkspace /></ProtectedPage>} />
        <Route path="/execution/:executionId/summary" element={<ProtectedPage><ExecutionSummary /></ProtectedPage>} />
        <Route path="/approvals" element={<ProtectedPage><Approvals /></ProtectedPage>} />
        <Route path="/connections" element={<ProtectedPage><Connections /></ProtectedPage>} />
        <Route path="/history" element={<ProtectedPage><History /></ProtectedPage>} />
        <Route path="/settings" element={<ProtectedPage><Settings /></ProtectedPage>} />
        <Route path="/help" element={<ProtectedPage><Help /></ProtectedPage>} />

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </React.Suspense>
  )
}

export default App
