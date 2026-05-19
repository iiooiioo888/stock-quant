import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  BarChart,
  Bar,
  Cell,
} from "recharts";

interface EquityPoint {
  date: string;
  value: number;
}

interface MonthlyReturn {
  month: string;
  return: number;
}

/* ── Equity Curve ── */

export function EquityCurve({ data }: { data: EquityPoint[] }) {
  if (!data || data.length === 0) return null;

  const formatValue = (v: number) => `¥${(v / 10000).toFixed(1)}萬`;
  const formatDate = (d: string) => d.slice(5); // MM-DD

  return (
    <div className="rounded-xl bg-gray-800/50 border border-gray-700/50 p-4">
      <h4 className="text-sm font-medium text-gray-300 mb-3">收益曲線</h4>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={data} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#6366f1" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#6366f1" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis
            dataKey="date"
            tickFormatter={formatDate}
            stroke="#6b7280"
            fontSize={11}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            tickFormatter={formatValue}
            stroke="#6b7280"
            fontSize={11}
            tickLine={false}
            width={70}
          />
          <Tooltip
            contentStyle={{
              background: "#1f2937",
              border: "1px solid #374151",
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: "#9ca3af" }}
            formatter={(value) => [`¥${Number(value).toLocaleString()}`, "淨值"]}
            labelFormatter={(label) => String(label)}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke="#6366f1"
            strokeWidth={2}
            fill="url(#equityGrad)"
            dot={false}
            activeDot={{ r: 4, fill: "#6366f1" }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

/* ── Monthly Returns Bar Chart ── */

export function MonthlyReturns({ data }: { data: MonthlyReturn[] }) {
  if (!data || data.length === 0) return null;

  return (
    <div className="rounded-xl bg-gray-800/50 border border-gray-700/50 p-4">
      <h4 className="text-sm font-medium text-gray-300 mb-3">月度收益率</h4>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={data} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis
            dataKey="month"
            stroke="#6b7280"
            fontSize={10}
            tickLine={false}
            interval={Math.max(0, Math.floor(data.length / 8))}
          />
          <YAxis
            tickFormatter={(v: number) => `${v}%`}
            stroke="#6b7280"
            fontSize={11}
            tickLine={false}
            width={45}
          />
          <Tooltip
            contentStyle={{
              background: "#1f2937",
              border: "1px solid #374151",
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: "#9ca3af" }}
            formatter={(value) => [`${Number(value).toFixed(2)}%`, "收益率"]}
          />
          <Bar dataKey="return" radius={[3, 3, 0, 0]}>
            {data.map((entry, index) => (
              <Cell
                key={index}
                fill={entry.return >= 0 ? "#34d399" : "#f87171"}
                fillOpacity={0.8}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/* ── Metric Cards Grid ── */

interface MetricCardProps {
  label: string;
  value: string;
  color?: string;
  subtext?: string;
}

export function MetricCards({ metrics }: { metrics: MetricCardProps[] }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
      {metrics.map((m) => (
        <div
          key={m.label}
          className="rounded-xl bg-gray-800/50 border border-gray-700/50 p-3"
        >
          <p className="text-xs text-gray-500 mb-1">{m.label}</p>
          <p className={`text-lg font-bold font-mono ${m.color ?? "text-gray-100"}`}>
            {m.value}
          </p>
          {m.subtext && <p className="text-xs text-gray-600 mt-0.5">{m.subtext}</p>}
        </div>
      ))}
    </div>
  );
}
