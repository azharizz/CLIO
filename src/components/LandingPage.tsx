import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from 'react'
import { Link } from '@tanstack/react-router'

type Signal = 'breaking' | 'traced'
type Item = { id: string; label: string; row: number; signal: Signal }

const columns: Item[][] = [
  [{ id: 'v5', label: 'V5', row: 0, signal: 'breaking' }],
  [
    { id: 'sc01', label: 'SC01', row: -1, signal: 'traced' },
    { id: 'sc17', label: 'SC17', row: 0, signal: 'breaking' },
    { id: 'sc25', label: 'SC25', row: 1, signal: 'traced' },
  ],
  [
    { id: 'b01', label: 'B01', row: -1, signal: 'breaking' },
    { id: 'b05', label: 'B05', row: 0, signal: 'breaking' },
    { id: 'b25', label: 'B25', row: 1, signal: 'traced' },
  ],
  [
    { id: 'sc18', label: 'SC18', row: -1, signal: 'breaking' },
    { id: 'sc19', label: 'SC19', row: 0, signal: 'breaking' },
    { id: 'sc24', label: 'SC24', row: 1, signal: 'traced' },
  ],
  [
    { id: 'trace', label: 'TRACE', row: -1, signal: 'breaking' },
    { id: 'impact', label: 'IMPACT', row: 0, signal: 'breaking' },
    { id: 'time', label: 'TIME', row: 1, signal: 'traced' },
  ],
  [{ id: 'decision', label: 'DECISION', row: 0, signal: 'traced' }],
  [
    { id: 'map', label: 'MAP', row: -1, signal: 'traced' },
    { id: 'clio', label: 'CLIO', row: 1, signal: 'traced' },
  ],
]

const stages = ['SOURCE', 'SCENES', 'BEATS', 'IMPACT', 'DECISION', 'TRACE', 'CLIO']
const NS = 'http://www.w3.org/2000/svg'

// The landing wordmark uses the same draw → pulse → reset language as the
// original reference animation, rebuilt as four CLIO glyphs.
const clioGlyphs = [
  [0, 'M760 0H250C112 0 0 112 0 250V1510C0 1648 112 1760 250 1760H760V1440H360C338 1440 320 1422 320 1400V360C320 338 338 320 360 320H760Z'],
  [900, 'M0 0H320V1440H740V1760H0Z'],
  [1740, 'M0 0H320V1760H0Z'],
  [2140, 'M200 0H520C630 0 720 90 720 200V1560C720 1670 630 1760 520 1760H200C90 1760 0 1670 0 1560V200C0 90 90 0 200 0ZM320 320C265 320 240 345 240 400V1360C240 1415 265 1440 320 1440H400C455 1440 480 1415 480 1360V400C480 345 455 320 400 320Z'],
] as const
const clioMarkWidth = 2860

const cropPath = (x: number, y: number, width: number, height: number) => {
  const c = Math.min(11, width * 0.15)
  return `M ${x + c} ${y}H${x}V${y + c} M ${x + width - c} ${y}H${x + width}V${y + c} M${x} ${y + height - c}V${y + height}H${x + c} M${x + width - c} ${y + height}H${x + width}V${y + height - c}`
}

function timers() {
  const ids: number[] = []
  const animations: Animation[] = []
  return {
    later: (fn: () => void, ms: number) => ids.push(window.setTimeout(fn, ms)),
    motion: (el: Element, frames: Keyframe[], options: KeyframeAnimationOptions) => {
      const animation = el.animate?.(frames, options)
      if (animation) animations.push(animation)
      return animation
    },
    clear: () => {
      ids.forEach(window.clearTimeout)
      animations.forEach((animation) => animation.cancel())
    },
  }
}

