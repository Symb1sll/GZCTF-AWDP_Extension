# 示例题部署命令速查

前提：已按 [部署说明](DEPLOYMENT.md) 完成平台接入。以下为服务器 Linux Bash 命令，路径和数据库用户须与自身部署相符。

## 首次构建题目与选手包

在 `extension/` 的父目录执行，已构建相同版本无需重复：

```bash
docker build -t awdp/python-base:0.1 extension/images/python-base
docker build -t awdp/ticket-target:1.0 extension/challenges/ticket-attachments/target
docker build -t awdp/ticket-checker:1.0 extension/challenges/ticket-attachments/checker
docker build -t awdp/gzctf-ticket-attack:1.0 -f extension/awdp/deploy/attack.Dockerfile extension/awdp/deploy
python3 extension/challenges/ticket-attachments/tools/build_release.py
```

Runner 白名单使用初始化时的 image ID，重建 target/checker 后需评审并更新白名单、重新验收，不能只沿用旧配置。

## 查询 ID、绑定与检查

后台建好题目，设置动态 Flag、`awdp/gzctf-ticket-attack:1.0`、端口 8080，上传生成的 `ticket-player.tar.gz`。

```bash
# 查询比赛ID、题目ID和名称；按实际环境调整数据库名和用户名。
docker exec gzctf-db-1 psql -U postgres -d gzctf -v ON_ERROR_STOP=1 -c 'SELECT "GameId" AS "比赛ID", "Id" AS "题目ID", "Title" AS "题目名称" FROM "GameChallenges" ORDER BY "GameId", "Id";'

# ID占位换成正整数，仅工单checker、修复100分；会短暂重启正式Web。
python3 /srv/awdp/gzctf-prod/map_challenge.py --game 比赛ID --challenge 题目ID

# 只看映射，不输出数据库密码。
python3 -c 'import json; a=json.load(open("/srv/awdp/gzctf-prod/config/platform.json"))["Awdp"]; print(json.dumps({k:a[k] for k in ("Challenges","Scores")},ensure_ascii=False,indent=2))'

curl -fsS -o /dev/null -w 'HTTP=%{http_code}\n' http://127.0.0.1:8091/
systemctl is-active gzctf-awdp-prod-runner.service
docker ps -a --filter label=gzctf.awdp.prod.managed=true --format 'table {{.Names}}\t{{.Status}}'
```

已绑定题目不重复绑定。`relation "GameChallenges" does not exist` 时先核对实际数据库，不要在错误数据库建表。以上表名和字段对应 GZCTF v1.2.5 基线，查询需要显式连接业务数据库。

## 制作及调整补丁（选手本地 Linux / WSL）

每次从原始附件生成完整补丁，不在服务器部署目录直接修代码：

```bash
# 附件路径替换为实际下载路径。
AWDP_PATCH_WORK=$(mktemp -d "$PWD/ticket-patch-XXXXXXXX")
tar -xzf /实际路径/ticket-player.tar.gz -C "$AWDP_PATCH_WORK"
cp -a "$AWDP_PATCH_WORK/ticket-player" "$AWDP_PATCH_WORK/original"
cp -a "$AWDP_PATCH_WORK/original" "$AWDP_PATCH_WORK/fixed"
nano "$AWDP_PATCH_WORK/fixed/src/app.py"
```

同一终端定义函数，生成新文件并检查应用格式；按普通交互式 Bash 使用，不开启 `set -e`：

```bash
awdp_make_patch() {
    local result output
    output=$(mktemp "$AWDP_PATCH_WORK/fix-XXXXXX.patch") || return
    if diff -u --label a/src/app.py --label b/src/app.py "$AWDP_PATCH_WORK/original/src/app.py" "$AWDP_PATCH_WORK/fixed/src/app.py" > "$output"; then
        echo '没有差异，请勿提交'; return 1
    else
        result=$?
        test "$result" -eq 1 || { echo 'diff失败，请勿提交'; return "$result"; }
    fi
    iconv -f UTF-8 -t UTF-8 "$output" > /dev/null || return
    test "$(wc -c < "$output")" -le 524288 || return
    (cd "$AWDP_PATCH_WORK/original" && patch --dry-run --batch --forward --fuzz=0 -p1 < "$output") || return
    printf '请在题目AWDP面板上传：%s\n' "$output"
}
awdp_make_patch

# 调整时仍改fixed，与original重新比较，不覆盖旧补丁。
nano "$AWDP_PATCH_WORK/fixed/src/app.py"
awdp_make_patch
```

格式正确不代表漏洞修复，最终由功能与安全 checker 判定。更多说明见 [PATCHES.md](PATCHES.md)。
