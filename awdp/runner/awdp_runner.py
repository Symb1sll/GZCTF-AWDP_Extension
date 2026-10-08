#!/usr/bin/env python3
"""Privileged but narrow AWDP Docker executor.

Judge containers never receive Docker access. The trusted GZCTF control plane
still uses Docker for attack instances. This service accepts only a
small fixed job schema, resolves challenge images from a root-owned allowlist,
and launches target/checker containers with hard-coded sandbox options.
"""

import concurrent.futures
import datetime
import json
import hashlib
import os
import pathlib
import re
import shutil
import signal
import subprocess
import threading
import time
import uuid


DATA_DIR = pathlib.Path(os.environ.get("AWDP_DATA_DIR", "/srv/awdp-dev/data"))
CONFIG_DIR = pathlib.Path(os.environ.get("AWDP_CONFIG_DIR", "/srv/awdp-dev/config"))
QUEUE_DIR = pathlib.Path(os.environ.get("AWDP_QUEUE_DIR", "/srv/awdp-dev/queue"))
TMP_DIR = pathlib.Path(os.environ.get("AWDP_TMP_DIR", "/srv/awdp-dev/tmp/jobs"))
MANAGED_LABEL = "gzctf.awdp.dev.managed=true"
CONCURRENCY = max(1, min(3, int(os.environ.get("AWDP_CONCURRENCY", "3"))))
MAX_PATCH_BYTES = 512 * 1024
ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")
IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
STOP = threading.Event()


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def challenges_config():
    data = load_json(CONFIG_DIR / "challenges.json")
    result = {}
    for item in data.get("challenges", []):
        challenge_id = str(item.get("id", ""))
        if not ID_RE.fullmatch(challenge_id) or not item.get("enabled", True):
            continue
        target = str(item.get("target_image_id", ""))
        checker = str(item.get("checker_image_id", ""))
        if not IMAGE_ID_RE.fullmatch(target) or not IMAGE_ID_RE.fullmatch(checker):
            continue
        result[challenge_id] = {
            "id": challenge_id,
            "target_image_id": target,
            "checker_image_id": checker,
            "fix_score": max(0, min(100000, int(item.get("fix_score", 100)))),
            "allowed_paths": [str(x) for x in item.get("allowed_paths", ["src/"])],
            "timeout_seconds": max(10, min(300, int(item.get("timeout_seconds", 90)))),
            "target_memory": str(item.get("target_memory", "512m")),
            "target_cpus": str(item.get("target_cpus", "1.0")),
        }
    return result


def validate_patch(blob, allowed_prefixes):
    if not blob or len(blob) > MAX_PATCH_BYTES or b"\x00" in blob:
        raise ValueError("invalid patch size or content")
    text = blob.decode("utf-8")
    if "GIT binary patch" in text or "Binary files " in text:
        raise ValueError("binary patch rejected")
    if re.search(r"(?m)^new file mode 120000$", text):
        raise ValueError("symlink patch rejected")
    paths = []
    for line in text.splitlines():
        if not (line.startswith("--- ") or line.startswith("+++ ")):
            continue
        raw = line[4:].split("\t", 1)[0].strip()
        if raw == "/dev/null":
            continue
        if raw.startswith("a/") or raw.startswith("b/"):
            raw = raw[2:]
        parts = pathlib.PurePosixPath(raw).parts
        if not raw or raw.startswith("/") or "\\" in raw or any(x in ("", ".", "..") for x in parts):
            raise ValueError("unsafe patch path")
        if not any(raw == prefix.rstrip("/") or (prefix.endswith("/") and raw.startswith(prefix)) for prefix in allowed_prefixes):
            raise ValueError("patch path outside allowlist")
        paths.append(raw)
    if not paths or len(set(paths)) > 30:
        raise ValueError("invalid patched file count")


def run_command(argv, timeout=None, check=False):
    return subprocess.run(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        timeout=timeout,
        check=check,
    )


def docker_cleanup(name):
    run_command(["docker", "rm", "-f", name], timeout=20)


