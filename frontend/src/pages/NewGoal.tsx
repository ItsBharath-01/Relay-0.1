// NewGoal redirects to Dashboard — standalone goal entry lives there
import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

export default function NewGoal() {
  const navigate = useNavigate()
  useEffect(() => {
    navigate('/dashboard', { replace: true })
  }, [navigate])
  return null
}
