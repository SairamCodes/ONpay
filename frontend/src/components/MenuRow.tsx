import { Icon } from './Icon'

export function MenuRow({
  icon,
  title,
  subtitle,
  onClick,
}: {
  icon: string
  title: string
  subtitle: string
  onClick: () => void
}) {
  return (
    <button className="menu-row" onClick={onClick}>
      <span className="menu-icon">
        <Icon name={icon} />
      </span>
      <span>
        <strong>{title}</strong>
        <small>{subtitle}</small>
      </span>
      <Icon name="arrow" size={17} />
    </button>
  )
}

export default MenuRow
