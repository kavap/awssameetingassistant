import { Component, StrictMode } from 'react'
import type { ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

class RootErrorBoundary extends Component<{ children: ReactNode }, { error: string | null }> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(e: Error) {
    return { error: e.message };
  }
  render() {
    if (this.state.error) {
      return (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100vh', background: '#0f172a', color: '#94a3b8', fontFamily: 'monospace', padding: '2rem', textAlign: 'center' }}>
          <p style={{ color: '#f87171', marginBottom: '0.5rem', fontSize: '0.875rem' }}>Application error</p>
          <p style={{ fontSize: '0.75rem', color: '#64748b', maxWidth: '600px' }}>{this.state.error}</p>
          <button
            onClick={() => this.setState({ error: null })}
            style={{ marginTop: '1rem', padding: '0.375rem 0.75rem', background: '#334155', color: '#cbd5e1', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem' }}
          >
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RootErrorBoundary>
      <App />
    </RootErrorBoundary>
  </StrictMode>,
)
