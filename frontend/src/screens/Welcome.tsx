import { Brand } from '../components/Brand'
import { Icon } from '../components/Icon'
import { Illustration } from '../components/Illustration'

export function Welcome({ onStart, onLogin }: { onStart: () => void; onLogin: () => void }) {
  return (
    <main className="auth-shell welcome-shell">
      <div className="auth-brand">
        <Brand />
        <p>
          Cash When You Need It.<br />
          <strong>Digital When You Have It.</strong>
        </p>
        <span className="student-badge">
          <span>✦</span> Built for Students
        </span>
      </div>
      <Illustration />
      <div className="welcome-points">
        <span>
          <b className="point-icon blue">◎</b>
          <strong>Nearby students</strong>
        </span>
        <span>
          <b className="point-icon green">✓</b>
          <strong>Safer meetups</strong>
        </span>
        <span>
          <b className="point-icon violet">↗</b>
          <strong>Simple process</strong>
        </span>
      </div>
      <div className="auth-actions">
        <button className="button button-primary button-wide" onClick={onStart}>
          Get started <Icon name="arrow" />
        </button>
        <p>
          Already have an account?{' '}
          <button className="link-button" onClick={onLogin}>
            Log in
          </button>
        </p>
      </div>
      <p className="fine-print">ONPay coordinates exchanges. Payments happen in your UPI app.</p>
    </main>
  )
}

export default Welcome
