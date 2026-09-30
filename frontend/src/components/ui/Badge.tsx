import React from 'react'

interface BadgeProps {
  label: string
  color?: 'slate' | 'blue' | 'green' | 'amber' | 'red' | 'violet' | 'indigo' | 'purple'
  size?: 'sm' | 'md'
  icon?: React.ReactNode
}

const COLOR_MAP: Record<string, string> = {
  slate: 'bg-slate-100 text-slate-700 border-slate-300',
  blue: 'bg-blue-50 text-blue-700 border-blue-200',
  green: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  amber: 'bg-amber-50 text-amber-700 border-amber-200',
  red: 'bg-rose-50 text-rose-700 border-rose-200',
  violet: 'bg-violet-50 text-violet-700 border-violet-200',
  indigo: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  purple: 'bg-purple-50 text-purple-700 border-purple-200',
}

export const Badge: React.FC<BadgeProps> = ({ label, color = 'slate', size = 'sm', icon }) => {
  const cls = COLOR_MAP[color] || COLOR_MAP.slate
  const sizeClass = size === 'sm' ? 'text-xs px-2 py-0.5' : 'text-sm px-2.5 py-1'

  return (
    <span className={`inline-flex items-center gap-1 rounded-full border font-medium ${cls} ${sizeClass}`}>
      {icon}
      {label}
    </span>
  )
}
