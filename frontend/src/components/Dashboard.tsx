import { useState, useEffect, useCallback } from "react";
import {
  Activity,
  Plus,
  RefreshCw,
  Wifi,
  WifiOff,
  BarChart3,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Search,
  SlidersHorizontal,
  ArrowUpDown,
  X,
} from "lucide-react";
import type { Task, TaskCreateInput, WsEvent } from "../types/task";
import { fetchTasks, createTask, cancelTask, deleteTask } from "../services/api";
import { useWebSocket } from "../hooks/useWebSocket";
import { TaskCard } from "./TaskCard";
import { TaskDetail } from "./TaskDetail";
import { CreateTask } from "./CreateTask";
import { StatsPanel } from "./StatsPanel";

type TabKey = "running" | "queued" | "history";

const tabs: { key: TabKey; label: string; icon: typeof Activity }[] = [
  { key: "running", label: "運行中", icon: Activity },
  { key: "queued", label: "排隊中", icon: Clock },
  { key: "history", label: "歷史記錄", icon: BarChart3 },
];

type SortField = "created_at" | "name" | "status" | "priority";
type SortOrder = "asc" | "desc";

export function Dashboard() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [stats, setStats] = useState({ total: 0, running: 0, queued: 0, completed: 0, failed: 0 });
  const [activeTab, setActiveTab] = useState<TabKey>("running");
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [loading, setLoading] = useState(true);

  // Search & filter state
  const [search, setSearch] = useState("");
  const [filterType, setFilterType] = useState<string>("");
  const [sortField, setSortField] = useState<SortField>("created_at");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");
  const [showFilters, setShowFilters] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await fetchTasks({
        limit: 200,
        search: search || undefined,
        task_type: filterType || undefined,
        sort_by: sortField,
        sort_order: sortOrder,
      });
      setTasks(data.items);
      setStats({
        total: data.total,
        running: data.running,
        queued: data.queued,
        completed: data.completed,
        failed: data.failed,
      });
    } catch (err) {
      console.error("Failed to load tasks:", err);
    } finally {
      setLoading(false);
    }
  }, [search, filterType, sortField, sortOrder]);

  useEffect(() => {
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, [load]);

  // Debounce search
  const [searchInput, setSearchInput] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => setSearch(searchInput), 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // WebSocket real-time updates
  const handleWsEvent = useCallback(
    (evt: WsEvent) => {
      setTasks((prev) => {
        const idx = prev.findIndex((t) => t.id === evt.task.id);
        if (idx >= 0) {
          const next = [...prev];
          next[idx] = evt.task;
          return next;
        }
        return [evt.task, ...prev];
      });
      if (selectedTask?.id === evt.task.id) {
        setSelectedTask(evt.task);
      }
      load();
    },
    [selectedTask, load],
  );

  const { connected } = useWebSocket(handleWsEvent);

  const handleCreate = async (input: TaskCreateInput) => {
    await createTask(input);
    setShowCreate(false);
    load();
  };

  const handleCancel = async (id: string) => {
    await cancelTask(id);
    load();
  };

  const handleDelete = async (id: string) => {
    await deleteTask(id);
    setTasks((prev) => prev.filter((t) => t.id !== id));
    if (selectedTask?.id === id) setSelectedTask(null);
    load();
  };

  const filtered = tasks.filter((t) => {
    if (activeTab === "running") return t.status === "running";
    if (activeTab === "queued") return t.status === "queued";
    return t.status !== "running" && t.status !== "queued";
  });

  const hasActiveFilters = search || filterType;

  return (
    <div className="min-h-screen">
      {/* Top bar */}
      <header className="sticky top-0 z-30 border-b border-gray-800 bg-gray-950/80 backdrop-blur-lg">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center">
                <BarChart3 className="w-4 h-4 text-white" />
              </div>
              <h1 className="text-lg font-bold text-gray-100">Stock Quant</h1>
              <span className="text-xs text-gray-600">任務面板</span>
            </div>

            <div className="flex items-center gap-3">
              <span className={`flex items-center gap-1.5 text-xs ${connected ? "text-emerald-400" : "text-red-400"}`}>
                {connected ? <Wifi className="w-3.5 h-3.5" /> : <WifiOff className="w-3.5 h-3.5" />}
                {connected ? "已連接" : "斷開"}
              </span>

              <button
                onClick={load}
                className="p-2 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-gray-200 transition"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
              </button>

              <button
                onClick={() => setShowCreate(true)}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-brand-600 text-white text-sm font-medium
                  hover:bg-brand-700 transition"
              >
                <Plus className="w-4 h-4" />
                新建任務
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Stats cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
          <StatCard icon={Activity} label="運行中" value={stats.running} color="text-blue-400" bg="bg-blue-400/10" />
          <StatCard icon={Clock} label="排隊中" value={stats.queued} color="text-amber-400" bg="bg-amber-400/10" />
          <StatCard icon={CheckCircle2} label="已完成" value={stats.completed} color="text-emerald-400" bg="bg-emerald-400/10" />
          <StatCard icon={AlertTriangle} label="失敗" value={stats.failed} color="text-red-400" bg="bg-red-400/10" />
        </div>

        {/* Stats Panel */}
        <StatsPanel />

        {/* Search & Filter bar */}
        <div className="mb-4 space-y-3">
          <div className="flex items-center gap-3">
            {/* Search input */}
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
              <input
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder="搜索任務名稱..."
                className="w-full pl-9 pr-8 py-2 rounded-lg bg-gray-900 border border-gray-800 text-sm text-gray-100
                  placeholder:text-gray-600 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition"
              />
              {searchInput && (
                <button
                  onClick={() => setSearchInput("")}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {/* Filter toggle */}
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-lg border text-sm transition
                ${showFilters || hasActiveFilters
                  ? "bg-brand-600/10 border-brand-500/30 text-brand-400"
                  : "bg-gray-900 border-gray-800 text-gray-400 hover:text-gray-200 hover:border-gray-700"
                }`}
            >
              <SlidersHorizontal className="w-4 h-4" />
              篩選
              {hasActiveFilters && (
                <span className="w-1.5 h-1.5 rounded-full bg-brand-500" />
              )}
            </button>

            {/* Sort */}
            <div className="flex items-center gap-1.5">
              <select
                value={sortField}
                onChange={(e) => setSortField(e.target.value as SortField)}
                className="px-2.5 py-2 rounded-lg bg-gray-900 border border-gray-800 text-sm text-gray-300
                  focus:outline-none focus:ring-2 focus:ring-brand-500 appearance-none cursor-pointer"
              >
                <option value="created_at">創建時間</option>
                <option value="name">名稱</option>
                <option value="priority">優先級</option>
              </select>
              <button
                onClick={() => setSortOrder(sortOrder === "desc" ? "asc" : "desc")}
                className="p-2 rounded-lg bg-gray-900 border border-gray-800 text-gray-400 hover:text-gray-200 transition"
                title={sortOrder === "desc" ? "降序" : "升序"}
              >
                <ArrowUpDown className={`w-4 h-4 ${sortOrder === "asc" ? "rotate-180" : ""} transition-transform`} />
              </button>
            </div>
          </div>

          {/* Expanded filters */}
          {showFilters && (
            <div className="flex items-center gap-3 p-3 rounded-lg bg-gray-900/50 border border-gray-800">
              <span className="text-xs text-gray-500">任務類型：</span>
              <div className="flex items-center gap-1.5">
                {["", "backtest", "optimize", "analyze"].map((t) => (
                  <button
                    key={t}
                    onClick={() => setFilterType(t)}
                    className={`px-2.5 py-1 rounded-md text-xs font-medium transition
                      ${filterType === t
                        ? "bg-brand-600 text-white"
                        : "bg-gray-800 text-gray-400 hover:text-gray-200"
                      }`}
                  >
                    {t === "" ? "全部" : t === "backtest" ? "回測" : t === "optimize" ? "優化" : "分析"}
                  </button>
                ))}
              </div>
              {hasActiveFilters && (
                <button
                  onClick={() => { setSearchInput(""); setFilterType(""); }}
                  className="ml-auto text-xs text-gray-500 hover:text-gray-300 transition"
                >
                  清除篩選
                </button>
              )}
            </div>
          )}
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-1 mb-6 bg-gray-900 rounded-xl p-1 w-fit border border-gray-800">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const count =
              tab.key === "running"
                ? stats.running
                : tab.key === "queued"
                ? stats.queued
                : stats.completed + stats.failed;
            return (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition
                  ${
                    activeTab === tab.key
                      ? "bg-gray-800 text-gray-100 shadow"
                      : "text-gray-500 hover:text-gray-300"
                  }`}
              >
                <Icon className="w-4 h-4" />
                {tab.label}
                <span
                  className={`text-xs px-1.5 py-0.5 rounded-full ${
                    activeTab === tab.key ? "bg-gray-700 text-gray-300" : "bg-gray-800 text-gray-600"
                  }`}
                >
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        {/* Task grid */}
        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-gray-600">
            <BarChart3 className="w-12 h-12 mb-4 opacity-30" />
            <p className="text-sm">
              {hasActiveFilters ? "沒有符合篩選條件的任務" : `暫無${tabs.find((t) => t.key === activeTab)?.label}任務`}
            </p>
            {!hasActiveFilters && (
              <button
                onClick={() => setShowCreate(true)}
                className="mt-3 text-sm text-brand-500 hover:text-brand-400 transition"
              >
                + 創建第一個任務
              </button>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {filtered.map((task) => (
              <TaskCard
                key={task.id}
                task={task}
                onSelect={setSelectedTask}
                onCancel={handleCancel}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </main>

      {/* Modals */}
      {selectedTask && (
        <TaskDetail
          task={selectedTask}
          onClose={() => setSelectedTask(null)}
          onCancel={handleCancel}
        />
      )}
      {showCreate && <CreateTask onClose={() => setShowCreate(false)} onSubmit={handleCreate} />}
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  color,
  bg,
}: {
  icon: typeof Activity;
  label: string;
  value: number;
  color: string;
  bg: string;
}) {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
      <div className="flex items-center gap-3">
        <div className={`p-2 rounded-lg ${bg}`}>
          <Icon className={`w-4 h-4 ${color}`} />
        </div>
        <div>
          <p className="text-xs text-gray-500">{label}</p>
          <p className="text-2xl font-bold text-gray-100 font-mono">{value}</p>
        </div>
      </div>
    </div>
  );
}
