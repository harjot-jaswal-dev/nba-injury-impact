import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import LandingAnimation from './components/ui/LandingAnimation.jsx'
import './index.css'

let hasPlayed = false
try { hasPlayed = !!sessionStorage.getItem('landing-played') } catch {}

function Root() {
  const [showLanding, setShowLanding] = useState(!hasPlayed)

  const handleLandingComplete = () => {
    setShowLanding(false)
    try { sessionStorage.setItem('landing-played', '1') } catch {}
  }

  return (
    <StrictMode>
      <BrowserRouter>
        {showLanding && <LandingAnimation onComplete={handleLandingComplete} />}
        <App />
      </BrowserRouter>
    </StrictMode>
  )
}

createRoot(document.getElementById('root')).render(<Root />)
