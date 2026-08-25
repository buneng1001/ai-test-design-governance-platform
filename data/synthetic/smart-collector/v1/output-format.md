# 澄明采集器 V1 数据输出说明

每个文件的元数据包含 device_id、task_id、requirement_version、channel、
started_at 和 ended_at。同一任务的各通道使用设备单调时钟，
文件名格式为 task_id/channel/sequence。导出前必须过滤网络凭据和配对密钥。
