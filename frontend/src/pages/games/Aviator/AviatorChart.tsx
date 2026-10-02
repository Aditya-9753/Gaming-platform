import React, { useEffect, useRef, useState } from 'react'
import { formatMultiplier } from '../../../utils/formatters'

export const AVIATOR_COVER_SRC = '/games/aviator/cover.jpg'
export const AVIATOR_PLANE_SRC = '/games/aviator/plane.png'

export interface AviatorChartProps {
  multiplier: number
  phase: 'waiting' | 'betting' | 'flying' | 'crashed'
  countdown: number
  /** Total betting window in seconds, for the countdown bar. */
  bettingTotal?: number
}

/** Flight progress 0→1: climbs quickly at first, then cruises near the top-right. */
const flightProgress = (multiplier: number) => 1 - Math.exp(-(Math.max(multiplier, 1) - 1) / 1.6)

export const AviatorChart: React.FC<AviatorChartProps> = ({
  multiplier,
  phase,
  countdown,
  bettingTotal = 6,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })
  const [crashPoint, setCrashPoint] = useState<{ x: number; y: number } | null>(null)

  useEffect(() => {
    const element = containerRef.current
    if (!element) return
    const observer = new ResizeObserver(([entry]) => {
      setSize({ width: entry.contentRect.width, height: entry.contentRect.height })
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  const { width, height } = size
  const startX = width * 0.06
  const startY = height * 0.86
  const maxX = width * 0.78
  const topY = height * 0.24
  const progress = phase === 'flying' || phase === 'crashed' ? flightProgress(multiplier) : 0
  // Gentle cruise bob once the plane has (nearly) levelled out
  const bob = phase === 'flying' && progress > 0.85 ? Math.sin(Date.now() / 380) * height * 0.015 : 0
  const endX = startX + (maxX - startX) * progress
  const endY = startY - (startY - topY) * Math.pow(progress, 0.85) + bob

  useEffect(() => {
    if (phase === 'crashed') setCrashPoint((point) => point ?? { x: endX, y: endY })
    else setCrashPoint(null)
  }, [phase, endX, endY])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !width || !height) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = window.devicePixelRatio || 1
    canvas.width = width * dpr
    canvas.height = height * dpr
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, width, height)

    // Axes
    ctx.strokeStyle = 'rgba(148, 163, 184, 0.18)'
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(startX, height * 0.08)
    ctx.lineTo(startX, startY)
    ctx.lineTo(width * 0.97, startY)
    ctx.stroke()

    if ((phase === 'flying' || phase === 'crashed') && progress > 0) {
      const controlX = startX + (endX - startX) * 0.55
      const fill = ctx.createLinearGradient(0, endY, 0, startY)
      fill.addColorStop(0, 'rgba(225, 29, 72, 0.45)')
      fill.addColorStop(1, 'rgba(225, 29, 72, 0.02)')

      ctx.beginPath()
      ctx.moveTo(startX, startY)
      ctx.quadraticCurveTo(controlX, startY, endX, endY)
      ctx.lineTo(endX, startY)
      ctx.closePath()
      ctx.fillStyle = fill
      ctx.fill()

      ctx.beginPath()
      ctx.moveTo(startX, startY)
      ctx.quadraticCurveTo(controlX, startY, endX, endY)
      ctx.strokeStyle = phase === 'crashed' ? 'rgba(225, 29, 72, 0.45)' : '#e11d48'
      ctx.lineWidth = 4
      ctx.lineCap = 'round'
      ctx.stroke()
    }
  }, [width, height, phase, progress, startX, startY, endX, endY])

  const planeWidth = Math.min(150, Math.max(84, width * 0.2))
  const planeHeight = planeWidth * (158 / 360)
  const showPlane = phase === 'flying' || phase === 'crashed'
  const planeAt = phase === 'crashed' && crashPoint ? crashPoint : { x: endX, y: endY }
  const planeStyle: React.CSSProperties = {
    width: planeWidth,
    left: planeAt.x - planeWidth * 0.18,
    top: planeAt.y - planeHeight * 0.78,
    transform: phase === 'crashed'
      ? `translate(${width}px, -${height}px) rotate(-25deg)`
      : `rotate(${-12 * (1 - progress * 0.6)}deg)`,
    opacity: phase === 'crashed' ? 0 : 1,
    transition: phase === 'crashed' ? 'transform 0.9s ease-in, opacity 0.9s ease-in' : 'none',
  }

  return (
    <div
      ref={containerRef}
      className="relative w-full h-80 sm:h-[26rem] rounded-3xl border border-dark-border overflow-hidden shadow-inner bg-[#07080d]"
    >
      {/* Rotating sun-ray backdrop */}
      <div
        aria-hidden
        className={`absolute opacity-40 ${phase === 'flying' ? 'animate-[spin_24s_linear_infinite]' : ''}`}
        style={{
          // 300% box centred on the curve origin (6%, 86%) so it rotates around it
          width: '300%',
          height: '300%',
          left: '-144%',
          top: '-64%',
          background: 'repeating-conic-gradient(from 0deg at 50% 50%, rgba(225,29,72,0.10) 0deg 10deg, transparent 10deg 20deg)',
        }}
      />
      <div aria-hidden className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom_left,rgba(225,29,72,0.18),transparent_60%)]" />

      <canvas ref={canvasRef} className="absolute inset-0 w-full h-full" />

      {showPlane && (
        <img
          src={AVIATOR_PLANE_SRC}
          alt=""
          draggable={false}
          className="absolute pointer-events-none select-none drop-shadow-[0_8px_18px_rgba(225,29,72,0.45)]"
          style={planeStyle}
        />
      )}

      {/* Center status overlay */}
      <div className="absolute inset-0 z-10 flex items-center justify-center text-center select-none pointer-events-none">
        {(phase === 'waiting' || phase === 'betting') && (
          <div className="space-y-3 flex flex-col items-center">
            <img src={AVIATOR_COVER_SRC} alt="Aviator" className="w-44 sm:w-56 rounded-2xl shadow-2xl shadow-rose-900/40" />
            {phase === 'betting' ? (
              <>
                <span className="text-xs uppercase tracking-widest font-black text-emerald-400">Place your bets • take off in</span>
                <div className="text-4xl sm:text-5xl font-black font-mono text-white">{countdown}s</div>
                <div className="w-48 h-1.5 bg-dark-card border border-dark-border rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-rose-500 to-emerald-400 transition-all duration-1000 ease-linear"
                    style={{ width: `${Math.min(100, (countdown / Math.max(bettingTotal, 1)) * 100)}%` }}
                  />
                </div>
              </>
            ) : (
              <span className="text-xs uppercase tracking-widest font-bold text-slate-400 animate-pulse">Waiting for next round…</span>
            )}
          </div>
        )}

        {phase === 'flying' && (
          <div className="text-6xl sm:text-7xl font-black font-mono tracking-tighter text-white drop-shadow-2xl">
            {formatMultiplier(multiplier)}
          </div>
        )}

        {phase === 'crashed' && (
          <div className="space-y-1">
            <span className="text-sm font-black uppercase tracking-widest text-rose-500 block">Flew away!</span>
            <div className="text-5xl sm:text-6xl font-black font-mono text-rose-500">{formatMultiplier(multiplier)}</div>
          </div>
        )}
      </div>
    </div>
  )
}
