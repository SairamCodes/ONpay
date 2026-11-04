import React from 'react'
import { Icon } from './Icon'

export function EmptyState({
  icon = 'search',
  title,
  body,
  action,
}: {
  icon?: string
  title: string
  body: string
  action?: React.ReactNode
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon">
        <Icon name={icon} size={27} />
      </span>
      <h3>{title}</h3>
      <p>{body}</p>
      {action}
    </div>
  )
}

export default EmptyState
