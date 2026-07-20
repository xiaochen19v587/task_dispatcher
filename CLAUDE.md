# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

分布式多执行器任务调度系统，通过 Redis 在 dispatcher（调度端）和 receiver（执行端）之间传递任务。两端分别部署在不同机器上，作为 systemd 服务运行。

## Architecture

**dispatcher.py（调度端）**：从任务源获取任务，放入本地 Queue，然后根据负载均衡策略（选择队列最短且状态为空闲的 worker）将任务通过 Redis `lpush` 分发给 receiver。同时通过心跳机制（Redis key `hearbeat`）监控各 receiver 的在线状态。

**receiver.py（执行端）**：从 Redis `rpop` 拉取任务，使用 `EnhancedTaskQueue` 管理多个 `TaskExecutor` 线程并发执行。通过 Redis key `status` 向 dispatcher 报告忙碌/空闲状态（1=空闲可接收，0=全忙）。当所有 worker 线程都在工作时，暂停从 Redis 拉取新任务。

**Redis 通信协议**：
- `tasks` (List)：任务队列，dispatcher lpush / receiver rpop
- `hearbeat` (String)：receiver 每 0.5s 更新时间戳，dispatcher 据此判断连接状态（5s 超时）
- `status` (String)："1"=可接收任务，"0"=忙碌
- 默认使用 db=1

## Running

两个组件作为 systemd 服务部署，service 文件位于项目根目录：

```shell
# 启动服务
sudo systemctl start task_dispatcher.service
sudo systemctl start task_receiver.service

# 查看日志
journalctl -u task_dispatcher.service -f
journalctl -u task_receiver.service -f
```

环境变量 `RECEIVER` 指定 Redis 所在机器的 IP 地址（receiver 端通过此连接本地 Redis，dispatcher 端通过 workers_ip 列表连接各 receiver 的 Redis）。

## Dependencies

Python 3，需要：`redis`、`requests`、`loguru`。
