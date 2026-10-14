# 构建、测试与正式接入

本指南说明独立测试部署及同机正式接入流程。命令用于 Linux Bash；执行前阅读 README 的许可、权限和隔离边界，并核对目标环境是否符合工具要求。

## 1. 前置环境

按 README 获取精确上游提交并应用覆盖层。后文用两个并列目录：`extension/` 为本仓库，`upstream/` 为已应用扩展的上游。

当前方案要求同机原生 Linux、rootful Docker Engine、Compose v2、systemd、Python 3.8+、curl。CLI、Web 和 Runner 使用同一个 `/var/run/docker.sock`，不能把 CLI 指向远程 Docker，却让队列和 bind mount 留在本机。Runner 固定使用 AppArmor `docker-default` 以及内存/CPU/PID 限制，缺少支持时不要删参数绕过。Docker Desktop、rootless、Swarm、Kubernetes 不在这份脚本的适配范围。

部署参考环境为 Ubuntu 20.04.3 LTS、Docker 26.0.0、Compose 2.25.0、Buildx 0.13.1。这些版本不是最低版本保证或当前软件推荐；换宿主机或工具版本应重新验证。独立测试使用 PostgreSQL 16，正式接入的参考数据库版本为 PostgreSQL 17.4；工具不会自动修改正式数据库镜像。

在服务器执行以下只读检查；`/srv/awdp` 未配置前，其相关命令会报错，应先由运维准备挂载点：

```bash
uname -m
python3 --version
docker version
docker compose version
docker buildx version
docker context show
docker context inspect --format '{{.Endpoints.docker.Host}}'
docker info --format 'Root={{.DockerRootDir}} Security={{json .SecurityOptions}} Cgroup={{.CgroupVersion}}'
systemctl is-active docker.service
test -S /var/run/docker.sock
findmnt /srv/awdp
df -hT / /srv/awdp
free -h
ss -lntp | sed -n '1p;/\(:8091\|:18091\) /p'
```

Docker endpoint 应为 `unix:///var/run/docker.sock`，SecurityOptions 应包含 `name=apparmor`、不含 rootless；再核查 `docker info` 的资源限制警告及 `docker-default` profile 可加载。`DOCKER_HOST` / `DOCKER_CONTEXT` 环境变量也会影响 CLI，须一并核对。工具不自动替你修改 context、防火墙或 AppArmor。

资源规划不能只看 `/srv/awdp`：还应对 `DockerRootDir` 所在文件系统执行 `df -hT`，考虑基础镜像、构建缓存、原数据库、附件及备份峰值。独立测试配额是 Web 2 GiB/2 CPU、数据库 1 GiB/1 CPU；Runner 最多 3 个并行任务，每个 target 默认 512 MiB/1 CPU、checker 128 MiB/0.25 CPU，另有在线攻击实例及宿主机开销。这些是限额，不是经过验证的宿主机最低配置，正式旧服务的配额也不会被自动改成测试值。

正式准备工具要求 `/srv/awdp` 是独立挂载点；磁盘配置是运维前置工作，本仓库不自动分区。目录写入和服务安装需要 root。不要在比赛或判题运行中切换平台，也不要并行运行初始化、准备或绑定脚本。

## 2. 镜像与选手包

在两个目录的父目录执行：

```bash
docker build -t awdp/python-base:0.1 extension/images/python-base
docker build -t awdp/ticket-target:1.0 extension/challenges/ticket-attachments/target
docker build -t awdp/ticket-checker:1.0 extension/challenges/ticket-attachments/checker
docker build -t awdp/gzctf-ticket-attack:1.0 -f extension/awdp/deploy/attack.Dockerfile extension/awdp/deploy
docker build -t gzctf-awdp-dev:1.2.5-local -f upstream/awdp/deploy/Dockerfile upstream
python3 extension/challenges/ticket-attachments/tools/build_release.py
```

构建需要网络：Docker registry（含 Microsoft .NET 镜像）、npm/pnpm、NuGet、apt 镜像源，以及上游 Vite 字体插件请求的 Google Fonts CSS/字体资源。仅能拉镜像不代表前后端构建网络畅通；遇到字体/依赖下载错误，先检查日志、DNS、代理和对应网络，不要假定是 AWDP 代码问题。

基础 Dockerfile 使用 Ubuntu 20.04 和软件镜像源，安装 Python 与 `patch`，不是不可变供应链快照。平台 Dockerfile 的 Node 22、.NET 9 标签也没有固定 digest。本仓库不含镜像 tar 或离线依赖，重建 image ID 可能变化；初始化读取本机实际 image ID，不应复用其他构建的白名单。在 ARM 等非参考架构部署时，须验证全部镜像和运行依赖，不能仅凭 tag 推断兼容性。

生成选手包仅包含 `src/app.py` 和说明，不要将 checker、参考答案或管理员配置作为附件。

## 3. 独立测试

仅首次初始化执行，已有 `/srv/awdp-dev` 时拒绝覆盖：

