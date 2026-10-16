import { Link, NavLink, Route, Routes } from 'react-router'
import { AboutPage } from './pages/AboutPage'
import { AskPage } from './pages/AskPage'
import { PaperDetailPage } from './pages/PaperDetailPage'
import { PapersPage } from './pages/PapersPage'

export function App() {
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="site-header">
        <Link to="/" className="brand">
          PaperTrail AI
        </Link>
        <nav aria-label="Main">
          <NavLink to="/" end>
            Papers
          </NavLink>
          <NavLink to="/ask">Ask</NavLink>
          <NavLink to="/about">About</NavLink>
        </nav>
      </header>
      <main id="main">
        <Routes>
          <Route path="/" element={<PapersPage />} />
          <Route path="/papers/:paperId" element={<PaperDetailPage />} />
          <Route path="/ask" element={<AskPage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="*" element={<p>Page not found.</p>} />
        </Routes>
      </main>
    </>
  )
}
