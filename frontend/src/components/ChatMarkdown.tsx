import { Fragment, type ReactNode } from 'react'

/**
 * Renders the small Markdown subset FOID AI replies use — paragraphs, **bold**, *italic*,
 * `code`, bullet and numbered lists, and short headings — as React elements.
 * No HTML is ever injected: anything else shows as plain text.
 */

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g

function inline(text: string): ReactNode[] {
  return text.split(INLINE).filter(Boolean).map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4)
      return <strong key={i} className="font-semibold text-neutral-900">{part.slice(2, -2)}</strong>
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2)
      return <code key={i} className="px-1 py-0.5 rounded bg-white/70 text-[12.5px]">{part.slice(1, -1)}</code>
    if (part.startsWith('*') && part.endsWith('*') && part.length > 2)
      return <em key={i}>{part.slice(1, -1)}</em>
    return <Fragment key={i}>{part}</Fragment>
  })
}

type Block =
  | { kind: 'p'; lines: string[] }
  | { kind: 'h'; text: string }
  | { kind: 'ul' | 'ol'; items: string[] }

const BULLET = /^\s*[-*•]\s+(.*)$/
const NUMBER = /^\s*\d+[.)]\s+(.*)$/
const HEADING = /^\s*#{1,6}\s+(.*)$/

function parse(text: string): Block[] {
  const blocks: Block[] = []
  for (const raw of text.replace(/\r\n/g, '\n').split('\n')) {
    const line = raw.trimEnd()
    const last = blocks[blocks.length - 1]
    const b = BULLET.exec(line), n = NUMBER.exec(line), h = HEADING.exec(line)
    if (!line.trim()) { blocks.push({ kind: 'p', lines: [] }); continue }
    if (h) blocks.push({ kind: 'h', text: h[1] })
    else if (b) last?.kind === 'ul' ? last.items.push(b[1]) : blocks.push({ kind: 'ul', items: [b[1]] })
    else if (n) last?.kind === 'ol' ? last.items.push(n[1]) : blocks.push({ kind: 'ol', items: [n[1]] })
    else if (last?.kind === 'p') last.lines.push(line.trim())
    else if ((last?.kind === 'ul' || last?.kind === 'ol') && /^\s{2,}/.test(raw))
      last.items[last.items.length - 1] += ' ' + line.trim()      // wrapped list item
    else blocks.push({ kind: 'p', lines: [line.trim()] })
  }
  return blocks.filter(b => b.kind !== 'p' || b.lines.length > 0)
}

export default function ChatMarkdown({ text }: { text: string }) {
  return (
    <div className="flex flex-col gap-2">
      {parse(text).map((b, i) => {
        if (b.kind === 'h') return <div key={i} className="font-semibold text-neutral-900">{inline(b.text)}</div>
        if (b.kind === 'p') return <p key={i}>{b.lines.map((l, j) => <Fragment key={j}>{j > 0 && <br />}{inline(l)}</Fragment>)}</p>
        const List = b.kind
        return (
          <List key={i} className={`${b.kind === 'ul' ? 'list-disc' : 'list-decimal'} pl-5 flex flex-col gap-1`}>
            {b.items.map((it, j) => <li key={j}>{inline(it)}</li>)}
          </List>
        )
      })}
    </div>
  )
}
