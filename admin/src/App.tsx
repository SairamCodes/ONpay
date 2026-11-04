import React, { useEffect, useState } from 'react'
import { api, AdminUser, getAdminToken } from './api'
import { LoginPage } from './pages/LoginPage'
import { DashboardPage } from './pages/DashboardPage'
import { UsersPage } from './pages/UsersPage'
import { TransactionsPage } from './pages/TransactionsPage'
import { PointsPage } from './pages/PointsPage'
import { SubscriptionsPage } from './pages/SubscriptionsPage'
import { QRCodePage } from './pages/QRCodePage'
import { AuditLogsPage } from './pages/AuditLogsPage'

export const App: React.FC = () => {
  const [admin, setAdmin] = useState<AdminUser | null>(null)
  const [loading, setLoading] = useState(true)
  const [currentTab, setCurrentTab] = useState<'dashboard' | 'users' | 'transactions' | 'points' | 'subscriptions' | 'qrcode' | 'audit'>('dashboard')
  const [pendingSubsCount, setPendingSubsCount] = useState<number>(0)

  const checkAuth = async () => {
    const token = getAdminToken()
    if (!token) {
      setAdmin(null)
      setLoading(false)
      return
    }
    try {
      setLoading(true)
      const res = await api.getMe()
      setAdmin(res.admin)
      // Quick fetch of pending subscriptions count for badge
      try {
        const subs = await api.getSubscriptions('PENDING', 1, 1)
        setPendingSubsCount(subs.total)
      } catch {
        // Ignore background badge error
      }
    } catch {
      setAdmin(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    checkAuth()

    const handleUnauthorized = () => {
      setAdmin(null)
    }
    window.addEventListener('onpay-admin-unauthorized', handleUnauthorized)
    return () => window.removeEventListener('onpay-admin-unauthorized', handleUnauthorized)
  }, [])

  const handleLogout = async () => {
    await api.logout()
    setAdmin(null)
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', background: '#0f172a', color: '#f8fafc' }}>
        <div>Loading Admin Session...</div>
      </div>
    )
  }

  if (!admin) {
    return <LoginPage onLoginSuccess={checkAuth} />
  }

  return (
    <div className="admin-layout">
      {/* Sidebar Navigation */}
      <aside className="admin-sidebar">
        <div className="sidebar-header">
          <span className="brand-badge">V2</span>
          <span className="brand-title">ONPay Admin</span>
        </div>

        <nav className="sidebar-nav">
          <button
            className={`nav-item ${currentTab === 'dashboard' ? 'active' : ''}`}
            onClick={() => setCurrentTab('dashboard')}
          >
            <span>📊</span> Dashboard
          </button>

          <button
            className={`nav-item ${currentTab === 'subscriptions' ? 'active' : ''}`}
            onClick={() => setCurrentTab('subscriptions')}
          >
            <span>💳</span> Subscriptions
            {pendingSubsCount > 0 && <span className="nav-badge">{pendingSubsCount}</span>}
          </button>

          <button
            className={`nav-item ${currentTab === 'qrcode' ? 'active' : ''}`}
            onClick={() => setCurrentTab('qrcode')}
          >
            <span>📱</span> QR Code
          </button>

          <button
            className={`nav-item ${currentTab === 'users' ? 'active' : ''}`}
            onClick={() => setCurrentTab('users')}
          >
            <span>👥</span> Students
          </button>

          <button
            className={`nav-item ${currentTab === 'transactions' ? 'active' : ''}`}
            onClick={() => setCurrentTab('transactions')}
          >
            <span>💸</span> Transactions
          </button>

          <button
            className={`nav-item ${currentTab === 'points' ? 'active' : ''}`}
            onClick={() => setCurrentTab('points')}
          >
            <span>⭐</span> Points Ledger
          </button>

          <button
            className={`nav-item ${currentTab === 'audit' ? 'active' : ''}`}
            onClick={() => setCurrentTab('audit')}
          >
            <span>🛡️</span> Audit Logs
          </button>
        </nav>

        <div className="sidebar-footer">
          <div className="admin-info">
            <span className="admin-email">{admin.email}</span>
            <span className="admin-role">{admin.role}</span>
          </div>
          <button className="btn-logout" onClick={handleLogout}>Exit</button>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="admin-main">
        <header className="admin-topbar">
          <div>
            <h1 className="page-title">
              {currentTab === 'dashboard' && 'Operations Dashboard'}
              {currentTab === 'subscriptions' && 'Subscription Payments Review'}
              {currentTab === 'qrcode' && 'UPI QR Code Management'}
              {currentTab === 'users' && 'Student Directory & Accounts'}
              {currentTab === 'transactions' && 'Exchanges & Transactions'}
              {currentTab === 'points' && 'Points Incentive Ledger'}
              {currentTab === 'audit' && 'Security & Operational Audit Log'}
            </h1>
            <p className="page-subtitle">ONPay V2 Real-Time Administration & Enforcement</p>
          </div>
        </header>

        <div className="admin-content">
          {currentTab === 'dashboard' && <DashboardPage />}
          {currentTab === 'subscriptions' && <SubscriptionsPage />}
          {currentTab === 'qrcode' && <QRCodePage />}
          {currentTab === 'users' && <UsersPage />}
          {currentTab === 'transactions' && <TransactionsPage />}
          {currentTab === 'points' && <PointsPage />}
          {currentTab === 'audit' && <AuditLogsPage />}
        </div>
      </main>
    </div>
  )
}
