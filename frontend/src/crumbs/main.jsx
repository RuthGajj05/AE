import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './crumbs.css'
import CrumbsApp from './CrumbsApp.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <CrumbsApp />
  </StrictMode>,
)
