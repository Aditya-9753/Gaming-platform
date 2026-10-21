import { useState } from 'react'

/**
 * Calls `onChange` during render whenever `value` changes (not on mount), so
 * the caller can reset its own state right away instead of in an effect that
 * would paint stale state first. This is React's "adjusting state when a prop
 * changes" pattern: https://react.dev/learn/you-might-not-need-an-effect
 * `onChange` may only update state of the component calling this hook.
 */
export function useOnChange<T>(value: T, onChange: (value: T) => void): void {
  const [prev, setPrev] = useState<{ value: T }>({ value })
  if (!Object.is(prev.value, value)) {
    setPrev({ value })
    onChange(value)
  }
}
