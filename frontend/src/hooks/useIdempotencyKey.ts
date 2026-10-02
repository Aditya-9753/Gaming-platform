import { useState, useCallback } from 'react'

export function useIdempotencyKey(): [string, () => void] {
  const generate = () => crypto.randomUUID()

  const [key, setKey] = useState<string>(generate)
  const rotate = useCallback(() => setKey(generate()), [])
  return [key, rotate]
}
