import React from 'react'

interface SkeletonProps {
  className?: string
  lines?: number
}

export const Skeleton: React.FC<SkeletonProps> = ({ className = '', lines = 1 }) => {
  if (lines === 1) {
    return <div className={`h-4 bg-slate-100 rounded animate-pulse ${className}`} />
  }
  return (
    <div className="space-y-2">
      {Array.from({ length: lines }, (_, i) => (
        <div
          key={i}
          className={`h-4 bg-slate-100 rounded animate-pulse ${className}`}
          style={{ width: i === lines - 1 ? '60%' : '100%' }}
        />
      ))}
    </div>
  )
}

export const SkeletonCard: React.FC = () => (
  <div className="bg-white border border-slate-200 rounded-card p-5 space-y-3 animate-pulse">
    <div className="h-4 bg-slate-100 rounded w-3/4" />
    <div className="space-y-2">
      <div className="h-3 bg-slate-100 rounded" />
      <div className="h-3 bg-slate-100 rounded w-5/6" />
    </div>
    <div className="flex gap-2">
      <div className="h-6 bg-slate-100 rounded-full w-20" />
      <div className="h-6 bg-slate-100 rounded-full w-16" />
    </div>
  </div>
)