function LandingGraph({ onLayout, svgRef }: { onLayout: () => void; svgRef: RefObject<SVGSVGElement | null> }) {
  const [size, setSize] = useState({ w: 1000, h: 420 })
  const lastSize = useRef(size)
  const { w, h } = size
  const frameWidth = w < 820 ? Math.max(44, Math.min(70, w * 0.1)) : Math.min(122, w * 0.078)
  const frameHeight = frameWidth / 2.39
  const gap = (w - frameWidth) / 6
  const rowGap = Math.min(frameHeight * 2.3, (h - frameHeight) / 2.3)

  const data = useMemo(
    () =>
      columns.map((column, stage) =>
        column.map((item) => ({
          ...item,
          stage,
          x: stage * gap,
          y: h / 2 + item.row * rowGap - frameHeight / 2,
        })),
      ),
    [gap, h, frameHeight, rowGap],
  )

  const edges = useMemo(
    () =>
      data.slice(0, -1).flatMap((column, stage) =>
        column.flatMap((from) =>
          data[stage + 1]!.flatMap((to) => {
            if (column.length > 2 && data[stage + 1]!.length > 1 && Math.abs(from.row - to.row) > 1) return []
            const x1 = from.x + frameWidth
            const x2 = to.x
            const mid = x1 + (x2 - x1) / 2
            return [
              {
                id: `${from.id}-${to.id}`,
                stage,
                signal: from.signal === 'breaking' && to.signal === 'breaking' ? 'breaking' : ('traced' as Signal),
                d:
                  Math.abs(from.y - to.y) < 1
                    ? `M${x1} ${from.y + frameHeight / 2}H${x2}`
                    : `M${x1} ${from.y + frameHeight / 2}H${mid}V${to.y + frameHeight / 2}H${x2}`,
              },
            ]
          }),
        ),
      ),
    [data, frameHeight, frameWidth],
  )

  useEffect(() => {
    const parent = svgRef.current?.parentElement
    if (!parent) return
    const update = () => {
      const rect = parent.getBoundingClientRect()
      if (rect.width && rect.height) {
        const next = { w: Math.round(rect.width), h: Math.round(rect.height) }
        if (lastSize.current.w === next.w && lastSize.current.h === next.h) return
        lastSize.current = next
        setSize(next)
        onLayout()
      }
    }
    update()
    const observer = new ResizeObserver(update)
    observer.observe(parent)
    return () => observer.disconnect()
  }, [onLayout, svgRef])

  return (
    <svg
      ref={svgRef}
      className="fg-proto-graph"
      viewBox={`0 0 ${w} ${h}`}
      role="img"
      aria-label="CLIO dependency graph from revision V5 through editorial decision"
    >
      <title>CLIO revision V5 dependency signal</title>
      <g>
        {edges.map((edge) => (
          <path key={edge.id} d={edge.d} className={`fg-proto-edge fg-proto-edge--${edge.signal}`} data-edge={edge.stage} data-signal={edge.signal} />
        ))}
      </g>
      <g data-pulse-layer="true" />
      <g>
        {data.flat().map((node) => (
          <g key={node.id} data-node={node.stage} className={`fg-proto-node fg-proto-node--${node.signal}`}>
            <rect x={node.x} y={node.y} width={frameWidth} height={frameHeight} className="fg-proto-node__body" />
            <path d={cropPath(node.x, node.y, frameWidth, frameHeight)} className="fg-proto-node__crop" />
            <line x1={node.x} y1={node.y + frameHeight} x2={node.x + frameWidth} y2={node.y + frameHeight} className="fg-proto-node__edge" />
            <text x={node.x + frameWidth / 2} y={node.y + frameHeight / 2 + 4} className="fg-proto-node__id" textAnchor="middle">
              {node.label}
            </text>
          </g>
        ))}
      </g>
    </svg>
  )
}

function ClioMark({ svgRef }: { svgRef: RefObject<SVGSVGElement | null> }) {
  return (
    <svg ref={svgRef} className="fg-proto-mark" viewBox={`0 0 ${clioMarkWidth} 1760`} role="img" aria-label="CLIO">
      <title>CLIO</title>
      <g>
        {clioGlyphs.map(([offset, d]) => (
          <path key={`fill-${offset}`} d={d} transform={`translate(${offset} 0)`} className="fg-proto-mark__fill" data-clio-fill="true" fillRule="evenodd" />
        ))}
      </g>
      <g>
        {clioGlyphs.map(([offset, d]) => (
          <path key={`line-${offset}`} d={d} transform={`translate(${offset} 0)`} className="fg-proto-mark__line" data-clio-line="true" fillRule="evenodd" />
        ))}
      </g>
      <g data-clio-pulses="true" />
    </svg>
  )
}

type LandingLink = { element: SVGPathElement; d: string; severity: Signal; stage: number; length: number }

