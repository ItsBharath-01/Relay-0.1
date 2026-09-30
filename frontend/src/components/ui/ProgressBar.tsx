import React from 'react'

interface ProgressBarProps {
  value: number
  max?: number
  color?: 'blue' | 'green' | 'violet'
  showLabel?: boolean
  className?: string
}

const COLOR_MAP: Record<string, string> = {
  blue: 'bg-blue-500',
  green: 'bg-emerald-500',
  violet: 'bg-violet-500',
}

export const ProgressBar: React.FC<ProgressBarProps> = ({
  value,
  max = 100,
  color = 'blue',
  showLabel = false,
  className = '',
}) => {
  const pct = Math.min(100, Math.max(0, (value / max) * 100))
  return (
    <div className={`w-full ${className}`}>
      {showLabel && (
        <div className="flex justify-between text-xs text-slate-500 mb-1">
          <span>{Math.round(pct)}%</span>
        </div>
      )}
      <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${COLOR_MAP[color]}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}
