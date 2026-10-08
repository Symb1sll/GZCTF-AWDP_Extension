# AWDP 控制与判题组件

平台补丁 API 使用 `AwdpLedger`（PostgreSQL 提交账本），`AwdpWorker` 对接 Runner 结果及计分。`AwdpQueue` 和 `validation/` 保留早期文件队列适配器的测试，不是正式环境计分账本。

Runner 默认读取 `/srv/awdp-dev`。正式准备工具复制它并替换生产目录、容器前缀和清理标签，避免测试/正式任务互相清理。

`deploy/` 应在覆盖层已应用的上游目录下使用。参见 [部署说明](../docs/DEPLOYMENT.md)；不要套用旧独立 API 原型的安装流程。
