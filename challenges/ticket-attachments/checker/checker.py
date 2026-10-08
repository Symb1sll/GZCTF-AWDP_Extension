import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get('CHECK_BASE', 'http://127.0.0.1:8080')
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def get(path):
    try:
        with OPENER.open(BASE + path, timeout=2) as response:
            return response.status, response.read(131072)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(131072)


def result(passed, message):
    print('AWDP_RESULT=' + json.dumps({'passed': passed, 'message': message},
                                     ensure_ascii=False), flush=True)
    return 0 if passed else 1


def check():
    for _ in range(20):
        try:
            if get('/health') == (200, b'ok\n'):
                break
        except OSError:
            pass
        time.sleep(0.2)
    else:
        return result(False, '服务健康检查失败')
    expected = {'welcome.txt': b'Welcome to HelpDesk\n',
                'tickets/1042/report.txt': b'Ticket 1042: repaired\n',
                'release..notes.txt': b'Two dots inside a filename are valid\n',
                'space name.txt': b'Spaces are valid\n',
                'empty.txt': b'', 'binary.bin': bytes(range(256))}
    code, listing = get('/api/attachments')
    if code != 200:
        return result(False, '附件列表不可用')
    names = json.loads(listing)['files']
    if not set(expected).issubset(names):
        return result(False, '正常附件列表缺失')
    for name, content in expected.items():
        if get('/download?name=' + urllib.parse.quote(name, safe='')) != (200, content):
            return result(False, '正常附件内容或状态错误: ' + name)
    random_names = [n for n in names if n.startswith('tickets/1042/') and n not in expected]
    if len(random_names) != 3:
        return result(False, '动态附件列表不完整')
    for name in random_names:
        code, content = get('/download?name=' + urllib.parse.quote(name, safe=''))
        if code != 200 or len(content) != 48 or any(c not in b'0123456789abcdef' for c in content):
            return result(False, '动态附件业务失败')
    blocked = ['../flag.txt', '../private.txt', '../attachments-private/secret.txt',
               '/work/runtime/flag.txt', '/etc/passwd', 'external-link.txt',
               'tickets/1042/../../../private.txt', 'does-not-exist.txt', '.', '']
    for name in blocked:
        code, _ = get('/download?name=' + urllib.parse.quote(name, safe=''))
        if code not in (400, 403, 404):
            return result(False, '越界或非法附件未被拒绝')
    for raw in ['%2e%2e%2fflag.txt', '..%2Fprivate.txt', '%2Fetc%2Fpasswd', '%00']:
        if get('/download?name=' + raw)[0] not in (400, 403, 404):
            return result(False, '编码路径未被拒绝')
    return result(True, '正常下载、动态附件和越界访问回归通过')


def main():
    try:
        return check()
    except (TimeoutError, OSError, urllib.error.URLError):
        return result(False, '业务请求超时或连接中断')
    except Exception:
        return result(False, '服务响应格式不符合题目协议')


if __name__ == '__main__':
    raise SystemExit(main())