def bounded(text, limit=16000):
    text = text or ""
    return text[-limit:]


def write_result(submission_id, result):
    try:
        job = load_json(QUEUE_DIR / "running" / (submission_id + ".json"))
        if not isinstance(job, dict):
            job = {}
    except (OSError, ValueError):
        job = {}  # Emit an unbound error; the ledger rejects it, never awards points.
    result.update({key: job.get(key) for key in ("team_id", "challenge_id", "patch_sha256")})
    result["submission_id"] = submission_id
    target = QUEUE_DIR / "results" / (submission_id + ".json")
    temp = target.with_name("." + target.name + ".tmp")
    payload = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with temp.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(str(temp), 0o660)
    os.replace(str(temp), str(target))


def parse_checker(output):
    for line in reversed(output.splitlines()):
        if line.startswith("AWDP_RESULT="):
            value = json.loads(line[len("AWDP_RESULT="):])
            if not isinstance(value, dict):
                break
            return value
    raise ValueError("checker did not emit AWDP_RESULT")


def execute_job(job_path):
    started = utc_now()
    submission_id = job_path.stem
    stage_dir = None
    target_name = None
    checker_name = None
    try:
        uuid.UUID(submission_id)
        if job_path.is_symlink() or job_path.stat().st_size > 64 * 1024:
            raise ValueError("invalid job file")
        job = load_json(job_path)
        if job.get("schema_version") != 1 or str(job.get("submission_id")) != submission_id:
            raise ValueError("invalid job schema")
        team_id = str(job.get("team_id", ""))
        challenge_id = str(job.get("challenge_id", ""))
        if not ID_RE.fullmatch(team_id) or not ID_RE.fullmatch(challenge_id):
            raise ValueError("invalid identifiers")
        challenge = challenges_config().get(challenge_id)
        if not challenge:
            raise ValueError("challenge is not in the runner allowlist")

        source_patch = DATA_DIR / "submissions" / (submission_id + ".patch")
        if source_patch.is_symlink() or not source_patch.is_file() or source_patch.stat().st_size > MAX_PATCH_BYTES:
            raise ValueError("submission patch is missing or invalid")
        blob = source_patch.read_bytes()
        if hashlib.sha256(blob).hexdigest() != job.get("patch_sha256"):
            raise ValueError("patch digest mismatch")
        validate_patch(blob, challenge["allowed_paths"])

        stage_dir = TMP_DIR / submission_id
        stage_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
        staged_patch = stage_dir / "patch.diff"
        staged_patch.write_bytes(blob)
        os.chmod(str(staged_patch), 0o444)

        short = submission_id.replace("-", "")[:20]
        target_name = "gzctf-awdp-dev-target-" + short
        checker_name = "gzctf-awdp-dev-checker-" + short
        target_cmd = [
            "docker", "run", "-d", "--init",
            "--name", target_name,
            "--label", MANAGED_LABEL,
            "--label", "awdp.submission=" + submission_id,
            "--network", "none",
            "--read-only",
            "--tmpfs", "/work:rw,exec,nosuid,nodev,size=256m,uid=65534,gid=65534,mode=700",
            "--user", "65534:65534",
            "--cap-drop", "ALL",
            "--security-opt", "apparmor=docker-default",
            "--security-opt", "no-new-privileges:true",
            "--pids-limit", "128",
            "--memory", challenge["target_memory"],
            "--cpus", challenge["target_cpus"],
            "--ulimit", "nofile=256:256",
            "--mount", "type=bind,src=%s,dst=/submission/patch.diff,readonly" % staged_patch,
            challenge["target_image_id"],
        ]
        target_start = run_command(target_cmd, timeout=45)
        if target_start.returncode != 0:
            raise RuntimeError("target start failed: " + bounded(target_start.stdout, 4000))
        time.sleep(1)
        state = run_command(
            ["docker", "inspect", "--format", "{{.State.Running}}", target_name], timeout=15
        )
        if state.returncode != 0 or state.stdout.strip() != "true":
            logs = run_command(["docker", "logs", target_name], timeout=15)
            raise RuntimeError("target exited before checking: " + bounded(logs.stdout, 6000))

        checker_cmd = [
            "docker", "run", "--rm", "--init",
            "--name", checker_name,
            "--label", MANAGED_LABEL,
            "--label", "awdp.submission=" + submission_id,
            "--network", "container:" + target_name,
            "--read-only",
            "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777",
            "--user", "65534:65534",
            "--cap-drop", "ALL",
            "--security-opt", "apparmor=docker-default",
            "--security-opt", "no-new-privileges:true",
            "--pids-limit", "64",
            "--memory", "128m",
            "--cpus", "0.25",
            "--ulimit", "nofile=128:128",
            challenge["checker_image_id"],
        ]
        try:
            checker = run_command(checker_cmd, timeout=challenge["timeout_seconds"])
        except subprocess.TimeoutExpired:
            docker_cleanup(checker_name)
            result = {
                "status": "timeout",
                "score": 0,
                "message": "判题超时",
                "log_excerpt": "checker timeout",
                "started_at": started,
                "finished_at": utc_now(),
            }
            write_result(submission_id, result)
            return
        parsed = parse_checker(checker.stdout)
        passed = checker.returncode == 0 and parsed.get("passed") is True
        target_logs = run_command(["docker", "logs", target_name], timeout=15)
        result = {
            "status": "passed" if passed else "failed",
            "score": challenge["fix_score"] if passed else 0,
            "message": str(parsed.get("message", "通过" if passed else "未通过"))[:1000],
            "log_excerpt": bounded("[checker]\n" + checker.stdout + "\n[target]\n" + target_logs.stdout),
            "started_at": started,
            "finished_at": utc_now(),
        }
        write_result(submission_id, result)
    except Exception as exc:
        write_result(
            submission_id,
            {
                "status": "error",
                "score": 0,
                "message": "判题执行错误",
                "log_excerpt": bounded(type(exc).__name__ + ": " + str(exc)),
                "started_at": started,
                "finished_at": utc_now(),
            },
        )
    finally:
        if checker_name:
            docker_cleanup(checker_name)
        if target_name:
            docker_cleanup(target_name)
        if stage_dir:
            shutil.rmtree(str(stage_dir), ignore_errors=True)
        archive = QUEUE_DIR / "archive" / job_path.name
        try:
            os.replace(str(job_path), str(archive))
        except OSError:
            pass


