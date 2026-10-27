export function resolveApiBase(configuredBase, isDevelopment, developmentHost = 'localhost') {
  const configured = typeof configuredBase === 'string' ? configuredBase.trim() : ''
  if (configured) return configured.replace(/\/+$/, '')
  if (!isDevelopment) return ''
  const host = typeof developmentHost === 'string' && developmentHost.trim() ? developmentHost.trim() : 'localhost'
  const urlHost = host.includes(':') && !host.startsWith('[') ? `[${host}]` : host
  return `http://${urlHost}:8000`
}
