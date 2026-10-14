# 失守的工单附件（管理员示例）

附件下载目录越界读取题，判题标识 `ticket-attachments`。target 提供业务及随机夹具，checker 通过 HTTP 检查正常下载和拒绝越界访问。

- `target/`：漏洞服务及判题入口，应用提交的 `src/app.py` 补丁。
- `checker/`：功能与安全回归，输出 `AWDP_RESULT`。
- `examples/`：正确、无效、关闭下载三类参考补丁。
- `tools/build_release.py`：生成补丁、本地 HTTP 回归、制作选手包。
- `PLAYER.md`：可随选手源码发放的说明，不含参考修复。

攻击镜像在 `awdp/deploy/attack.Dockerfile` 中构建，适配 GZCTF 注入的 `GZCTF_FLAG`，不写死正式 Flag。判题使用独立夹具 Flag，不是攻击得分答案。

本仓库是公开示例题，正式比赛应使用未公开答案的题目、审核 checker 并保护管理员包。部署和题目绑定步骤见 [命令速查](../../docs/COMMANDS.md)。
