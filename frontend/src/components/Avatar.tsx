import { initials } from '../utils'

export function Avatar({ name, size = 'md' }: { name: string; size?: 'sm' | 'md' | 'lg' }) {
  return (
    <span className={`avatar avatar-${size}`} aria-label={name}>
      {initials(name)}
    </span>
  )
}

export default Avatar
