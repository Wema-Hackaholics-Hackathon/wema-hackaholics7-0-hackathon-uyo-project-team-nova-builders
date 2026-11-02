interface CardProps {
  children: React.ReactNode
  /** Extra Tailwind classes e.g. "p-8" to override default padding */
  className?: string
  style?: React.CSSProperties
}

export default function Card({ children, className = '', style }: CardProps) {
  return (
    <div
      className={`bg-white shadow-sm rounded-2xl p-6 relative min-h-[150px] flex flex-col justify-center ${className}`}
      style={style}
    >
      {children}
    </div>
  )
}
