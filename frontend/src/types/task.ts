export interface Task {
  id: string;
  name: string;
  task_type: string;
  status: "queued" | "running" | "success" | "failed" | "cancelled";
  progress: number;
  config: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  error_message: string | null;
  celery_task_id: string | null;
  priority: number;
  retry_count: number;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface TaskListResponse {
  items: Task[];
  total: number;
  running: number;
  queued: number;
  completed: number;
  failed: number;
}

export interface TaskCreateInput {
  name: string;
  task_type?: string;
  config?: Record<string, unknown>;
  priority?: number;
}

export type WsEvent =
  | { event: "task_created"; task: Task }
  | { event: "task_updated"; task: Task }
  | { event: "task_cancelled"; task: Task };

export interface DailyTaskCount {
  date: string;
  count: number;
}

export interface TaskStats {
  total: number;
  running: number;
  queued: number;
  completed: number;
  failed: number;
  cancelled: number;
  success_rate: number;
  avg_execution_seconds: number | null;
  by_type: Record<string, number>;
  daily_activity: DailyTaskCount[];
}
