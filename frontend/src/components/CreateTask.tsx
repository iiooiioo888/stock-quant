import { useState } from "react";
import { X, Plus } from "lucide-react";
import type { TaskCreateInput } from "../types/task";

interface CreateTaskProps {
  onClose: () => void;
  onSubmit: (input: TaskCreateInput) => void;
}

export function CreateTask({ onClose, onSubmit }: CreateTaskProps) {
  const [name, setName] = useState("");
  const [taskType, setTaskType] = useState("backtest");
  const [strategy, setStrategy] = useState("ma_cross");
  const [symbol, setSymbol] = useState("000001.SZ");
  const [startDate, setStartDate] = useState("2024-01-01");
  const [endDate, setEndDate] = useState("2024-12-31");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    onSubmit({
      name: name.trim(),
      task_type: taskType,
      config: { strategy, symbol, start_date: startDate, end_date: endDate },
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="relative w-full max-w-lg rounded-2xl bg-gray-900 border border-gray-700 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-6 pb-4 border-b border-gray-800">
          <h2 className="text-lg font-bold text-gray-100">新建任務</h2>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-gray-200 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Name */}
          <div>
            <label className="block text-sm text-gray-400 mb-1">任務名稱</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例：雙均線策略回測"
              className="w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2.5 text-sm text-gray-100
                placeholder:text-gray-600 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
              required
            />
          </div>

          {/* Task type */}
          <div>
            <label className="block text-sm text-gray-400 mb-1">任務類型</label>
            <select
              value={taskType}
              onChange={(e) => setTaskType(e.target.value)}
              className="w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2.5 text-sm text-gray-100
                focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              <option value="backtest">回測</option>
              <option value="optimize">參數優化</option>
              <option value="analyze">數據分析</option>
            </select>
          </div>

          {/* Strategy */}
          <div>
            <label className="block text-sm text-gray-400 mb-1">策略</label>
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              className="w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2.5 text-sm text-gray-100
                focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              <option value="ma_cross">雙均線交叉</option>
              <option value="macd">MACD</option>
              <option value="rsi">RSI 超買超賣</option>
              <option value="bollinger">布林帶</option>
              <option value="custom">自定義</option>
            </select>
          </div>

          {/* Symbol + Date range */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm text-gray-400 mb-1">標的代碼</label>
              <input
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className="w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2.5 text-sm text-gray-100
                  focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">初始資金</label>
              <input
                defaultValue="1000000"
                className="w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2.5 text-sm text-gray-100
                  focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm text-gray-400 mb-1">開始日期</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2.5 text-sm text-gray-100
                  focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">結束日期</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2.5 text-sm text-gray-100
                  focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
          </div>

          {/* Submit */}
          <button
            type="submit"
            className="w-full flex items-center justify-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5
              text-sm font-medium text-white hover:bg-brand-700 transition"
          >
            <Plus className="w-4 h-4" />
            提交任務
          </button>
        </form>
      </div>
    </div>
  );
}
