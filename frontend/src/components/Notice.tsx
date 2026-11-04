import { Icon } from './Icon'

export function Notice({ message, onClose }: { message: string; onClose: () => void }) {
  if (!message) return null
  return (
    <div className="notice" role="status">
      <Icon name="info" size={18} />
      <span>{message}</span>
      <button className="icon-button" onClick={onClose} aria-label="Dismiss">
        <Icon name="close" size={17} />
      </button>
    </div>
  )
}

export default Notice
