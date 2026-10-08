# GZCTF AWDP Extension

基于 GZCTF v1.2.5 的静态 AWDP 扩展：复用平台账户、队伍和比赛身份，在同一题目中支持动态 Flag 攻击与修复补丁提交，通过独立 Docker Runner 判题，并将修复分纳入原排行榜。

本仓库发布扩展代码和集成覆盖层，不是完整 GZCTF 源码，不包含服务器配置、数据库、备份或已构建镜像。

## 实现范围

- 前端补丁面板及提交记录；后端补丁 API、身份校验和提交限流。
- PostgreSQL `AwdpSubmissions` 账本与 EF Core 迁移，持久化提交状态和修复分。
- 文件队列连接 Web 与 Runner；结果绑定提交、参赛身份、判题标识及补丁摘要。
- 按参赛记录和题目取最高有效修复分，重复通过不重复加分；保留原攻击计分。
- Runner 将补丁应用到全新题目基线，检查正常功能及漏洞修复，清理带专属标签的临时容器。
- 示例题「失守的工单附件」、三类参考补丁，以及部署和绑定工具。

这是静态补丁判题模式：补丁不替换选手的在线攻击实例；不实现轮次式 AWD、实时在线修复或任意题目自动接入。

## 代码与集成

上游：[GZTimeWalker/GZCTF](https://github.com/GZTimeWalker/GZCTF)，基线提交：

```text
7c42b6ce82f0f1ae5e29ee8750df4281016b459e
```

覆盖层包含 24 个新增或修改文件。`integration/manifest.json` 记录原文件及扩展文件的 SHA-256；安装器检查上游版本和目标内容，拒绝覆盖不匹配的本地修改。许可附录列出的容器管理器和 `useConfig.ts` 未修改、未包含在本仓库，需从上游单独取得。

```text
integration/overlay/       后端、前端、迁移及测试的集成改动
awdp/runner/               判题 Runner 与单元测试
awdp/deploy/               平台构建、独立测试部署及攻击镜像适配
challenges/ticket-attachments/  示例题、checker、选手说明及补丁
images/python-base/        示例题基础镜像 Dockerfile
tools/                    覆盖层安装器、正式接入及绑定工具
docs/                     部署、题目命令、补丁制作与验证边界
```

在 Linux 上准备两个并列目录，先取得上游再安装扩展（`extension` 为本仓库，`upstream` 为上游）：

```bash
git clone https://github.com/Symb1sll/GZCTF-AWDP_Extension.git extension
git -c core.autocrlf=false clone https://github.com/GZTimeWalker/GZCTF.git upstream
git -C upstream config core.autocrlf false
git -C upstream checkout --detach 7c42b6ce82f0f1ae5e29ee8750df4281016b459e
python3 extension/tools/apply_overlay.py --upstream upstream --check
python3 extension/tools/apply_overlay.py --upstream upstream
```

发布前审查本地文件时，可直接将候选目录作为 `extension/` 使用；仓库发布后才可执行上述第一条 clone 命令。

安装器也将 `awdp/` 和 `docs/` 复制到上游工作目录，用于 Docker 构建及保留部署说明；不安装服务、不访问服务器、不修改数据库。目标已有不同内容时拒绝覆盖。可信同版本源码压缩包可显式使用 `--source-archive`，此时只校验涉及文件的摘要，不能验证 Git HEAD；不要对未知版本使用。

## 构建与部署

运行前提：同机原生 Linux、rootful Docker Engine、Compose v2、systemd、Python 3.8+、AppArmor `docker-default` 及可用的 CPU/内存/PID 资源限制；Web、Runner 和 CLI 必须使用同一个 `/var/run/docker.sock`。当前脚本不是 Docker Desktop、远程 Docker、rootless、Swarm 或 Kubernetes 的安装方案。

历史环境记录为 Ubuntu 20.04.3 LTS、Docker 26.0.0、Compose 2.25.0、Buildx 0.13.1；这是测试记录，不是当前版本推荐或最低版本承诺。Docker 构建使用 Node.js 22、pnpm 10.6.2 和 .NET 9；若脱离 Docker 手动构建，还须遵循上游 `src/global.json`（SDK 9.0.201、`rollForward=latestMinor`）。项目镜像由仓库内 Dockerfile 构建，底层使用公开的 Ubuntu、Node.js、.NET 和 PostgreSQL 基础镜像，不是下载现成的 AWDP 功能镜像。

实施顺序：环境与存储核查 → 扩展集成及镜像构建 → 独立测试部署 → 功能回归 → 正式数据备份 → 同机 Web 接入 → 题目绑定 → 最终验收。

历史方案的独立测试实例监听 `127.0.0.1:18091`，使用 PostgreSQL 16；正式接入保留同一虚拟机的 `8091`、原 PostgreSQL 17.4 和附件目录。Web/数据库由 Compose 管理，Runner 由 systemd 管理。正式接入工具针对特定路径和服务名称，不是通用迁移工具。

- [部署说明](docs/DEPLOYMENT.md)：构建、独立测试、正式接入前提及回退边界。
- [题目部署命令速查](docs/COMMANDS.md)：查询 ID、绑定示例题、检查服务。
- [补丁制作与修改](docs/PATCHES.md)：从原始源码生成完整 UTF-8 unified diff。
- [验证及发布整理说明](docs/VERIFICATION.md)：历史部署证据与本次本地检查的区别。

示例题配置：动态 Flag、攻击镜像 `awdp/gzctf-ticket-attack:1.0`、容器端口 `8080`、选手包 `ticket-player.tar.gz`。绑定脚本只绑定到 `ticket-attachments` checker，修复分固定 100；其他题目须编写自己的 target/checker 并调整配置。

## 部署主要问题与避坑

| 问题 | 原因与处理 |
| --- | --- |
| 上游源码不匹配，覆盖层安装失败 | 必须使用上述完整提交 SHA，并关闭 CRLF 自动转换；不要换成最新分支或强行覆盖本地改动。 |
| 正式平台使用 `latest`，但实际版本未知 | 镜像标签不是版本证明。接入工具只接受原 Web v1.2.5 和基线的 7 条数据库迁移记录；较新、较旧、自定义 schema 或已接入 AWDP 的平台需另行评估，不能直接降级。 |
| Docker 能运行，判题仍无法启动 | Runner 固定要求 AppArmor `docker-default`、rootful 本机 socket 和资源限制。先检查宿主机与 Docker context，不要删掉隔离参数来绕过失败。 |
| 构建卡在下载、字体或包依赖 | 除 Docker registry、npm/pnpm、NuGet、apt 外，上游 Vite 还请求 Google Fonts。提前检查构建网络/代理；仓库不提供离线依赖或可复现的镜像 digest 快照。 |
| `/srv/awdp` 有空间，构建却耗尽根分区 | DockerRootDir、构建缓存可能仍在根分区。分别核查 Docker 存储、AWDP 数据、数据库及备份空间；容器配额不是宿主机最低配置。 |
| 初始化/准备失败，重跑提示目录已存在 | 新版先在私有临时目录写完整文件，生产 Compose 校验先于写入；失败临时目录保留供排查。旧版遗留目录要人工核查归档，不要直接删除正式数据，也不要反复初始化已有实例。 |
| 重建镜像后判题使用旧代码 | tag 可以变化，Runner 白名单固定 image ID。重建 target/checker 后必须评审更新白名单并重新验收；正式 Web 要使用真正验收过的 image ID。 |
| 18091 外部打不开或题目实例不可达 | 测试入口和默认攻击端口绑定 localhost，应使用 SSH 隧道；测试攻击网络不等于断网判题网络。正式接入保留原 `PublicEntry`/网络，须自行核查路由、端口和防火墙。 |
| 首页 200、`/healthz` 返回 HTML，就认为验收成功 | 前端 fallback 可能返回页面，首页只证明入口可达；还须核查迁移、Runner、补丁结果与计分。应用容器不保证有 curl，检查应从宿主机执行，并等待启动完成。 |
| 查询报 `GameChallenges` 不存在 | 正式示例显式连接 `gzctf`，不能误连默认 `postgres`；按实际库名/用户核对，不要为修复报错擅自建表。 |
| 随便绑定一道题或比赛中运行绑定 | 绑定脚本只适配工单 checker，且会短暂重启正式 Web；先核对比赛/题目归属，只在空闲维护窗口运行。其他题目须单独实现 checker。 |
| 接入后重建丢失配置，或误以为换旧镜像即可回退 | 正式 Web 重建必须同时使用原 Compose 和 AWDP override。首次启动会新增数据库迁移；回退涉及 schema 与新增数据，切换前须准备一致性备份及恢复方案。 |

具体检查与操作见[部署说明](docs/DEPLOYMENT.md)。新增生产预检为 `prepare_gzctf_production.py --expected-image-id … --check`，不写文件或切换服务；版本标记及迁移表检查不能替代自定义数据库审计和功能验收。不要修改版本标记或迁移表来绕过检查。

## 验证与安全边界

历史测试环境验证过正确/错误补丁、正常业务、重复修复去重、多队伍/新比赛隔离、正常重启持久化。正式接入后的最终题目验收由部署者自行完成并确认；详细边界见[验证说明](docs/VERIFICATION.md)。历史验收不代表重新部署自动通过。

判题 target 无外网，checker 共享 target 网络命名空间；容器使用非 root 用户、只读根文件系统、能力删除及资源限制。测试在线攻击实例使用单独 bridge 网络，并非断网判题容器。Web 挂载 Docker socket，Runner 以 root 运行，均属于可信控制面；Docker 共享宿主机内核，不是虚拟机级隔离。

默认 Runner 最多并行 3 个任务，不提供大规模容量保证。checker 是有限回归测试，不是任意补丁安全性的完整证明。复杂负载、全部异常场景、上游依赖警告处理及备份恢复演练未在记录中全部完成，正式比赛前仍需评估。

## 许可与归属

保留上游 [AGPLv3 许可文本](LICENSE.txt) 和 [GZCTF 许可附录](LICENSE_ADDENDUM.txt)。本仓库扩展代码按 AGPLv3 发布，上游派生文件仍须遵守其原始许可及附录；未重新声明为 MIT 等宽松许可。GZCTF 名称和相关标识保持不变。

上游平台并非本项目原创；本项目的工作是 AWDP 集成、Runner、示例题和部署工具。运行或再分发时请阅读两份许可文件，并保留上游归属及源码提供义务。
