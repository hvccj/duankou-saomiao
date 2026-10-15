# 架构与数据流

本文只描述当前 `端口扫描系统软件.py` 中已经存在的结构，不把未来规划写成现有能力。

## 组件关系

```text
┌──────────────┐
│  MainWindow  │  PyQt5 GUI、输入校验、结果表格
└──────┬───────┘
       │ 创建并启动
       v
┌────────────────────┐
│ PortScannerThread  │  QThread 生命周期与扫描汇总
└──────┬─────────────┘
       │ 创建并填充
       v
┌──────────────┐     领取任务      ┌────────────────┐
│    Queue     │ ────────────────> │ worker threads │
└──────────────┘                   └───────┬────────┘
                                           │ result/progress
                                           v
                                  ┌────────────────┐
                                  │   Qt signals   │
                                  └───────┬────────┘
                                          v
                                  ┌────────────────┐
                                  │  result table  │
                                  └────────────────┘
```

## 扫描流程

1. `MainWindow.start_scan()` 读取端口输入、全端口选项、极速模式和线程数，并以当前本机 IP 创建 `PortScannerThread`。
2. `PortScannerThread.run()` 创建 `Queue`，把待扫描端口逐个放入队列，再启动不超过配置值且不超过端口数量的 Python `threading.Thread` worker。
3. 每个 worker 在 `scan_worker()` 中使用 `get_nowait()` 取端口，通过 TCP `socket.connect_ex()` 探测。普通模式为每个端口发出“开放”或“关闭”结果；极速模式只在连接成功时发出“开放”结果。
4. 每个已处理端口发出一次 `progress` signal；有结果时发出 `result(port, state, elapsed, service)` signal。服务名由本机 `socket.getservbyport()` 查询。
5. `MainWindow` 通过 `on_progress()` 更新进度条，通过 `on_result()` 保存结果并按当前筛选状态插入 `QTableWidget`。`finish` signal 触发 `on_finish()`，恢复控件并显示汇总。

## 为什么 GUI 不被扫描阻塞

按钮点击发生在 Qt GUI 线程，但点击后只创建并启动 `PortScannerThread`。实际 socket 等待发生在 QThread 的 `run()` 及其 worker threads 中，GUI 线程继续运行 Qt 事件循环。worker 不直接访问 Qt 控件，而是发出信号；Qt 槽函数在 `MainWindow` 中更新表格和进度。这种边界避免了在网络等待期间冻结窗口。

这里的 `QThread` 是扫描流程的承载线程；它内部再使用受限数量的 Python worker threads 执行端口任务。`Queue` 负责分发任务，不为每个端口创建线程。

## 停止与异常边界

`stop()` 将共享的 `running` 标志设为 `False`，worker 在下一轮检查后不再继续领取任务。已经进入 `connect_ex()` 的调用仍可能等待配置的 socket timeout；当前源码没有单独的取消 token、强制关闭全部 worker 或暂停/恢复功能。

socket 异常会按普通模式记录为关闭端口；队列为空时 worker 退出，`Queue.join()` 返回后发出 `finish`。文档不将该行为扩展为网络重试、结果持久化或远程扫描。
