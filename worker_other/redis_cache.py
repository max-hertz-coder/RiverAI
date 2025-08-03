# worker/redis_cache.py
from common.redis_utils import (
    init_redis_pool,
    save_raw_tasks,
    get_raw_tasks,
    save_context,
    get_context_by_task_id,
    delete_context_by_task_id,
    cleanup_task_context,
    save_conversation,
    get_conversation,
    clear_conversation
)

# Экспортируем все функции для обратной совместимости
__all__ = [
    'init_redis_pool',
    'save_raw_tasks',
    'get_raw_tasks',
    'save_context',
    'get_context_by_task_id',
    'delete_context_by_task_id',
    'cleanup_task_context',
    'save_conversation',
    'get_conversation',
    'clear_conversation'
]