```bash
cd upstream/awdp/deploy
sudo python3 init.py
sudo python3 prepare_attack_network.py
sudo install -o root -g root -m 0644 /srv/awdp-dev/awdp-dev-runner.service /etc/systemd/system/awdp-dev-runner.service
sudo systemctl daemon-reload
sudo systemctl enable --now awdp-dev-runner.service
sudo docker compose --env-file /srv/awdp-dev/compose.env -f compose.yaml up -d --no-build
sudo bash verify.sh
```

初始密码在 `/srv/awdp-dev/admin-password.txt`，只在服务器本地查看，不提交 Git。测试 Web 监听 `127.0.0.1:18091`，可通过自己的 SSH 隧道访问；数据库为 `gzctf_awdp_dev` / PostgreSQL 16。`verify.sh` 会有限次数等待首页可达；失败时查看 `docker compose … logs web db`，不要因为容器显示 running 就继续。

初始化先在 `/srv/.awdp-dev.prepare-*` 私有目录准备全部文件，成功后才发布 `/srv/awdp-dev`。正常写入失败时最终目录不被占用，可排障后重试；失败临时目录可能含随机密码，应保持私有并由维护者核查处理。已有实例拒绝覆盖是保护机制，不是让你删除数据的提示。

Web 加入普通 `web-entry` 提供入口，数据库使用内部 `control`。Compose `challenges` 内部网络与在线攻击网络不同：动态 Flag 实例配置 `gzctf-awdp-dev-attack`（bridge，Internal=false，ICC 关闭，默认发布绑定 localhost）。这些设置不等同完整防火墙策略。

后台创建比赛和动态 Flag 题目，设置攻击镜像 `awdp/gzctf-ticket-attack:1.0`、端口 8080、选手包，确认 ID 后绑定：

```bash
sudo docker compose --env-file /srv/awdp-dev/compose.env -f compose.yaml stop web
sudo python3 map_challenge.py --game 比赛ID --challenge 题目ID
sudo docker compose --env-file /srv/awdp-dev/compose.env -f compose.yaml start web
```

占位 ID 换成正整数；这是工单 checker，修复 100 分，不是任意题目通用绑定。随后在浏览器验证 Flag、正确/错误/关闭业务补丁、重复通过去重、队伍/比赛隔离、正常重启状态。脚本通过不能替代浏览器验收。

## 4. 正式前提与备份

正式接入工具按以下部署约定检查既有平台：

| 项目 | 部署约定 |
| --- | --- |
| Compose 项目 / Web 服务 | `gzctf` / `gzctf` |
| 既有 Compose / 配置 | `/root/GZCTF/docker-compose.yml` / `/root/GZCTF/appsettings.json` |
| 既有容器 | `gzctf-gzctf-1`、`gzctf-db-1` |
| 端口 | 8091，沿用原绑定 |
| 正式 AWDP 数据 | `/srv/awdp/gzctf-prod` |
| 数据库 / 附件 | 保留原 PostgreSQL、`/root/GZCTF/data/files` |

路径、服务名、运行用户或配置结构不同，必须先调整工具。准备工具保留原配置值，只增加 `Awdp`，不更换数据库，不修改原 `ContainerProvider`。正式攻击实例网络策略须单独核查，不能据测试网络推断生产隔离。

本工具仅用于**原 Web 仍为 v1.2.5、尚未接入 AWDP** 的同机部署。它从原运行容器读取 `/app/files/version.txt`，核对原配置只读挂载及环境变量没有覆盖数据库/容器配置，并只读查询原连接字符串指定数据库的 `__EFMigrationsHistory`；要求 7 条记录与 `integration/manifest.json` 的 `upstream_migrations` 完全一致。原库须在 `gzctf-db-1` 中，与 Web 共享网络，连接 Host 指向该容器网络别名、Port=5432；自动预检只支持字母/下划线开头的简单数据库名。非 root Web、远程数据库、特殊连接字符串、已有正式目录/unit、较新/较旧迁移历史均不应强行绕过。

`latest` 只是镜像标签，不能说明实际版本。版本文件是上游启动写入的标记，不是二进制签名；迁移历史一致也不证明自定义 schema 无差异。版本未知或库做过自定义修改时，先另行审计，不修改版本文件或迁移表来通过预检。

先在两个源码目录的父目录运行只读预检，必须保留完整 `extension/`（工具依赖其中的 manifest 和暂存模块，不能只上传单个 prepare 脚本）：

```bash
AWDP_TESTED_IMAGE=$(docker image inspect --format '{{.Id}}' gzctf-awdp-dev:1.2.5-local)
python3 extension/tools/prepare_gzctf_production.py --expected-image-id "$AWDP_TESTED_IMAGE" --check
```

变量须是刚刚验收、尚未重建替换的镜像；读取 ID 不证明已经测试。`--check` 不写运行目录、不安装/重启服务、不修改数据库；通过后仍须完成下面的备份。

