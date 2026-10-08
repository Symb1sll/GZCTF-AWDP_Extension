# 独立测试部署

在已应用覆盖层的上游目录构建平台，再运行 `init.py`、`prepare_attack_network.py` 和 Compose。命令见 [DEPLOYMENT.md](../../docs/DEPLOYMENT.md)。

- `init.py`：仅初始化不存在的 `/srv/awdp-dev`，生成随机密码、配置及 Runner unit；不安装 unit。
- `compose.yaml`：测试 Web 仅绑定 localhost 18091；数据库不发布端口。
- `prepare_attack_network.py`：创建或校验攻击 bridge；不重建不符合要求的现有网络。
- `map_challenge.py`：测试绑定，调用前停止测试 Web，写入后再启动。
- `verify.sh`：首页、端口、网络、Runner 和数据库检查，不替代浏览器提交/计分验收。

原记录中 `/healthz` 曾返回 SPA HTML，不能误当作专门健康检查。本版本检查首页，并保留数据库和浏览器验收要求。
