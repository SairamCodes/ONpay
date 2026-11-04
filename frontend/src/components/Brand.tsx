export function Brand({ small = false }: { small?: boolean }) {
  return (
    <div className={`brand ${small ? 'brand-small' : ''}`} aria-label="ONPay">
      <span className="brand-mark">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2Zm1.8 17V9.4l2.6 2.6 1.7-1.7L12 4.2l-6.1 6.1 1.7 1.7 2.6-2.6V19Z" />
        </svg>
      </span>
      <span className="brand-word">
        <b>ON</b>Pay
      </span>
    </div>
  )
}

export default Brand
