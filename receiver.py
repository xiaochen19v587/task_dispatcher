import os
import threading
import time
import json
from loguru import logger
from queue import Queue, Empty
from enum import Enum
import os
import redis
import subprocess
from redis.exceptions import ConnectionError

current_dir = os.path.dirname(os.path.abspath(__file__))

class RedisManager:
    def __init__(self, host='localhost', port=6379, db=1, password=None):
        self.pool = redis.ConnectionPool(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=True  # 自动解码为字符串
        )
        self.stop_event = threading.Event()
        self.conn = redis.Redis(connection_pool=self.pool)
        hearbeat_thread = threading.Thread(target=self.send_hearbeat)
        hearbeat_thread.start()
    
    def test_connection(self):
        try:
            return self.conn.ping()
        except ConnectionError:
            return False
    
    def pop_task(self):
        """弹出任务"""
        return self.conn.rpop('tasks')

    def send_hearbeat(self):
        while not self.stop_event.is_set():
            self.conn.set('hearbeat', int(time.time()))
            time.sleep(0.5)

    def set_status(self, status:int):
        self.conn.set("status", status)
    
    def stop(self):
        self.stop_event.set()

def local_command(cmd:str, output_file=os.path.join(current_dir, "logs/execute_logs/output.txt")):
    if not os.path.exists(output_file):
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
    # 本地执行shell命令
    output_method = open(output_file, 'w')
    subprocess.call(cmd, shell=True, stdout=output_method, stderr=output_method)
    with open(output_file, "r")as f:
        output_info = f.read()
    return output_info

class ExecutorStatus(Enum):
    IDLE = 0
    WORKING = 1
    ERROR = 2

class TaskExecutor:
    def __init__(self, executor_info, workspace):
        self.status = ExecutorStatus.IDLE
        self.current_task = None
        self.lock = threading.Lock()
        self.info = executor_info
        self.workspace = workspace

    def update_status(self, status, task=None):
        with self.lock:
            self.status = status
            self.current_task = task
            logger.info(f"thor:{self.info.get('host')}, 状态更新: {status.name} | 当前任务: {task}")

class EnhancedTaskQueue:
    def __init__(self, workers, workspace):
        self.task_queue = Queue()
        self.executors = [TaskExecutor(worker, workspace) for worker in workers]
        self.stop_event = threading.Event()
        self.all_busy_event = threading.Event()  # 新增：所有worker忙碌的事件

    def are_all_workers_busy(self):
        """检查是否所有worker都在WORKING状态"""
        busy_count = sum(1 for executor in self.executors 
                        if executor.status == ExecutorStatus.WORKING)
        all_busy = busy_count == len(self.executors)
        
        if all_busy:
            self.all_busy_event.set()
            logger.debug("所有worker都在忙碌状态, 暂停接收新任务")
        else:
            self.all_busy_event.clear()
        
        return all_busy

    def worker(self, executor):
        while not self.stop_event.is_set():
            try:
                task = self.task_queue.get(timeout=1)
                executor.update_status(ExecutorStatus.WORKING, task)
                logger.info(f"thor:{executor.info.get('host')}, workspace: {executor.workspace}, 开始处理: {task}")
                
                logger.debug(task)
                time.sleep(10)
                # cmd = f"cd {executor.workspace}; python3 smoke_test.py '{json.dumps(executor.info)}' '{json.dumps(task)}' "
                # logger.debug(cmd)
                # output_file = os.path.join(current_dir, f"logs/thor_{executor.info.get('host')}_{task.get('commit_id')}.log")
                # local_command(cmd, output_file)

                logger.info(f"thor:{executor.info.get('host')}, workspace: {executor.workspace}, 完成任务: {task}")
                executor.update_status(ExecutorStatus.IDLE)
                self.task_queue.task_done()
                # 每次任务完成后检查worker状态
                self.are_all_workers_busy()
            except Empty:
                # 队列为空时继续等待
                executor.update_status(ExecutorStatus.IDLE)
                self.are_all_workers_busy()  # 检查状态
                continue
            except Exception as e:
                logger.error(f"worker执行异常:{e}")
                executor.update_status(ExecutorStatus.ERROR)
                self.are_all_workers_busy()  # 检查状态

    def start(self):
        for executor in self.executors:
            t = threading.Thread(target=self.worker, args=(executor,), daemon=True)
            t.start()

    def stop(self):
        self.stop_event.set()

def fetch_tasks(task_queue, rdb):
    while not task_queue.stop_event.is_set():
        try:
            # 检查是否所有worker都在忙碌
            if task_queue.are_all_workers_busy():
                logger.info("所有worker都在忙碌, 等待空闲worker...")
                rdb.set_status(0)
                # 等待至少一个worker空闲
                while task_queue.all_busy_event.is_set() and not task_queue.stop_event.is_set():
                    time.sleep(1)
                continue
            rdb.set_status(1)
            task = rdb.pop_task()
            if task:
                task = json.loads(task)
                logger.info(f"获取新任务: {task}")
                task_queue.task_queue.put(task)
            else:
                logger.debug("no task")
                time.sleep(1)
        except json.JSONDecodeError as e:
            logger.error(f"任务JSON解析错误: {e}")
        except Exception as e:
            logger.error(f"获取任务异常: {e}")
            time.sleep(1)

if __name__ == "__main__":
    RECEIVER = os.getenv("RECEIVER")
    workers = []
    workspace = ""
    if RECEIVER == "10.172.129.240":
        workers = [ 
            {"host":"10.172.129.116", "username":"nvidia", "password":"nvidia", "port":2222, "reboot": {"method":1, "power_num": "6"}}, # thor域控信息
            {"host":"10.172.129.117", "username":"nvidia", "password":"nvidia", "port":2222, "reboot": {"method":1, "power_num": "7"}} # thor域控信息
        ]
        workspace = f"/home/security/wmh/smoke_test"
    elif RECEIVER == "10.243.10.16":
        workers = [ 
            {"host":"198.18.42.52", "username":"nvidia", "password":"nvidia", "port":22, "reboot": {"method":2}}, # thor域控信息
        ]
        workspace = f"/home/user/wmh/smoke_test"
    elif RECEIVER == "10.243.10.12":
        workers = [ 
            {"host":"198.18.42.52", "username":"nvidia", "password":"nvidia", "port":22, "reboot": {"method":3}}, # thor域控信息
        ]
        workspace = f"/home/user/wmh/smoke_test"
    elif RECEIVER == "192.168.140.163":
        workers = [ 
            {"host":"198.18.42.51", "username":"nvidia", "password":"nvidia", "port":22, "reboot": {"method":3}}, # thor域控信息
        ]
        workspace = f"/home/user/wmh/smoke_test"
    if workers:
        queue = EnhancedTaskQueue(workers, workspace)
        queue.start()
        rdb = RedisManager(RECEIVER)

        try:
            fetch_tasks(queue, rdb)
        except KeyboardInterrupt:
            queue.stop()
            rdb.stop()
            logger.info("系统终止")
    else:
        logger.error("no workers")