/** Ports the reference prototype's single continuous graph → wordmark signal. */
function LandingMotion({
  graphRef,
  markRef,
  onActive,
  layoutVersion,
}: {
  graphRef: RefObject<SVGSVGElement | null>
  markRef: RefObject<SVGSVGElement | null>
  onActive: (stage: number) => void
  layoutVersion: number
}) {
  useEffect(() => {
    const graph = graphRef.current
    const mark = markRef.current
    const graphPulseLayer = graph?.querySelector<SVGGElement>('[data-pulse-layer]')
    const markPulseLayer = mark?.querySelector<SVGGElement>('[data-clio-pulses]')
    if (!graph || !mark || !graphPulseLayer || !markPulseLayer) return

    const nodes = [...graph.querySelectorAll<SVGGElement>('[data-node]')]
    const links: LandingLink[] = [...graph.querySelectorAll<SVGPathElement>('[data-edge]')].map((element) => ({
      element,
      d: element.getAttribute('d') ?? '',
      severity: element.dataset.signal === 'breaking' ? 'breaking' : 'traced',
      stage: Number(element.dataset.edge ?? 0),
      length: element.getTotalLength(),
    }))
    const letters = [...mark.querySelectorAll<SVGPathElement>('[data-clio-line]')].map((element, index) => ({
      element,
      fill: mark.querySelectorAll<SVGPathElement>('[data-clio-fill]')[index]!,
      d: element.getAttribute('d') ?? '',
      transform: element.getAttribute('transform') ?? '',
      length: element.getTotalLength(),
    }))
    const { later, motion, clear } = timers()

    if (matchMedia('(prefers-reduced-motion: reduce)').matches) {
      nodes.forEach((node) => (node.style.opacity = '1'))
      links.forEach(({ element }) => {
        element.style.strokeDasharray = 'none'
        element.style.strokeDashoffset = '0'
      })
      letters.forEach(({ element, fill }) => {
        element.style.strokeDasharray = 'none'
        element.style.strokeDashoffset = '0'
        fill.style.opacity = '1'
      })
      onActive(-1)
      return clear
    }

    // Reference intro: assemble each graph column, then draw the CLIO outlines.
    nodes.forEach((node) => (node.style.opacity = '0'))
    links.forEach(({ element, length }) => {
      element.style.strokeDasharray = `${length}`
      element.style.strokeDashoffset = `${length}`
    })
    letters.forEach(({ element, fill, length }) => {
      element.style.strokeDasharray = `${length}`
      element.style.strokeDashoffset = `${length}`
      fill.style.opacity = '0'
    })

    const step = 175
    columns.forEach((_, stage) => {
      later(() => {
        onActive(stage)
        nodes
          .filter((node) => node.dataset.node === String(stage))
          .forEach((node, index) =>
            motion(node, [{ opacity: 0 }, { opacity: 1 }], {
              duration: 290,
              delay: index * 64,
              fill: 'forwards',
              easing: 'cubic-bezier(.2,0,0,1)',
            }),
          )
        links
          .filter(({ stage: linkStage }) => linkStage === stage - 1)
          .forEach(({ element, length }) =>
            motion(element, [{ strokeDashoffset: length }, { strokeDashoffset: 0 }], {
              duration: 320,
              fill: 'forwards',
              easing: 'cubic-bezier(.2,0,0,1)',
            }),
          )
      }, 140 + stage * step)
    })

    const afterGraph = 140 + columns.length * step + 180
    letters.forEach(({ element, length }, index) => {
      later(
        () =>
          motion(element, [{ strokeDashoffset: length }, { strokeDashoffset: 0 }], {
            duration: 420,
            fill: 'forwards',
            easing: 'cubic-bezier(.2,0,0,1)',
          }),
        afterGraph + index * 72,
      )
    })

    const byStage = Array.from({ length: 6 }, (_, stage) => links.filter((link) => link.stage === stage))
    const pulse = (layer: SVGGElement, d: string, transform: string, length: number, severity: Signal, className: string) => {
      const dash = Math.max(className === 'graph' ? 14 : 30, length * (className === 'graph' ? 0.15 : 0.13))
      const path = document.createElementNS(NS, 'path')
      path.setAttribute('d', d)
      if (transform) path.setAttribute('transform', transform)
      path.setAttribute('class', className === 'graph' ? `fg-proto-pulse fg-proto-pulse--${severity}` : `fg-proto-mark__pulse fg-proto-mark__pulse--${severity}`)
      path.style.strokeDasharray = `${dash} ${length}`
      path.style.strokeDashoffset = `${dash}`
      layer.append(path)
      const animation = motion(path, [{ strokeDashoffset: dash }, { strokeDashoffset: -length }], {
        duration: className === 'graph' ? 480 : 760,
        easing: 'cubic-bezier(.34,0,.22,1)',
        fill: 'forwards',
      })
      if (animation) animation.onfinish = () => path.remove()
    }

    let stageIndex = 0
    const runGraphSignal = () => {
      onActive(stageIndex + 1)
      byStage[stageIndex]?.forEach((link) => pulse(graphPulseLayer, link.d, '', link.length, link.severity, 'graph'))
      stageIndex += 1
      if (stageIndex >= byStage.length) later(runMarkSignal, 300)
      else later(runGraphSignal, 300)
    }
    const runMarkSignal = () => {
      onActive(-1)
      letters.forEach(({ element, fill, d, transform, length }, index) => {
        later(() => {
          pulse(markPulseLayer, d, transform, length, index < 2 ? 'breaking' : 'traced', 'mark')
          motion(fill, [{ opacity: 0 }, { opacity: 1 }], { duration: 300, delay: 420, fill: 'forwards', easing: 'linear' })
        }, index * 118)
      })
      const markTotal = letters.length * 118 + 900
      later(() => {
        letters.forEach(({ fill }, index) => motion(fill, [{ opacity: 1 }, { opacity: 0 }], { duration: 340, delay: index * 40, fill: 'forwards', easing: 'linear' }))
        later(() => {
          stageIndex = 0
          runGraphSignal()
        }, letters.length * 40 + 520)
      }, markTotal + 1700)
    }

    later(() => {
      onActive(-1)
      runGraphSignal()
    }, afterGraph + letters.length * 72 + 560)

    return () => {
      clear()
      graphPulseLayer.replaceChildren()
      markPulseLayer.replaceChildren()
    }
  }, [graphRef, markRef, onActive, layoutVersion])

  return null
}

