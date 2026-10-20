#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Unity 官方安装包多连接分片下载器（仅使用官方 CDN 原始 URL + HTTP Range 请求）

用途：Unity 官方 CDN 对单连接限速（实测单流约 100 KB/s，12 连接聚合约 10 MB/s），
      本脚本用多个并发 Range 请求提升总吞吐，下载完成后用官方 MD5 校验完整性。

特点：
  - 不修改、不拼接 URL，仅对官方原地址发起合法的分段请求
  - 断点续传：已完成的 32MB 分片会跳过
  - 完成后校验文件大小与官方 MD5（md5-<base64> 格式）
用法：
  python unity_fetch.py --url URL --out PATH --size BYTES [--md5b64 XXX] [--workers 12]
"""

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time

CHUNK = 32 * 1024 * 1024  # 32 MB
PROXY = "http://127.0.0.1:7890"  # 本机 Clash 混合端口

lock = threading.Lock()
done_bytes = [0]
done_chunks = [0]


def fetch_chunk(url, start, end, path, retries=5):
    """用 curl 拉取 [start, end] 区间到一个分片文件，成功返回 True"""
    for attempt in range(1, retries + 1):
        r = subprocess.run(
            [
                "curl", "-sS", "-L", "-x", PROXY,
                "--connect-timeout", "20", "--max-time", "600",
                "-r", f"{start}-{end}",
                "-o", path, url,
            ],
            capture_output=True, text=True,
        )
        if r.returncode == 0 and os.path.exists(path):
            expect = end - start + 1
            got = os.path.getsize(path)
            if got == expect:
                return True
            # 长度不符则删除重试
            try:
                os.remove(path)
            except OSError:
                pass
        time.sleep(1.5 * attempt)
    return False


def worker(url, chunks, out_dir, total, errors):
    while True:
        with lock:
            if not chunks:
                return
            idx, start, end = chunks.pop(0)
        path = os.path.join(out_dir, f"chunk_{idx:05d}")
        if os.path.exists(path) and os.path.getsize(path) == end - start + 1:
            with lock:
                done_bytes[0] += end - start + 1
                done_chunks[0] += 1
            continue
        ok = fetch_chunk(url, start, end, path)
        with lock:
            if ok:
                done_bytes[0] += end - start + 1
                done_chunks[0] += 1
            else:
                errors.append(idx)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=int, required=True)
    ap.add_argument("--md5b64", default="")
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()

    out = args.out
    out_dir = out + ".parts"
    os.makedirs(out_dir, exist_ok=True)

    total = args.size
    chunks = []
    idx = 0
    s = 0
    while s < total:
        e = min(s + CHUNK - 1, total - 1)
        chunks.append((idx, s, e))
        idx += 1
        s = e + 1
    total_chunks = len(chunks)

    print(f"[开始] {os.path.basename(out)}  共 {total/1048576:.1f} MB / {total_chunks} 个分片 / {args.workers} 并发", flush=True)

    threads = []
    errors = []
    for _ in range(args.workers):
        t = threading.Thread(target=worker, args=(args.url, chunks, out_dir, total, errors), daemon=True)
        t.start()
        threads.append(t)

    start_time = time.time()
    last_t = start_time
    last_b = 0
    while any(t.is_alive() for t in threads):
        time.sleep(2)
        with lock:
            b = done_bytes[0]
            c = done_chunks[0]
        now = time.time()
        if now - last_t >= 5:
            sp = (b - last_b) / (now - last_t) / 1048576
            pct = b / total * 100
            eta = (total - b) / max((b / max(now - start_time, 1)), 1) / 60
            print(f"  {pct:5.1f}%  {b/1048576:7.0f}/{total/1048576:.0f} MB  {sp:5.1f} MB/s  分片 {c}/{total_chunks}  预计剩余 {eta:.1f} 分钟", flush=True)
            last_t, last_b = now, b
    for t in threads:
        t.join()

    if errors:
        print(f"[失败] 有 {len(errors)} 个分片未完成: {errors[:10]}，可重新运行本脚本续传", flush=True)
        return 2

    # 合并
    print("[合并] 正在拼接分片...", flush=True)
    with open(out, "wb") as fo:
        for i in range(total_chunks):
            p = os.path.join(out_dir, f"chunk_{i:05d}")
            with open(p, "rb") as fi:
                shutil.copyfileobj(fi, fo, 8 * 1024 * 1024)
    got = os.path.getsize(out)
    print(f"[合并完成] {out}  {got/1048576:.1f} MB", flush=True)
    if got != total:
        print(f"[错误] 大小不符：期望 {total}，实际 {got}", flush=True)
        return 3

    # 校验
    if args.md5b64:
        print("[校验] 计算 MD5 ...", flush=True)
        m = hashlib.md5()
        with open(out, "rb") as f:
            for block in iter(lambda: f.read(16 * 1024 * 1024), b""):
                m.update(block)
        expect = base64.b64decode(args.md5b64).hex()
        actual = m.hexdigest()
        ok = expect == actual
        print(f"[校验] 官方 {expect}", flush=True)
        print(f"[校验] 实际 {actual}  ->  {'通过 ✅' if ok else '不通过 ❌'}", flush=True)
        if not ok:
            return 4
        shutil.rmtree(out_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
