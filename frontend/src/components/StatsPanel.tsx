import { useState, useEffect, useCallback } from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import {
  TrendingUp,
  Clock,
  CheckCircle2,
  Target,
  Layers,
} from "lucide-react";
import type { TaskStats } from "../types/task";
import { fetchStats } from "../services/api";

const PIE_COLORS = ["#6366f1", "#34d399", "#f59e0b", "#f87171", "#8b5cf6"];

export function StatsPanel() {
  const [stats, setStats] = useState<TaskStats | null>(null);
  const [expanded, setExpanded] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await fetchStats();
      setStats(data);
    } catch {
      // silently ignore
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
  }, [load]);

  if (!stats) return null;

  const typeData = Object.entries(stats.by_type).map(([name, value]) => ({
    name,
    value,
  }));

  const formatSeconds = (s: number | null) => {
    if (s === null) return "-";
    if (s < 60) return `${s.toFixed(0)}s`;
    return `${(s / 60).toFixed(1)}m`;
  };

  return (
    <div className="mb-6">
      {/* Toggle */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-sm text-gray-400 hover:text-gray-200 transition mb-3"
      >
        <TrendingUp className="w-4 h-4" />
        <span className="font-medium">統計分析</span>
        <span className="text-xs text-gray-600">{expanded ? "收起" : "展開"}</span>
      </button>

      {expanded && (
        <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-5 space-y-5">
          {/* Key metrics row */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <MetricItem
              icon={Target}
              label="成功率"
              value={`${stats.success_rate}%`}
              color="text-emerald-400"
              bg="bg-emerald-400/10"
            />
            <MetricItem
              icon={Clock}
              label="平均耗時"
              value={formatSeconds(stats.avg_execution_seconds)}
              color="text-blue-400"
              bg="bg-blue-400/10"
            />
            <MetricItem
              icon={CheckCircle2}
              label="完成/總數"
              value={`${stats.completed}/${stats.total}`}
              color="text-gray-200"
              bg="bg-gray-700/30"
            />
            <MetricItem
              icon={Layers}
              label="任務類型"
              value={`${typeData.length}`}
              color="text-purple-400"
              bg="bg-purple-400/10"
            />
          </div>

          {/* Charts row */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Daily activity */}
            {stats.daily_activity.length > 0 && (
              <div className="rounded-xl bg-gray-800/50 border border-gray-700/50 p-4">
                <h4 className="text-sm font-medium text-gray-300 mb-3">近 14 天任務量</h4>
                <ResponsiveContainer width="100%" height={150}>
                  <BarChart data={stats.daily_activity}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis
                      dataKey="date"
                      stroke="#6b7280"
                      fontSize={10}
                      tickLine={false}
                      tickFormatter={(d: string) => d.slice(5)}
                    />
                    <YAxis stroke="#6b7280" fontSize={10} tickLine={false} width={30} />
                    <Tooltip
                      contentStyle={{
                        background: "#1f2937",
                        border: "1px solid #374151",
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                      labelStyle={{ color: "#9ca3af" }}
                      formatter={(value) => [value, "任務數"]}
                    />
                    <Bar dataKey="count" fill="#6366f1" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* Type distribution */}
            {typeData.length > 0 && (
              <div className="rounded-xl bg-gray-800/50 border border-gray-700/50 p-4">
                <h4 className="text-sm font-medium text-gray-300 mb-3">任務類型分佈</h4>
                <ResponsiveContainer width="100%" height={150}>
                  <PieChart>
                    <Pie
                      data={typeData}
                      cx="50%"
                      cy="50%"
                      innerRadius={35}
                      outerRadius={60}
                      paddingAngle={3}
                      dataKey="value"
                    >
                      {typeData.map((_, index) => (
                        <Cell key={index} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{
                        background: "#1f2937",
                        border: "1px solid #374151",
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                      formatter={(value, name) => [value, String(name)]}
                    />
                  </PieChart>
                </ResponsiveContainer>
                <div className="flex flex-wrap gap-3 mt-2 justify-center">
                  {typeData.map((item, i) => (
                    <div key={item.name} className="flex items-center gap-1.5 text-xs text-gray-400">
                      <span
                        className="w-2.5 h-2.5 rounded-full"
                        style={{ background: PIE_COLORS[i % PIE_COLORS.length] }}
                      />
                      {item.name}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function MetricItem({
  icon: Icon,
  label,
  value,
  color,
  bg,
}: {
  icon: typeof TrendingUp;
  label: string;
  value: string;
  color: string;
  bg: string;
}) {
  return (
    <div className="flex items-center gap-3">
      <div className={`p-2 rounded-lg ${bg}`}>
        <Icon className={`w-4 h-4 ${color}`} />
      </div>
      <div>
        <p className="text-xs text-gray-500">{label}</p>
        <p className="text-lg font-bold text-gray-100 font-mono">{value}</p>
      </div>
    </div>
  );
}
