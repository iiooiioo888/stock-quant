import axios from "axios";
import type { TaskCreateInput, TaskListResponse, Task, TaskStats } from "../types/task";

const api = axios.create({ baseURL: "/api" });

export async function fetchTasks(params?: {
  status?: string;
  task_type?: string;
  search?: string;
  sort_by?: string;
  sort_order?: string;
  limit?: number;
  offset?: number;
}): Promise<TaskListResponse> {
  const { data } = await api.get("/tasks", { params });
  return data;
}

export async function fetchTask(id: string): Promise<Task> {
  const { data } = await api.get(`/tasks/${id}`);
  return data;
}

export async function fetchStats(): Promise<TaskStats> {
  const { data } = await api.get("/tasks/stats");
  return data;
}

export async function createTask(input: TaskCreateInput): Promise<Task> {
  const { data } = await api.post("/tasks", input);
  return data;
}

export async function cancelTask(id: string): Promise<Task> {
  const { data } = await api.post(`/tasks/${id}/cancel`);
  return data;
}

export async function deleteTask(id: string): Promise<void> {
  await api.delete(`/tasks/${id}`);
}
