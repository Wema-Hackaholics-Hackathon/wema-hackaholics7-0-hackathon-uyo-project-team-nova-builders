import { useEffect, useRef, useState } from 'react'

interface Tab<T extends string> {
  key: T
  label: string
}

interface SegmentedTabsProps<T extends string> {
  tabs: Tab<T>[]
  value: T
  onChange: (key: T) => void
}

export default function SegmentedTabs<T extends string>({
  tabs,
  value,
  onChange,
}: SegmentedTabsProps<T>) {
  const trackRef  = useRef<HTMLDivElement>(null)
  const btnRefs   = useRef<(HTMLButtonElement | null)[]>([])
  const [pill, setPill] = useState({ left: 0, width: 0 })

  /* Recompute sliding pill geometry whenever value changes */
  useEffect(() => {
    const idx = tabs.findIndex(t => t.key === value)
    const btn = btnRefs.current[idx]
    const track = trackRef.current
    if (!btn || !track) return
    const bRect = btn.getBoundingClientRect()
    const tRect = track.getBoundingClientRect()
    setPill({ left: bRect.left - tRect.left, width: bRect.width })
  }, [value, tabs])

  return (
    <div
      ref={trackRef}
      className="relative flex items-center rounded-full p-1"
      style={{ background: '#f0f0f0' }}
    >
      {/* Sliding white pill */}
      <span
        aria-hidden
        className="absolute rounded-full bg-white shadow-sm"
        style={{
          left:   pill.left,
          width:  pill.width,
          top:    4,
          bottom: 4,
          transition: 'left 220ms cubic-bezier(.4,0,.2,1), width 220ms cubic-bezier(.4,0,.2,1)',
        }}
      />

      {/* Tab buttons */}
      {tabs.map((tab, i) => (
        <button
          key={tab.key}
          ref={el => { btnRefs.current[i] = el }}
          onClick={() => onChange(tab.key)}
          className="relative z-10 px-4 sm:px-8 py-2 rounded-full text-[13px] font-medium transition-colors duration-150 whitespace-nowrap"
          style={{
            color: value === tab.key ? '#18181b' : '#9a9a9a',
            fontWeight: value === tab.key ? 700 : 500,
          }}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}
