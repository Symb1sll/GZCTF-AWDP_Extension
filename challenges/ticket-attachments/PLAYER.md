# 失守的工单附件

一家公司的工单系统最近上线了附件下载功能。管理员怀疑下载接口能够读取附件目录之外的文件。请取得攻击实例中的Flag，并提交修复补丁，确保工单附件业务继续正常运行。

## 攻击阶段

攻击入口由GZCTF题目面板提供，不使用固定共享实例地址。实际攻击分以比赛配置为准。

- `GET /health`：健康检查。
- `GET /api/attachments`：附件路径列表。
- `GET /download?name=welcome.txt`：下载指定附件。
- 附件根目录为 `/work/runtime/attachments`，目标Flag文件位于 `/work/runtime/flag.txt`。

将获得的完整Flag提交到AWDP平台本题的Flag输入框。仅测试管理员提供的攻击实例。

## 修复阶段：100分

仅修改 `src/app.py`，提交UTF-8 unified diff，最大512 KiB。补丁头应使用 `a/src/app.py`、`b/src/app.py`。平台会在全新断网容器中应用补丁，检查功能和安全性。

必须保留：健康检查、附件列表、普通及嵌套路径、带空格和文件名内部包含两个点的合法文件、空文件、二进制文件及随机动态附件。返回正确内容；不能通过关闭下载或固定返回测试答案修复。

必须拒绝：根目录之外的相对路径、绝对路径越界、越界符号链接、非法及不存在文件。合法附件的绝对路径是否可用不是业务要求。错误请求返回400/403/404，不应卡住或返回500。

可使用标准库；没有在线安装依赖和外网访问。校验基于动态夹具和协议测试，仍可能存在有限测试覆盖；人为绕过判题器不属于有效修复，正式比赛需人工复核。

## 本地运行（Linux、Python 3.8及以上）

在解压附件的目录执行：

```bash
mkdir -p runtime/attachments/tickets/1042
printf 'hello\n' > runtime/attachments/welcome.txt
printf 'flag{local-practice-only}\n' > runtime/flag.txt
ATTACHMENT_ROOT="$PWD/runtime/attachments" TICKET_PORT=8080 python3 src/app.py
```

访问 http://127.0.0.1:8080/download?name=welcome.txt 。本地练习Flag不能提交到服务器得分。

修改前保留原始源码，修改后与原始源码比较，生成UTF-8 unified diff；每次都是原始基线到当前修复的完整补丁，不是上一版到下一版的增量。可用Linux/WSL的diff或能设置UTF-8的IDE导出。不要上传完整源码、zip或管理员参考补丁包。
