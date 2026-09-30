import React from 'react'
import type { ReactNode } from 'react'

interface CardProps {
  children: ReactNode
  className?: string
  padding?: 'none' | 'sm' | 'md' | 'lg'
  hover?: boolean
}

const PAD_MAP: Record<string, string> = {
  none: '',
  sm: 'p-3',
  md: 'p-5',
  lg: 'p-6',
}

export const Card: React.FC<CardProps> = ({ children, className = '', padding = 'md', hover = false }) => {
  return (
    <div className={`bg-white border border-slate-200 rounded-card shadow-subtle ${PAD_MAP[padding]} ${hover ? 'hover:border-primary-200 hover:shadow-lifted transition-shadow cursor-pointer' : ''} ${className}`}>
      {children}
    </div>
  )
}
