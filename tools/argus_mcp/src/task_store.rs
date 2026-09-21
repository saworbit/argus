use rmcp::model::{DetailedTask, Task};
use rmcp::task_manager::{TaskContext, TaskFuture, TaskManager, TaskOptions};
use rmcp::ErrorData as McpError;
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

pub const MATCH_TASK_TTL: Duration = Duration::from_secs(30 * 60);
pub const MATCH_TASK_TERMINAL_GRACE: Duration = Duration::from_secs(10 * 60);

/// Gives active operations an unlimited internal lifetime while advertising a
/// bounded observation lifetime and evicting terminal payloads. rmcp 3.4 still
/// uses one TTL for both hard-aborting active work and retaining terminal work,
/// which is unsafe for a match future that owns engine cleanup.
#[derive(Clone)]
pub struct TaskStore {
    managers: Arc<Mutex<HashMap<String, TaskManager>>>,
    advertised_ttl: Duration,
    terminal_grace: Duration,
}

impl Default for TaskStore {
    fn default() -> Self {
        Self::new(MATCH_TASK_TTL, MATCH_TASK_TERMINAL_GRACE)
    }
}

impl TaskStore {
    pub fn new(advertised_ttl: Duration, terminal_grace: Duration) -> Self {
        Self {
            managers: Arc::new(Mutex::new(HashMap::new())),
            advertised_ttl,
            terminal_grace,
        }
    }

    pub fn spawn<F>(&self, mut options: TaskOptions, make_future: F) -> Task
    where
        F: FnOnce(TaskContext) -> TaskFuture,
    {
        // The SDK TTL aborts active futures. This private manager gets no hard
        // deadline; TaskStore removes it only after its future has returned.
        options.ttl_ms = None;
        let manager = TaskManager::new();
        let created = Instant::now();
        let store = self.clone();
        let (id_sender, id_receiver) = tokio::sync::oneshot::channel();
        let mut task = manager.spawn(options, move |context| {
            let operation = make_future(context);
            Box::pin(async move {
                let task_id = id_receiver
                    .await
                    .expect("task id is published before its operation starts");
                let result = operation.await;
                store.schedule_terminal_eviction(task_id, created);
                result
            })
        });
        let task_id = task.task_id.clone();
        self.managers
            .lock()
            .expect("task store lock poisoned")
            .insert(task_id.clone(), manager);
        id_sender
            .send(task_id)
            .expect("new task operation dropped before startup");
        task.ttl_ms = Some(self.advertised_ttl_ms());
        task
    }

    pub fn get_task(&self, task_id: &str) -> Result<DetailedTask, McpError> {
        let manager = self.manager(task_id)?;
        let mut task = manager.get_task(task_id)?;
        task.task.ttl_ms = Some(self.advertised_ttl_ms());
        Ok(task)
    }

    pub fn update_task(
        &self,
        task_id: &str,
        input_responses: impl IntoIterator<Item = (String, serde_json::Value)>,
    ) -> Result<(), McpError> {
        self.manager(task_id)?.update_task(task_id, input_responses)
    }

    pub fn cancel_task(&self, task_id: &str) -> Result<(), McpError> {
        self.manager(task_id)?.cancel_task(task_id)
    }

    pub fn shutdown(&self) {
        let managers: Vec<_> = self
            .managers
            .lock()
            .expect("task store lock poisoned")
            .drain()
            .map(|(_, manager)| manager)
            .collect();
        for manager in managers {
            manager.shutdown();
        }
    }

    fn manager(&self, task_id: &str) -> Result<TaskManager, McpError> {
        self.managers
            .lock()
            .expect("task store lock poisoned")
            .get(task_id)
            .cloned()
            .ok_or_else(|| McpError::invalid_params(format!("unknown task: {task_id}"), None))
    }

    fn advertised_ttl_ms(&self) -> u64 {
        u64::try_from(self.advertised_ttl.as_millis()).unwrap_or(u64::MAX)
    }

    fn schedule_terminal_eviction(&self, task_id: String, created: Instant) {
        let managers = self.managers.clone();
        let until_advertised_ttl = self.advertised_ttl.saturating_sub(created.elapsed());
        let delay = until_advertised_ttl.max(self.terminal_grace);
        tokio::spawn(async move {
            tokio::time::sleep(delay).await;
            managers
                .lock()
                .expect("task store lock poisoned")
                .remove(&task_id);
        });
    }

    #[cfg(test)]
    fn len(&self) -> usize {
        self.managers
            .lock()
            .expect("task store lock poisoned")
            .len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rmcp::model::{CallToolResult, ContentBlock, TaskPayload};
    use rmcp::task_manager::TaskExit;

    #[tokio::test]
    async fn active_tasks_outlive_the_wire_ttl_then_evict_after_terminal_grace() {
        let store = TaskStore::new(Duration::from_millis(30), Duration::from_millis(15));
        let release = Arc::new(tokio::sync::Notify::new());
        let wait = release.clone();
        let task = store.spawn(TaskOptions::new(), move |_context| {
            Box::pin(async move {
                wait.notified().await;
                Ok(CallToolResult::success(vec![ContentBlock::text("done")]))
            })
        });
        assert_eq!(task.ttl_ms, Some(30));

        tokio::time::sleep(Duration::from_millis(45)).await;
        assert!(!store
            .get_task(&task.task_id)
            .unwrap()
            .status()
            .is_terminal());
        release.notify_one();
        let terminal = loop {
            let state = store.get_task(&task.task_id).unwrap();
            if state.status().is_terminal() {
                break state;
            }
            tokio::task::yield_now().await;
        };
        assert!(matches!(terminal.payload, TaskPayload::Completed { .. }));
        tokio::time::sleep(Duration::from_millis(80)).await;
        assert!(store.get_task(&task.task_id).is_err());
        assert_eq!(store.len(), 0);
    }

    #[tokio::test]
    async fn every_terminal_payload_is_observable_then_bounded() {
        let store = TaskStore::new(Duration::from_millis(30), Duration::from_millis(10));
        let completed = store.spawn(TaskOptions::new(), |_context| {
            Box::pin(async { Ok(CallToolResult::success(vec![ContentBlock::text("ok")])) })
        });
        let failed = store.spawn(TaskOptions::new(), |_context| {
            Box::pin(async { Err(TaskExit::Error(McpError::internal_error("failed", None))) })
        });
        let cancelled = store.spawn(TaskOptions::new(), |context| {
            Box::pin(async move {
                context.cancelled().await;
                Err(TaskExit::Cancelled)
            })
        });
        store.cancel_task(&cancelled.task_id).unwrap();

        for task_id in [&completed.task_id, &failed.task_id, &cancelled.task_id] {
            loop {
                let state = store.get_task(task_id).unwrap();
                if state.status().is_terminal() {
                    break;
                }
                tokio::task::yield_now().await;
            }
        }
        assert_eq!(store.len(), 3);
        tokio::time::sleep(Duration::from_millis(50)).await;
        assert_eq!(store.len(), 0);
        assert!(store.get_task(&completed.task_id).is_err());
        assert!(store.get_task(&failed.task_id).is_err());
        assert!(store.get_task(&cancelled.task_id).is_err());
    }
}
