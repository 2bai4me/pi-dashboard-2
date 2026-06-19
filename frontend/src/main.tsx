import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './styles.css'
import App from './App.tsx'

// Global error handler for debugging
window.addEventListener('error', function(e) {
  console.error('GLOBAL ERROR:', e.message, e.error);
  const el = document.getElementById('root');
  if (el) {
    el.innerHTML = '<div style="color:#f85149;padding:20px;font-family:monospace;font-size:14px;background:#0e1217;min-height:100vh">' +
      '<h2>Pi Dashboard Error</h2>' +
      '<p>' + e.message + '</p>' +
      '<pre style="color:#8b949e;font-size:12px;margin-top:8px">' + (e.error?.stack || 'no stack') + '</pre>' +
      '</div>';
  }
  return true;
});

window.addEventListener('unhandledrejection', function(e) {
  console.error('UNHANDLED REJECTION:', e.reason);
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
