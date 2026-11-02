import {
  ComposedChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from 'recharts'

const BRAND      = '#c026d3'
const BRAND_LITE = '#f5d0fe'
const PINK       = '#e879f9'

const naira = (n: number) => '₦' + n.toLocaleString('en-NG')

const defaultData = [
  { week: 'Week 1', income: 32000,  expense: 28000 },
  { week: 'Week 2', income: 90000,  expense: 55000 },
  { week: 'Week 3', income: 64000,  expense: 80000 },
  { week: 'Week 4', income: 50000,  expense: 22000 },
  { week: 'Week 5', income: 120000, expense: 95000 },
  { week: 'Week 6', income: 75000,  expense: 45000 },
  { week: 'Week 7', income: 129000, expense: 110000 },
]

interface DataPoint {
  week: string
  income: number
  expense: number
}

interface IncomeExpenseChartProps {
  data?: DataPoint[]
  height?: number
  title?: string
  subtitle?: string
  /** series names for the legend/tooltip */
  names?: [string, string]
  /** false = plain counts instead of naira */
  money?: boolean
}

export default function IncomeExpenseChart({
  data = defaultData,
  height = 380,
  title = 'Income vs. expenses',
  subtitle = 'Last 14 days across all connected banks',
  names = ['Income', 'Expenses'],
  money = true,
}: IncomeExpenseChartProps) {
  const fmt = (n: number) => money ? naira(n) : n.toLocaleString('en-NG')
  const short = (v: number) => `${money ? '₦' : ''}${v >= 1000 ? Math.round(v / 1000) + 'k' : v}`
  return (
    <div className="bg-white border border-neutral-200 rounded-2xl p-5">
      <div className="font-bold text-[15px] text-neutral-900 mb-0.5">{title}</div>
      <div className="text-[12px] text-neutral-400 mb-4">{subtitle}</div>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={data} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
          <defs>
            <linearGradient id="gradIncomeChart" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor={BRAND}      stopOpacity={0.25} />
              <stop offset="100%" stopColor={BRAND}      stopOpacity={0.02} />
            </linearGradient>
            <linearGradient id="gradExpenseChart" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor={BRAND_LITE} stopOpacity={0.45} />
              <stop offset="100%" stopColor={BRAND_LITE} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#f4f4f5" vertical={false} />
          <XAxis
            dataKey="week"
            tick={{ fontSize: 11, fill: '#a1a1aa' }}
            axisLine={false} tickLine={false}
          />
          <YAxis
            domain={[0, money ? 'dataMax + 20000' : 'auto']}
            tick={{ fontSize: 11, fill: '#a1a1aa' }}
            axisLine={false} tickLine={false}
            tickFormatter={short}
            width={56}
          />
          <Tooltip
            formatter={(val, name) => [fmt(Number(val)), name === 'income' ? names[0] : names[1]]}
            contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e4e4e7' }}
          />
          <Area type="monotone" dataKey="income" stroke={BRAND} strokeWidth={2} fill="url(#gradIncomeChart)"
            dot={{ r: 3, fill: '#fff', stroke: BRAND, strokeWidth: 2 }}
            activeDot={{ r: 4, fill: BRAND }}
          />
          <Area type="monotone" dataKey="expense" stroke={PINK} strokeWidth={2} fill="url(#gradExpenseChart)"
            dot={{ r: 3, fill: '#fff', stroke: PINK, strokeWidth: 2 }}
            activeDot={{ r: 4, fill: PINK }}
          />
          <Legend
            verticalAlign="bottom"
            align="right"
            iconType="circle"
            iconSize={10}
            wrapperStyle={{ fontSize: 12, paddingTop: 12 }}
            formatter={(value) => (
              <span style={{ color: '#71717a' }}>
                {value === 'income' ? names[0] : names[1]}
              </span>
            )}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
