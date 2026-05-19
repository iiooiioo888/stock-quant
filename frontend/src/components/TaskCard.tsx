import type { Task } from "../types/task";
import {
  Play,
  Clock,
  CheckCircle2,
  XCircle,
  Ban,
  MoreVertical,
  Trash2,
  X as XIcon,
} from "lucide-react";
import { useState, useRef, useEffect, useMemo } from "react";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import "dayjs/locale/zh-cn";

dayjs.extend(relativeTime);
dayjs.locale("zh-cn");

const statusConfig: Record<
  Task["status"],
  { label: string; icon: typeof Play; color: string; bg: string; ring: string }
> = {
  queued: {
    label: "排隊中",
    icon: Clock,
    color: "text-amber-400",
    bg: "bg-amber-400/10",
    ring: "ring-amber-400/30",
  },
  running: {
    label: "運行中",
    icon: Play,
    color: "text-blue-400",
    bg: "bg-blue-400/10",
    ring: "ring-blue-400/30",
  },
  success: {
    label: "已完成",
    icon: CheckCircle2,
    color: "text-emerald-400",
    bg: "bg-emerald-400/10",
    ring: "ring-emerald-400/30",
  },
  failed: {
    label: "失敗",
    icon: XCircle,
    color: "text-red-400",
    bg: "bg-red-400/10",
    ring: "ring-red-400/30",
  },
  cancelled: {
    label: "已取消",
    icon: Ban,
    color: "text-gray-500",
    bg: "bg-gray-500/10",
    ring: "ring-gray-500/30",
  },
};

function useETA(task: Task): string | null {
  return useMemo(() => {
    if (task.status !== "running" || !task.started_at || task.progress <= 0) return null;
    const elapsed = (Date.now() - new Date(task.started_at).getTime()) / 1000;
    const totalEstimate = elapsed / (task.progress / 100);
    const remaining = totalEstimate - elapsed;
    if (remaining <= 0) return null;
    if (remaining < 60) return `~${Math.ceil(remaining)}s`;
    if (remaining < 3600) return `~${Math.ceil(remaining / 60)}m`;
    return `~${(remaining / 3600).toFixed(1)}h`;
  }, [task.status, task.started_at, task.progress]);
}

interface TaskCardProps {
  task: Task;
  onSelect: (task: Task) => void;
  onCancel: (id: string) => void;
  onDelete: (id: string) => void;
}

export function TaskCard({ task, onSelect, onCancel, onDelete }: TaskCardProps) {
  const cfg = statusConfig[task.status];
  const Icon = cfg.icon;
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const eta = useETA(task);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    if (menuOpen) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [menuOpen]);

  const isActive = task.status === "running" || task.status === "queued";

  return (
    <div
      onClick={() => onSelect(task)}
      className={`group relative rounded-xl border ${isActive ? "border-gray-700" : "border-gray-800"} ${cfg.bg} p-4 cursor-pointer
        hover:border-gray-600 hover:shadow-lg hover:shadow-black/20 transition-all duration-200
        ${task.status === "running" ? "ring-1 ring-blue-500/20" : ""}`}
    >
      {/* Pulse indicator for running */}
      {task.status === "running" && (
        <span className="absolute top-3 right-3 flex h-2.5 w-2.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-blue-500" />
        </span>
      )}

      {/* Queue position for queued */}
      {task.status === "queued" && (
        <span className="absolute top-3 right-3 text-xs text-amber-500/60 font-mono">
          #{task.priority}
        </span>
      )}

      {/* Status badge + menu */}
      <div className="flex items-center justify-between mb-3">
        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ${cfg.color} ${cfg.bg} ${cfg.ring}`}
        >
          <Icon className="w-3 h-3" />
          {cfg.label}
        </span>

        {isActive && (
          <div className="relative" ref={menuRef}>
            <button
              onClick={(e) => {
                e.stopPropagation();
                setMenuOpen(!menuOpen);
              }}
              className="p-1 rounded-lg hover:bg-gray-800 text-gray-500 hover:text-gray-300 opacity-0 group-hover:opacity-100 transition"
            >
              <MoreVertical className="w-4 h-4" />
            </button>
            {menuOpen && (
              <div className="absolute right-0 top-8 z-10 w-36 rounded-lg bg-gray-900 border border-gray-700 shadow-xl py-1">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onCancel(task.id);
                    setMenuOpen(false);
                  }}
                  className="flex items-center gap-2 w-full px-3 py-2 text-sm text-amber-400 hover:bg-gray-800"
                >
                  <XIcon className="w-3.5 h-3.5" />
                  取消任務
                </button>
              </div>
            )}
          </div>
        )}

        {!isActive && task.status !== "queued" && (
          <div className="relative" ref={menuRef}>
            <button
              onClick={(e) => {
                e.stopPropagation();
                setMenuOpen(!menuOpen);
              }}
              className="p-1 rounded-lg hover:bg-gray-800 text-gray-500 hover:text-gray-300 opacity-0 group-hover:opacity-100 transition"
            >
              <MoreVertical className="w-4 h-4" />
            </button>
            {menuOpen && (
              <div className="absolute right-0 top-8 z-10 w-36 rounded-lg bg-gray-900 border border-gray-700 shadow-xl py-1">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(task.id);
                    setMenuOpen(false);
                  }}
                  className="flex items-center gap-2 w-full px-3 py-2 text-sm text-red-400 hover:bg-gray-800"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  刪除
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Task name */}
      <h3 className="text-sm font-semibold text-gray-100 truncate mb-1">{task.name}</h3>
      <p className="text-xs text-gray-500 mb-3">{task.task_type}</p>

      {/* Enhanced progress bar for running tasks */}
      {task.status === "running" && (
        <div className="mb-3">
          <div className="flex justify-between text-xs text-gray-400 mb-1.5">
            <span>進度</span>
            <div className="flex items-center gap-2">
              {eta && <span className="text-blue-400/70">{eta}</span>}
              <span className="font-mono">{task.progress.toFixed(1)}%</span>
            </div>
          </div>
          <div className="w-full h-2 bg-gray-800 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-700 ease-out bg-gradient-to-r from-blue-600 via-blue-500 to-blue-400"
              style={{ width: `${task.progress}%` }}
            >
              {/* Shimmer effect */}
              <div className="h-full w-full bg-gradient-to-r from-transparent via-white/20 to-transparent animate-[shimmer_2s_infinite]" />
            </div>
          </div>
        </div>
      )}

      {/* Queued indicator */}
      {task.status === "queued" && (
        <div className="mb-3">
          <div className="w-full h-1.5 bg-gray-800 rounded-full overflow-hidden">
            <div className="h-full bg-amber-500/30 rounded-full w-full animate-pulse" />
          </div>
          <p className="text-xs text-amber-500/60 mt-1">等待執行中...</p>
        </div>
      )}

      {/* Timestamps */}
      <div className="flex items-center justify-between text-xs text-gray-500">
        <span>{dayjs(task.created_at).fromNow()}</span>
        {task.status === "success" && task.result && (
          <span
            className={`font-medium font-mono ${
              (task.result.total_return as number) >= 0 ? "text-emerald-400" : "text-red-400"
            }`}
          >
            {(task.result.total_return as number) >= 0 ? "+" : ""}
            {String(task.result.total_return)}%
          </span>
        )}
        {task.status === "failed" && (
          <span className="text-red-400/70 text-xs">失敗</span>
        )}
      </div>
    </div>
  );
}