切换前完成可恢复备份：数据库逻辑导出、原 Compose/配置/附件、容器/镜像元数据，必要时保存原镜像及一致性数据快照。拷贝 PostgreSQL 数据目录须满足一致性要求；不能运行中直接打包当作有效备份。备份名包含 UTC 时间，校验后保存服务器之外的副本。

校验摘要只能检查备份文件完整性，不能替代恢复验证。切换前应在隔离环境验证恢复流程，并准备原镜像、配置及数据恢复点。备份和回退准备未完成时，不执行下一节。

## 5. 接入原 8091

先准备文件，后续安装与 `up` 才会切换正式 Web，数据库不换镜像。在空闲维护窗口，由 root 在两个源码目录的父目录执行：

```bash
AWDP_TESTED_IMAGE=$(docker image inspect --format '{{.Id}}' gzctf-awdp-dev:1.2.5-local)
python3 extension/tools/prepare_gzctf_production.py --expected-image-id "$AWDP_TESTED_IMAGE"
```

工具再次检查宿主机、原版本、数据库历史和已验收镜像，拒绝已有正式路径或 unit，复制测试 Runner 和判题 image ID 白名单。Compose 合并先通过 stdin 校验，尚未通过时不会创建正式运行目录；随后在 `/srv/awdp/.gzctf-prod.prepare-*` 私有目录写完整配置、override 和 unit，全部成功才发布到 `/srv/awdp/gzctf-prod`。**只准备文件，不切换服务**。

正常写入失败时保留私有临时目录供排查，最终路径不被占用；重试不会自动清理失败目录。临时目录可能含生产凭据，切勿上传。已存在的运行目录或服务必须先确认状态、备份或归档，再决定如何处理；工具不自动覆盖。此机制不提供断电后的完整事务保证，不允许并发准备。

核对输出后安装服务并切换 Web：

```bash
install -o root -g root -m 0644 /srv/awdp/gzctf-prod/gzctf-awdp-prod-runner.service /etc/systemd/system/gzctf-awdp-prod-runner.service
systemctl daemon-reload
systemctl enable --now gzctf-awdp-prod-runner.service
docker compose -p gzctf -f /root/GZCTF/docker-compose.yml -f /srv/awdp/gzctf-prod/compose.awdp.json up -d --no-deps --no-build gzctf
test ! -e /srv/awdp/gzctf-prod/map_challenge.py && install -o root -g root -m 0700 extension/tools/map_challenge.py /srv/awdp/gzctf-prod/map_challenge.py
```

以后重建正式 Web 仍须使用两个 Compose 文件；只用旧文件可能恢复旧镜像/挂载。原数据库和附件沿用旧 Compose，override 新增配置/队列；结果、运行任务及归档对 Web 为只读、Runner 可写。

平台启动涉及数据库迁移，保留数据库容器不代表 schema 不变。启动后检查入口、Runner、容器状态和最新迁移：

```bash
# 有限重试等待入口，失败则停止后续验收，查看Web日志。
curl -fsS --retry 30 --retry-connrefused --retry-delay 2 --retry-max-time 180 --connect-timeout 3 --max-time 5 -o /dev/null -w 'HTTP=%{http_code}\n' http://127.0.0.1:8091/
systemctl is-active gzctf-awdp-prod-runner.service
docker inspect --format 'Status={{.State.Status}} RestartCount={{.RestartCount}}' gzctf-gzctf-1
docker exec gzctf-db-1 psql -U postgres -d gzctf -v ON_ERROR_STOP=1 -c 'SELECT "MigrationId" FROM "__EFMigrationsHistory" ORDER BY "MigrationId" DESC LIMIT 1;'
```

数据库名和用户按自身实例核对；应出现新增迁移 `20260920053850_AddAwdpSubmissionLedger`，否则不要继续绑定。curl 在宿主机执行，不能假定容器有 curl；首页 200 或 `/healthz` 的 HTML fallback 不证明后端业务健康。未配置 healthcheck 的 Web 不能单凭 `not-configured` 判定异常或健康。

## 6. 绑定及验收

按 [COMMANDS.md](COMMANDS.md) 查询 ID、配置正式题目并绑定。脚本备份配置、拒绝覆盖映射、短暂停止/启动 Web，仅空闲时运行；不创建比赛/题目，不查询数据库验证 ID 归属。

验收：原登录与页面 → 动态 Flag → 正确补丁计分 → 错误补丁失败 → 重复通过不额外加分 → 排行榜一致 → 临时容器清理。异常时保留日志及备份，不批量删除任务。

## 7. 回退边界

预先保存原镜像 digest、原配置和一致性备份。回退同时考虑 Web、数据库迁移及新增提交，不能保证只切旧镜像就兼容新 schema。数据库恢复覆盖数据，应由维护者选择恢复点并接受之后数据丢失。本仓库不提供自动覆盖数据库或删除目录的回滚命令。
