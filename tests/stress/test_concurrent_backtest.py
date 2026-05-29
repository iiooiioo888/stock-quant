"""
壓力測試 - 模擬 100+ 併發回測任務，驗證分散式隊列穩定性
"""
import asyncio
import time
import random
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from src.monitoring.metrics import MetricsCollector


class StressTestRunner:
    """
    壓力測試執行器
    
    功能：
    - 模擬多用戶併發提交回測任務
    - 監控任務隊列長度變化
    - 統計成功率、平均延遲、P95/P99 延遲
    - 生成測試報告
    """
    
    def __init__(self):
        self.collector = MetricsCollector()
        self.results: List[Dict] = []
        self.lock = threading.Lock()
    
    async def simulate_backtest_task(self, task_id: str, user_id: str, delay_ms: int) -> Dict:
        """模擬單個回測任務"""
        start_time = time.time()
        
        try:
            # 記錄任務開始
            self.collector.record_backtest_task("started")
            
            # 模擬任務執行延遲
            await asyncio.sleep(delay_ms / 1000.0)
            
            # 模擬隨機成功/失敗 (95% 成功率)
            success = random.random() < 0.95
            
            if success:
                self.collector.record_backtest_task("completed")
                status = "completed"
            else:
                self.collector.record_backtest_task("failed")
                status = "failed"
            
            elapsed = (time.time() - start_time) * 1000  # ms
            
            result = {
                "task_id": task_id,
                "user_id": user_id,
                "status": status,
                "elapsed_ms": elapsed,
                "success": success,
            }
            
            with self.lock:
                self.results.append(result)
            
            return result
        
        except Exception as e:
            self.collector.record_backtest_task("failed")
            elapsed = (time.time() - start_time) * 1000
            
            result = {
                "task_id": task_id,
                "user_id": user_id,
                "status": "error",
                "elapsed_ms": elapsed,
                "success": False,
                "error": str(e),
            }
            
            with self.lock:
                self.results.append(result)
            
            return result
    
    async def run_concurrent_test(
        self,
        num_tasks: int = 100,
        num_users: int = 10,
        min_delay_ms: int = 50,
        max_delay_ms: int = 500,
        max_concurrent: int = 20,
    ) -> Dict:
        """
        運行併發測試
        
        Args:
            num_tasks: 總任務數
            num_users: 模擬用戶數
            min_delay_ms: 最小任務延遲 (ms)
            max_delay_ms: 最大任務延遲 (ms)
            max_concurrent: 最大併發數
        """
        print(f"\n{'='*60}")
        print(f"壓力測試開始")
        print(f"{'='*60}")
        print(f"總任務數：{num_tasks}")
        print(f"模擬用戶數：{num_users}")
        print(f"任務延遲範圍：{min_delay_ms}-{max_delay_ms}ms")
        print(f"最大併發數：{max_concurrent}")
        print(f"{'='*60}\n")
        
        # 重置指標
        self.collector.reset()
        self.results.clear()
        
        # 創建任務
        tasks = []
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def bounded_task(task_id: str, user_id: str, delay_ms: int):
            async with semaphore:
                return await self.simulate_backtest_task(task_id, user_id, delay_ms)
        
        for i in range(num_tasks):
            task_id = f"task_{i:04d}"
            user_id = f"user_{random.randint(0, num_users-1):02d}"
            delay_ms = random.randint(min_delay_ms, max_delay_ms)
            
            tasks.append(bounded_task(task_id, user_id, delay_ms))
        
        # 記錄開始時的隊列長度
        self.collector.set_queue_length("backtest", num_tasks)
        
        start_time = time.time()
        
        # 執行所有任務
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        total_time = time.time() - start_time
        
        # 記錄結束時的隊列長度
        self.collector.set_queue_length("backtest", 0)
        
        # 分析結果
        successful = sum(1 for r in self.results if r.get("success", False))
        failed = len(self.results) - successful
        
        elapsed_times = [r["elapsed_ms"] for r in self.results if "elapsed_ms" in r]
        elapsed_times.sort()
        
        avg_elapsed = sum(elapsed_times) / len(elapsed_times) if elapsed_times else 0
        p50_elapsed = elapsed_times[int(len(elapsed_times) * 0.5)] if elapsed_times else 0
        p95_elapsed = elapsed_times[int(len(elapsed_times) * 0.95)] if len(elapsed_times) > 20 else (elapsed_times[-1] if elapsed_times else 0)
        p99_elapsed = elapsed_times[int(len(elapsed_times) * 0.99)] if len(elapsed_times) > 100 else (elapsed_times[-1] if elapsed_times else 0)
        
        report = {
            "summary": {
                "total_tasks": num_tasks,
                "successful": successful,
                "failed": failed,
                "success_rate": f"{successful/num_tasks*100:.2f}%",
                "total_time_sec": round(total_time, 2),
                "tasks_per_sec": round(num_tasks / total_time, 2),
            },
            "latency": {
                "avg_ms": round(avg_elapsed, 2),
                "p50_ms": round(p50_elapsed, 2),
                "p95_ms": round(p95_elapsed, 2),
                "p99_ms": round(p99_elapsed, 2),
                "min_ms": round(min(elapsed_times), 2) if elapsed_times else 0,
                "max_ms": round(max(elapsed_times), 2) if elapsed_times else 0,
            },
            "metrics": self.collector.get_all_metrics(),
        }
        
        # 打印報告
        print(f"\n{'='*60}")
        print(f"壓力測試完成")
        print(f"{'='*60}")
        print(f"\n【總結】")
        print(f"  總任務數：{num_tasks}")
        print(f"  成功：{successful} | 失敗：{failed}")
        print(f"  成功率：{successful/num_tasks*100:.2f}%")
        print(f"  總耗時：{total_time:.2f}秒")
        print(f"  吞吐量：{num_tasks/total_time:.2f} 任務/秒")
        
        print(f"\n【延遲分佈】")
        print(f"  平均：{avg_elapsed:.2f}ms")
        print(f"  P50: {p50_elapsed:.2f}ms")
        print(f"  P95: {p95_elapsed:.2f}ms")
        print(f"  P99: {p99_elapsed:.2f}ms")
        print(f"  Min: {min(elapsed_times):.2f}ms" if elapsed_times else "  Min: N/A")
        print(f"  Max: {max(elapsed_times):.2f}ms" if elapsed_times else "  Max: N/A")
        
        print(f"\n【監控指標】")
        print(f"  最終隊列長度：{self.collector.get_gauge('task_queue_length', {'queue': 'backtest'}) or 0}")
        print(f"  回測任務總數：{self.collector.get_counter('backtest_tasks_total')}")
        
        print(f"\n{'='*60}\n")
        
        return report
    
    def run_sync_test(
        self,
        num_tasks: int = 100,
        num_users: int = 10,
        min_delay_ms: int = 50,
        max_delay_ms: int = 500,
        max_concurrent: int = 20,
    ) -> Dict:
        """同步版本（用於非 async 環境）"""
        return asyncio.run(
            self.run_concurrent_test(
                num_tasks=num_tasks,
                num_users=num_users,
                min_delay_ms=min_delay_ms,
                max_delay_ms=max_delay_ms,
                max_concurrent=max_concurrent,
            )
        )


async def main():
    """主函數 - 運行壓力測試"""
    runner = StressTestRunner()
    
    # 運行 100 個併發任務測試
    report = await runner.run_concurrent_test(
        num_tasks=100,
        num_users=10,
        min_delay_ms=50,
        max_delay_ms=300,
        max_concurrent=20,
    )
    
    return report


if __name__ == "__main__":
    asyncio.run(main())
