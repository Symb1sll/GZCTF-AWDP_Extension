# 修复补丁如何制作

附件的 `src/app.py` 是每次判题的原始基线。仅修改该文件，保存为 UTF-8 / LF；保留健康检查、列表和正常下载，修复目录越界读取，不能关闭业务或硬编码测试答案。

管理员示例：`good-fix.patch` 为参考修复；`bad-fix.patch` 保持漏洞；`disable-download.patch` 关闭功能，应失败。示例用于本题回归，不是通用修复模板。

分别保留 `original/` 和 `fixed/`，以 `diff -u --label a/src/app.py --label b/src/app.py` 生成补丁。diff 返回 1 表示有差异，是正常结果；0 是空补丁，大于 1 是错误。命令见 [COMMANDS.md](COMMANDS.md)。

修改第二版时继续编辑 `fixed/src/app.py`，仍与 `original/src/app.py` 比较；每次提交原始源码到当前修复的完整差异，不能交上一版修复到下一版的增量。不要手改补丁的 hunk 行数。

API 接收最大 512 KiB 的 UTF-8 unified diff，网页面板负责请求格式。不要上传完整源码、zip、镜像或参考答案包。平台校验身份和路径，在全新断网判题容器中应用补丁并运行 checker；在线攻击实例不受补丁替换。

`patch --dry-run` 只检查可应用性，不证明安全和功能通过。本题包含普通/嵌套附件、空格、文件名内部两个点、空/二进制文件、动态随机附件和越界符号链接检查。

Git 用户也可 `git diff -- src/app.py`，但基线必须正确。旧 Windows PowerShell 重定向编码可能不是 UTF-8，建议用 WSL/Linux 或明确设置 UTF-8 的编辑器导出。
