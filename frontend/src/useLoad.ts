import { useCallback, useEffect, useState } from 'react'
import { messageOf } from './api'

interface LoadState<T> {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => void
}

interface Settled<T> {
  data: T | null
  error: string | null
  load: () => Promise<T> // which request this result belongs to
  version: number
}

/** Loads data when `load` changes (pass a stable function); `reload()` fetches again. */
export function useLoad<T>(load: () => Promise<T>): LoadState<T> {
  const [version, setVersion] = useState(0)
  const [settled, setSettled] = useState<Settled<T> | null>(null)

  useEffect(() => {
    let cancelled = false // ignore responses that arrive after unmount or a newer request
    load().then(
      (data) => {
        if (!cancelled) setSettled({ data, error: null, load, version })
      },
      (err: unknown) => {
        if (!cancelled) {
          setSettled((previous) => ({
            data: previous?.load === load ? previous.data : null,
            error: messageOf(err),
            load,
            version,
          }))
        }
      },
    )
    return () => {
      cancelled = true
    }
  }, [load, version])

  const reload = useCallback(() => setVersion((v) => v + 1), [])
  // Results of a different `load` (e.g. another paper) are never shown.
  const current = settled?.load === load ? settled : null
  return {
    data: current?.data ?? null,
    error: current?.error ?? null,
    loading: current?.version !== version,
    reload,
  }
}
