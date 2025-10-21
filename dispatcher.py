
import time
import json
import redis
import requests
import threading
from loguru import logger
from queue import Queue
from redis.exceptions import ConnectionError

class RedisManager:
    def __init__(self, host='localhost', port=6379, db=1, password=None):
        self.pool = redis.ConnectionPool(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=True  # 自动解码为字符串
        )
        self.name = host
        self.stop_event = threading.Event()
        self.connect_result = False
        self.conn = redis.Redis(connection_pool=self.pool)
        check_hearbeat_thread = threading.Thread(target=self.check_hearbeat)
        check_hearbeat_thread.start()
    
    def test_connection(self):
        try:
            return self.conn.ping()
        except ConnectionError:
            return False
    
    def create_task(self, task):
        """创建任务"""
        self.conn.lpush('tasks', task)
    
    def get_task_list(self):
        '''获取任务列表长度'''
        return self.conn.llen("tasks")
    
    def get_status(self):
        '''获取任务执行器状态'''
        return self.conn.get("status")
    
    def check_hearbeat(self):
        while not self.stop_event.is_set():
            heatbeat_timestamp = self.conn.get("hearbeat")
            if heatbeat_timestamp:
                current_timestamp = time.time()
                diff_timestamp = int(current_timestamp)-int(heatbeat_timestamp)
                if diff_timestamp < 5:
                    self.connect_result = True
                else:
                    self.connect_result = False
            else: 
                self.connect_result = False
            time.sleep(1)

    def stop(self):
        self.stop_event.set()

def receive_task(task_queue):
    count = 0
    while count<30:
        task = json.dumps({"task_id":count})
        task_queue.put(task)
        time.sleep(2)
        count += 1
    # while True:
    #     request_url = "https://megsim.mc.machdrive.cn/api/reinjection/task"
    #     params = {"project": 4,"type": 40}
    #     res = requests.post(request_url, json=params)
    #     logger.debug(res)
    #     if res.status_code == 200:
    #         result = json.loads(res.content.decode())
    #         if result:
    #             task_id = result.get("task_id")
    #             snapshot = result.get("snapshot")
    #             branch = snapshot.get("branch")
    #             commit = snapshot.get("commit")
    #             thor_s3_path = snapshot.get("thor_s3_path")
    #             ci_type = snapshot.get("ci_type")
    #             logger.debug(f"task info:")
    #             logger.debug(f"    id: {task_id}, branch: {branch}, commit: {commit}, ci_type: {ci_type}")
    #             logger.debug(f"    thor s3 path: {thor_s3_path}")
    #             task = json.dumps({"task_id":task_id, "branch": branch, "commit_id": commit, "test_type":ci_type, "package_path": thor_s3_path})
    #             task_queue.put(task)
    #         else:
    #             logger.warning(f"Megsim暂无测试任务")
    #     elif res.status_code == 404:
    #         logger.info(f"No task for the time being.")
    #     else:
    #         logger.error(f"Request {request_url} exception! status code:{res.status_code},detail:{result}")
    #     time.sleep(2)

if __name__ == '__main__':
    task_queue = Queue()
    # workers_ip = ["10.172.129.240", "10.243.10.16", "10.243.10.12"]
    workers_ip = ["192.168.140.163"]
    workers = [RedisManager(ip) for ip in workers_ip]
    
    receive_task_thread = threading.Thread(target=receive_task, args=(task_queue,))
    receive_task_thread.start()
    try:
        while True:
            time.sleep(2)
            logger.debug(f'task queue size: {task_queue.qsize()}')
            workers_info = [{worker: {"name": worker.name, "task_lenght": worker.get_task_list(), "connect_result": worker.connect_result, "status": worker.get_status()}} for worker in workers]
            normal_workers = [worker.name for worker in workers if worker.connect_result]
            abnormal_workers = [worker.name for worker in workers if not worker.connect_result]
            logger.debug(f"normal workers: {normal_workers}, abnormal workers: {abnormal_workers}")
            if task_queue.empty():
                continue
            if not normal_workers:
                logger.error("All workers are abnormal")

            try:
                selected_worker = min(
                    (worker for worker in workers_info if list(worker.values())[0]['connect_result'] and list(worker.values())[0]['status'] == "1"),
                    key=lambda x: list(x.values())[0]['task_lenght']
                )
            except ValueError:
                selected_worker = None  # 如果没有符合条件的元素
            
            if selected_worker:
                if list(selected_worker.values())[0]['status'] == "1":
                    worker = list(selected_worker.keys())[0]
                    task = task_queue.get()
                    worker.create_task(task)
                    logger.debug((selected_worker, task))
    except KeyboardInterrupt:
        for worker in workers:
            worker.stop()