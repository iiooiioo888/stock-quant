import type { Task } from "../types/task";
import { X, Copy } from "lucide-react";
import dayjs from "dayjs";
import { EquityCurve, MonthlyReturns, MetricCards } from "./BacktestCharts";

interface TaskDetailProps {
  task: Task;
  onClose: () => void;
  onCancel: (id: string) => void;
}

const statusColors: Record<string, string> = {
  queued: "text-amber-400",
  running: "text-blue-400",
  success: "text-emerald-400",
  failed: "text-red-400",
  cancelled: "text-gray-500",
};

const statusLabels: Record<string, string> = {
  queued: "排隊中",
  running: "運行中",
  success: "已完成",
  failed: "失敗",
  cancelled: "已取消",
};

export function TaskDetail({ task, onClose, onCancel }: TaskDetailProps) {
  const copyId = () => navigator.clipboard.writeText(task.id);

  const result = task.result;
  const equityCurve = result?.equity_curve as { date: string; value: number }[] | undefined;
  const monthlyReturns = result?.monthly_returns as { month: string; return: number }[] | undefined;
  const totalReturn = result?.total_return as number | undefined;

  const metricCards = result
    ? [
        {
          label: "總收益率",
          value: `${totalReturn ?? 0}%`,
          color: (totalReturn ?? 0) >= 0 ? "text-emerald-400" : "text-red-400",
          subtext: `¥${((result.final_value as number) / 10000).toFixed(1)}萬`,
        },
        {
          label: "夏普比率",
          value: String(result.sharpe_ratio ?? "-"),
          color: (result.sharpe_ratio as number) >= 1 ? "text-emerald-400" : "text-gray-100",
        },
        {
          label: "最大回撤",
          value: `${result.max_drawdown}%`,
          color: "text-red-400",
        },
        {
          label: "勝率",
          value: `${result.win_rate}%`,
          color: (result.win_rate as number) >= 50 ? "text-emerald-400" : "text-amber-400",
        },
        {
          label: "總交易次數",
          value: String(result.total_trades ?? "-"),
        },
        {
          label: "年化收益",
          value: `${result.annual_return ?? "-"}%`,
          color: (result.annual_return as number) >= 0 ? "text-emerald-400" : "text-red-400",
        },
        {
          label: "波動率",
          value: `${result.volatility ?? "-"}%`,
        },
        {
          label: "卡瑪比率",
          value: String(result.calmar_ratio ?? "-"),
        },
      ]
    : [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="relative w-full max-w-3xl max-h-[90vh] overflow-y-auto rounded-2xl bg-gray-900 border border-gray-700 shadow-2xl">
        {/* Header */}
        <div className="sticky top-0 flex items-center justify-between p-6 pb-4 bg-gray-900 border-b border-gray-800 z-10">
          <div>
            <h2 className="text-lg font-bold text-gray-100">{task.name}</h2>
            <div className="flex items-center gap-2 mt-1">
              <span className={`text-sm font-medium ${statusColors[task.status]}`}>
                {statusLabels[task.status]}
              </span>
              <span className="text-xs text-gray-500">·</span>
              <span className="text-xs text-gray-500">{task.task_type}</span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-gray-200 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-6">
          {/* Progress */}
          {task.status === "running" && (
            <div>
              <div className="flex justify-between text-sm text-gray-400 mb-2">
                <span>執行進度</span>
                <span className="font-mono">{task.progress.toFixed(1)}%</span>
              </div>
              <div className="w-full h-3 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-blue-600 via-blue-500 to-blue-400 rounded-full transition-all duration-500"
                  style={{ width: `${task.progress}%` }}
                />
              </div>
            </div>
          )}

          {/* Result metrics */}
          {task.status === "success" && result && (
            <>
              <MetricCards metrics={metricCards} />
              {equityCurve && equityCurve.length > 0 && <EquityCurve data={equityCurve} />}
              {monthlyReturns && monthlyReturns.length > 0 && (
                <MonthlyReturns data={monthlyReturns} />
              )}
            </>
          )}

          {/* Error */}
          {task.status === "failed" && task.error_message && (
            <div className="rounded-xl bg-red-500/10 border border-red-500/20 p-4">
              <p className="text-sm text-red-400 font-mono whitespace-pre-wrap">
                {task.error_message}
              </p>
            </div>
          )}

          {/* Meta info */}
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-gray-500 mb-0.5">任務 ID</p>
              <div className="flex items-center gap-1.5">
                <code className="text-gray-300 font-mono text-xs">{task.id.slice(0, 8)}…</code>
                <button onClick={copyId} className="text-gray-600 hover:text-gray-400">
                  <Copy className="w-3 h-3" />
                </button>
              </div>
            </div>
            <div>
              <p className="text-gray-500 mb-0.5">優先級</p>
              <p className="text-gray-300">{task.priority}</p>
            </div>
            <div>
              <p className="text-gray-500 mb-0.5">創建時間</p>
              <p className="text-gray-300">
                {task.created_at ? dayjs(task.created_at).format("YYYY-MM-DD HH:mm:ss") : "-"}
              </p>
            </div>
            <div>
              <p className="text-gray-500 mb-0.5">開始時間</p>
              <p className="text-gray-300">
                {task.started_at ? dayjs(task.started_at).format("YYYY-MM-DD HH:mm:ss") : "-"}
              </p>
            </div>
            <div>
              <p className="text-gray-500 mb-0.5">完成時間</p>
              <p className="text-gray-300">
                {task.finished_at ? dayjs(task.finished_at).format("YYYY-MM-DD HH:mm:ss") : "-"}
              </p>
            </div>
            {task.started_at && task.finished_at && (
              <div>
                <p className="text-gray-500 mb-0.5">執行耗時</p>
                <p className="text-gray-300">
                  {(() => {
                    const sec = (new Date(task.finished_at).getTime() - new Date(task.started_at).getTime()) / 1000;
                    if (sec < 60) return `${sec.toFixed(1)}s`;
                    if (sec < 3600) return `${(sec / 60).toFixed(1)}m`;
                    return `${(sec / 3600).toFixed(1)}h`;
                  })()}
                </p>
              </div>
            )}
            {task.celery_task_id && (
              <div>
                <p className="text-gray-500 mb-0.5">Celery ID</p>
                <code className="text-gray-300 font-mono text-xs">{task.celery_task_id.slice(0, 12)}…</code>
              </div>
            )}
          </div>

          {/* Config */}
          {task.config && (
            <div>
              <p className="text-sm text-gray-500 mb-2">配置參數</p>
              <pre className="rounded-xl bg-gray-800/50 border border-gray-700/50 p-4 text-xs text-gray-300 overflow-x-auto">
                {JSON.stringify(task.config, null, 2)}
              </pre>
            </div>
          )}

          {/* Actions */}
          {(task.status === "running" || task.status === "queued") && (
            <div className="flex justify-end pt-2">
              <button
                onClick={() => onCancel(task.id)}
                className="px-4 py-2 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20
                  hover:bg-amber-500/20 transition text-sm font-medium"
              >
                取消任務
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