const timecode = (frame: number) => {
  const seconds = Math.floor(frame / 24)
  return [Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, seconds % 60, frame % 24]
    .map((value) => String(value).padStart(2, '0'))
    .join(':')
}

export function LandingPage() {
  const [frame, setFrame] = useState(0)
  const [active, setActive] = useState(-1)
  const [layoutVersion, setLayoutVersion] = useState(0)
  const graphRef = useRef<SVGSVGElement | null>(null)
  const markRef = useRef<SVGSVGElement | null>(null)
  const onGraphLayout = useCallback(() => setLayoutVersion((version) => version + 1), [])

  useEffect(() => {
    const id = window.setInterval(() => setFrame((value) => value + 1), 1000 / 24)
    return () => clearInterval(id)
  }, [])

  return (
    <main className="fg-landing fg-proto-sheet" data-testid="landing">
      <section className="fg-proto-stage" aria-label="CLIO dependency artifact">
        <LandingGraph onLayout={onGraphLayout} svgRef={graphRef} />
      </section>
      <section className="fg-proto-markband" aria-label="CLIO wordmark">
        <div className="fg-proto-markwrap">
          <ClioMark svgRef={markRef} />
        </div>
        <span className="fg-proto-order">01</span>
      </section>
      <nav className="fg-proto-ruler" aria-label="Pipeline stages">
        <ol>
          {stages.map((stage, index) => (
            <li key={stage} data-live={active === index ? '' : undefined}>
              {stage}
            </li>
          ))}
        </ol>
      </nav>
      <div className="fg-proto-corner fg-proto-corner--tl">
        <Link to="/workspace">CLIO–01</Link>
      </div>
      <div className="fg-proto-corner fg-proto-corner--tr">
        <Link to="/workspace">ENTER</Link>
        <Link to="/workspace">ARCHIVE</Link>
      </div>
      <div className="fg-proto-corner fg-proto-corner--bl">
        <span>SCRIPT → DELIVERY</span>
      </div>
      <div className="fg-proto-corner fg-proto-corner--br">
        <span>{timecode(frame)}</span>
      </div>
      <div className="fg-proto-ticks" aria-hidden="true">
        {[18, 10, 10, 26, 10, 10, 18, 10, 14, 10, 26, 10, 10, 18].map((width, index) => (
          <i key={index} style={{ width }} />
        ))}
      </div>
      <LandingMotion graphRef={graphRef} markRef={markRef} onActive={setActive} layoutVersion={layoutVersion} />
    </main>
  )
}
