import React, { useEffect, useState } from 'react'
import { api, AnalyticsResponse } from '../api'

export const DashboardPage: React.FC = () => {
  const [data, setData] = useState<AnalyticsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadData = async () => {
    try {
      setLoading(true)
      const res = await api.getAnalytics(14)
      setData(res)
    } catch (err: any) {
      setError(err.message || 'Failed to load analytics')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  if (loading) return <div>Loading platform metrics...</div>
  if (error) return <div className="form-error">{error}</div>
  if (!data) return null

 const stats = data
const trends_14d = data.trend_14d

  return (
    <div>
      <div className="kpi-grid">
        <div className="kpi-card">
          <span className="kpi-label">Total Registered Users</span>
          <span className="kpi-value">{stats.total_users}</span>
          <span className="kpi-sub">Verified student accounts</span>
        </div>

        <div className="kpi-card">
          <span className="kpi-label">Daily Login Events (Today)</span>
          <span className="kpi-value">{stats.total_successful_daily_logins}</span>
          <span className="kpi-sub">Total auth successes</span>
        </div>

        <div className="kpi-card">
          <span className="kpi-label">Daily Active Users (DAU)</span>
          <span className="kpi-value">{stats.unique_daily_active_users}</span>
          <span className="kpi-sub">Unique active students today</span>
        </div>

        <div className="kpi-card success">
          <span className="kpi-label">Completed Volume</span>
          <span className="kpi-value">₹{stats.completed_transaction_volume.toLocaleString()}</span>
          <span className="kpi-sub">{stats.completed_transactions} successful exchanges</span>
        </div>

        <div className="kpi-card">
          <span className="kpi-label">Total Points Awarded</span>
          <span className="kpi-value">{stats.total_points_awarded.toLocaleString()}</span>
          <span className="kpi-sub">Platform reward ledger</span>
        </div>

        <div className="kpi-card warning">
          <span className="kpi-label">Pending Subscriptions</span>
          <span className="kpi-value">{stats.pending_subscriptions}</span>
          <span className="kpi-sub">{stats.active_subscriptions} active paid subscriptions</span>
        </div>
      </div>

      <div className="section-card">
        <div className="section-header">
          <h3 className="section-title">14-Day Activity Trends</h3>
          <button className="btn btn-outline btn-sm" onClick={loadData}>Refresh</button>
        </div>
        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Daily Logins</th>
                <th>Unique Users</th>
                <th>Completed Exchanges</th>
                <th>Volume (₹)</th>
              </tr>
            </thead>
            <tbody>
              {trends_14d.map((row) => (
                <tr key={row.date}>
                  <td className="code-font"><strong>{row.date}</strong></td>
                  <td>{row.logins}</td>
                  <td>
                    <span className="pill pill-neutral">{row.unique_users} DAU</span>
                  </td>
                 <td>{row.completed_tx ?? 0}</td>
                    <td><strong>₹{(row.volume ?? 0).toLocaleString('en-IN')}</strong></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
