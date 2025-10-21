# task_dispatcher
**多执行器任务调度工具**

1. ##### 在linux系统中创建dispatcher和receiver服务

   ```shell
   # /etc/systemd/system/task_dispatcher.service (调度器: 负责下发任务)
   [Unit] 
           Description=Task Dispatcher Service 
           After=network.target 
   [Service] 
           User=user 
           Group=user 
           ExecStart=/usr/bin/python3 /home/user/task_dispatcher/dispatcher.py
           Restart=on-failure 
           RestartSec=5s 
           Environment=PATH=/home/user/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin 
           StandardOutput=append:/var/log/task_dispatcher.log 
           StandardError=inherit
           Environment=RECEIVER="192.168.140.163"
   [Install] 
           WantedBy=multi-user.target
   ```

   ```shell
   # /etc/systemd/system/task_receiver.service (接收器: 负责接收调度器下发的任务)
   [Unit] 
           Description=Task Receiver Service 
           After=network.target 
   [Service] 
           User=user 
           Group=user 
           ExecStart=/usr/bin/python3 /home/user/task_dispatcher/receiver.py
           Restart=on-failure 
           RestartSec=5s 
           Environment=PATH=/home/user/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
           StandardOutput=append:/var/log/task_receiver.log 
           StandardError=inherit
           Environment=RECEIVER="192.168.140.163"
   [Install] 
           WantedBy=multi-user.target
   ```

2. ##### megsim_task_queue服务操作命令

   ```shell
   # 重载systemd配置 
        sudo systemctl daemon-reload
   # 启动服务 (指定具体service名称)
        sudo systemctl start task_***.service 
   # 设置开机自启 
        sudo systemctl enable task_***.service 
   # 查看状态 
        sudo systemctl status task_***.service 
   # 查看日志 
        journalctl -u task_***.service -f
   ```

   
