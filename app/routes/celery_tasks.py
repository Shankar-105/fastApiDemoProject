# programmatic alternative endpoints of flower
from fastapi import APIRouter, HTTPException
from app.celery_app import celery_app
from celery.result import AsyncResult

router = APIRouter(
    prefix="/v1/admin/tasks",
    tags=["Task Management"]
)


@router.get("/{task_id}/status")
async def get_task_status(task_id: str):
    """
    Get status and result of a specific task.
    
    Returns:
        - task_id: UUID of the task
        - status: PENDING, STARTED, RETRY, FAILURE, SUCCESS
        - result: Task result or error message
        - traceback: Error traceback if failed
    """
    task = AsyncResult(task_id, app=celery_app)
    
    if task.state == "PENDING":
        return {
            "task_id": task_id,
            "status": task.state,
            "result": "Task is waiting to be executed",
            "progress": 0,
        }
    elif task.state == "STARTED":
        return {
            "task_id": task_id,
            "status": task.state,
            "result": "Task is currently executing",
            "progress": 50,
        }
    elif task.state == "RETRY":
        return {
            "task_id": task_id,
            "status": task.state,
            "result": f"Task retrying: {task.info.get('exc_message', 'Unknown error')}",
            "progress": 25,
        }
    elif task.state == "FAILURE":
        return {
            "task_id": task_id,
            "status": task.state,
            "result": str(task.info),
            "traceback": task.traceback,
            "progress": 0,
        }
    elif task.state == "SUCCESS":
        return {
            "task_id": task_id,
            "status": task.state,
            "result": task.result,
            "progress": 100,
        }
    else:
        return {
            "task_id": task_id,
            "status": task.state,
            "result": str(task.info),
            "progress": 0,
        }


@router.get("/active")
async def get_active_tasks():
    """
    Get list of all active tasks currently being processed.
    
    Returns:
        List of tasks with their IDs, names, and arguments.
    """
    inspect = celery_app.control.inspect()
    active = inspect.active()
    
    if not active:
        return {"active_tasks": [], "count": 0}
    
    tasks_list = []
    for worker_name, tasks in active.items():
        for task in tasks:
            tasks_list.append({
                "worker": worker_name,
                "task_id": task["id"],
                "task_name": task["name"],
                "args": task.get("args", []),
                "time_start": task.get("time_start"),
            })
    
    return {"active_tasks": tasks_list, "count": len(tasks_list)}


@router.get("/reserved")
async def get_reserved_tasks():
    """
    Get list of reserved tasks (tasks pulled from queue but not yet executed).
    
    Returns:
        List of reserved tasks waiting to execute.
    """
    inspect = celery_app.control.inspect()
    reserved = inspect.reserved()
    
    if not reserved:
        return {"reserved_tasks": [], "count": 0}
    
    tasks_list = []
    for worker_name, tasks in reserved.items():
        for task in tasks:
            tasks_list.append({
                "worker": worker_name,
                "task_id": task["id"],
                "task_name": task["name"],
                "args": task.get("args", []),
            })
    
    return {"reserved_tasks": tasks_list, "count": len(tasks_list)}


@router.get("/stats")
async def get_worker_stats():
    """
    Get statistics about all Celery workers.
    
    Returns:
        Worker stats including pool size, processed tasks, total tasks.
    """
    inspect = celery_app.control.inspect()
    stats = inspect.stats()
    
    if not stats:
        return {"workers": {}, "message": "No workers available"}
    
    worker_info = {}
    for worker_name, worker_stats in stats.items():
        worker_info[worker_name] = {
            "pool_size": worker_stats.get("pool", {}).get("max-concurrency"),
            "processed_tasks": worker_stats.get("total"),
            "broker_transport": worker_stats.get("broker", {}).get("transport"),
        }
    
    return {"workers": worker_info}


@router.post("/{task_id}/revoke")
async def revoke_task(task_id: str, terminate: bool = False):
    """
    Revoke (cancel) a specific task.
    
    Args:
        task_id: UUID of task to revoke
        terminate: If True, terminate the task if it's currently executing
    
    Returns:
        Success message
    """
    celery_app.control.revoke(task_id, terminate=terminate)
    return {
        "message": f"Task {task_id} revoked successfully",
        "terminated": terminate,
    }


@router.get("/queues/{queue_name}/purge")
async def purge_queue(queue_name: str = "celery"):
    """
    Purge all tasks from a specific queue.
    WARNING: This will delete all pending tasks in the queue!
    Args:
        queue_name: Name of queue to purge (default: 'celery')
    Returns:
        Success message
    """
    celery_app.control.purge()
    return {"message": f"Queue '{queue_name}' purged successfully"}