def recover_previous_jobs():
    for path in (QUEUE_DIR / "running").glob("*.json"):
        try:
            os.replace(str(path), str(QUEUE_DIR / "pending" / path.name))
        except OSError:
            pass
    ids = run_command(
        ["docker", "ps", "-aq", "--filter", "label=" + MANAGED_LABEL], timeout=30
    )
    if ids.returncode == 0:
        for container_id in ids.stdout.split():
            run_command(["docker", "rm", "-f", container_id], timeout=20)


def signal_stop(signum, frame):
    STOP.set()


def main():
    os.umask(0o007)
    for child in ("pending", "running", "results", "archive", "failed"):
        (QUEUE_DIR / child).mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    recover_previous_jobs()
    signal.signal(signal.SIGTERM, signal_stop)
    signal.signal(signal.SIGINT, signal_stop)
    active = set()
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        while not STOP.is_set():
            active = {future for future in active if not future.done()}
            slots = CONCURRENCY - len(active)
            if slots > 0:
                for pending in sorted((QUEUE_DIR / "pending").glob("*.json"))[:slots]:
                    running = QUEUE_DIR / "running" / pending.name
                    try:
                        os.replace(str(pending), str(running))
                    except OSError:
                        continue
                    active.add(pool.submit(execute_job, running))
            STOP.wait(1.0)
        for future in active:
            try:
                future.result(timeout=330)
            except Exception:
                pass


if __name__ == "__main__":
    main()
