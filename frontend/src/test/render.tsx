import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router'

/** Render a page inside a router, optionally at a parameterised route like /papers/:paperId. */
export function renderAt(element: ReactElement, url = '/', pattern = '*') {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path={pattern} element={element} />
      </Routes>
    </MemoryRouter>,
  )
}
