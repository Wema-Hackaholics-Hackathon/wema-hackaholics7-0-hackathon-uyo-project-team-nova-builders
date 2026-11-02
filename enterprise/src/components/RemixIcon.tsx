interface RemixIconProps {
  /** Remix icon class name e.g. "ri-dashboard-line" */
  name: string
  /** Size in px applied to both width and height. Default: 20 */
  size?: number
  /** Icon colour. Default: inherits from parent */
  color?: string
  /** Show pointer cursor on hover. Default: false */
  clickable?: boolean
  /** Extra Tailwind / CSS classes */
  className?: string
  style?: React.CSSProperties
  onClick?: React.MouseEventHandler<HTMLElement>
  'aria-label'?: string
}

export default function RemixIcon({
  name,
  size = 20,
  color,
  clickable = false,
  className = '',
  style,
  onClick,
  'aria-label': ariaLabel,
}: RemixIconProps) {
  return (
    <i
      className={[
        name,
        clickable ? 'cursor-pointer' : '',
        className,
      ].filter(Boolean).join(' ')}
      style={{
        fontSize: size,
        width: size,
        height: size,
        lineHeight: `${size}px`,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
        ...(color ? { color } : {}),
        ...style,
      }}
      onClick={onClick}
      aria-label={ariaLabel}
      role={onClick ? 'button' : undefined}
    />
  )
}
