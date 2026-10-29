#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
从 Boom Library 的 "... Single" 长文件里自动切出单发采样，转成游戏可用规格。

为什么需要它：
    Tactical Guns 的 Single 文件不是"一发"，而是把若干个单发串在一个 wav 里
    （G36 Close Single 是 26.9 秒、6 发、间隔约 4.7 秒），而且规格是
    96 kHz / 24 bit / 立体声。游戏里既不能整段播，也不需要这么高的采样率。

  它做的事：
    1. 读 24bit wav（Boom 全系都是这个格式）
    2. 低通 + 二取一 降采样到 48 kHz（先滤波再抽取，避免混叠带来的刺耳感）
    3. 用包络检测找出每一发，按"起音前留 20ms + 尾音多留 250ms"切开
    4. 每发峰值归一到 -3 dBFS（多版本随机播放时响度才统一）
    5. 写 16bit / 48kHz / 立体声 wav 到 Unity 目录

用法：
    python Tools/cut_gun_sounds.py <输入.wav> <输出目录> <文件名前缀> [--max N]

例：
    python Tools/cut_gun_sounds.py \
        "D:/Game/GAMEdev/bl_tactical_guns_ds/GUNAuto_AR-HK G36 Close Single_B00M_TGDS.wav" \
        "D:/Game/GAMEdev/ZombieExtraction/Assets/Audio/Weapons/G36C" g36_close

注意：
    自动切分靠"音量包络超过阈值"，对 Boom 这种已经处理过的素材准确率高，
    但仍有小概率把一发切成两段、或把两发并成一段。跑完看一眼打印的时长，
    有异常的那一发删掉重跑即可（改 --threshold 调整灵敏度）。
"""

import wave
import os
import sys
import math

TARGET_SR = 48000
TARGET_PEAK = 0.708   # -3 dBFS


# ────────────────────────────── 读取 ──────────────────────────────

def read_wav_24(path):
    """读 24bit wav，返回 (每声道浮点样本列表, 采样率, 声道数)"""
    w = wave.open(path, "rb")
    ch, sr, sw, n = w.getnchannels(), w.getframerate(), w.getsampwidth(), w.getnframes()
    raw = w.readframes(n)
    w.close()

    if sw != 3:
        raise SystemExit(f"只处理 24bit wav，这个文件是 {sw * 8}bit：{path}")

    scale = 1.0 / 8388608.0
    chans = [[0.0] * n for _ in range(ch)]

    # 紧密循环：24bit 小端，按帧交错
    for i in range(n):
        base = i * ch * 3
        for c in range(ch):
            p = base + c * 3
            v = raw[p] | (raw[p + 1] << 8) | (raw[p + 2] << 16)
            if v & 0x800000:
                v -= 0x1000000
            chans[c][i] = v * scale

    return chans, sr, ch


# ────────────────────────────── 降采样 ──────────────────────────────

def biquad_lowpass(samples, sr, fc, q):
    """RBJ 二阶低通（直接 I 型）"""
    w0 = 2.0 * math.pi * fc / sr
    cosw = math.cos(w0)
    alpha = math.sin(w0) / (2.0 * q)

    b0 = (1.0 - cosw) * 0.5
    b1 = 1.0 - cosw
    b2 = b0
    a0 = 1.0 + alpha
    a1 = -2.0 * cosw
    a2 = 1.0 - alpha

    b0 /= a0; b1 /= a0; b2 /= a0
    a1 /= a0; a2 /= a0

    out = [0.0] * len(samples)
    x1 = x2 = y1 = y2 = 0.0
    for i, x in enumerate(samples):
        y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2 = x1; x1 = x
        y2 = y1; y1 = y
        out[i] = y
    return out


def downsample(chans, sr, target_sr):
    """先低通再抽取。用两级 Butterworth 级联（Q=0.5412 / 1.3066）做成 4 阶"""
    if sr == target_sr:
        return chans, sr
    if sr % target_sr != 0:
        raise SystemExit(f"暂不支持 {sr} → {target_sr} 的非整数倍转换")

    factor = sr // target_sr
    # 截止取目标奈奎斯特的 0.9 倍，留出过渡带
    fc = target_sr * 0.5 * 0.9

    result = []
    for ch_data in chans:
        y = biquad_lowpass(ch_data, sr, fc, 0.5412)
        y = biquad_lowpass(y, sr, fc, 1.3066)
        result.append(y[::factor])
    return result, target_sr


# ────────────────────────────── 检测 ──────────────────────────────

def envelope(chans, sr, block_ms=5):
    """按块取绝对值峰值，返回包络列表（每块一个值）"""
    n = len(chans[0])
    blk = max(1, int(sr * block_ms / 1000.0))
    env = []
    for start in range(0, n, blk):
        end = min(start + blk, n)
        peak = 0.0
        for c in chans:
            seg = c[start:end]
            m = max(abs(v) for v in seg) if seg else 0.0
            if m > peak:
                peak = m
        env.append(peak)
    return env, blk


def find_regions(env, blk, sr, threshold_ratio=0.02, merge_ms=300, min_ms=80):
    """找出超过阈值的连续区间，间隔小于 merge_ms 的合并（防止一发被尾音低谷切成两段）。

    短于 min_ms 的一律丢掉：枪声超过阈值至少持续上百毫秒，
    而母带里的咔哒、纸声、房间本底只会冒出几毫秒，不过滤会把它们当成一发切出来。
    """
    gmax = max(env) if env else 0.0
    if gmax <= 0:
        return []
    thr = gmax * threshold_ratio
    merge_blocks = int(merge_ms / 1000.0 * sr / blk)

    regions = []
    start = None
    last_on = None

    for i, v in enumerate(env):
        if v > thr:
            if start is None:
                start = i
            last_on = i
        else:
            if start is not None and last_on is not None and (i - last_on) > merge_blocks:
                regions.append((start, last_on))
                start = None
                last_on = None
    if start is not None and last_on is not None:
        regions.append((start, last_on))

    # 块 → 采样点，顺便丢掉过短的（毛刺）
    min_blocks = max(1, int(min_ms / 1000.0 * sr / blk))
    return [(a * blk, b * blk) for a, b in regions if (b - a) >= min_blocks]


# ────────────────────────────── 写出 ──────────────────────────────

def slice_and_normalize(chans, sr, start, end, pre_ms=20, tail_ms=250, max_ms=3000):
    """切出一段，前后留余量，峰值归一到 TARGET_PEAK"""
    a = max(0, start - int(sr * pre_ms / 1000.0))
    b = min(len(chans[0]), end + int(sr * tail_ms / 1000.0))

    # 截断上限，避免把下一发吃进来
    limit = int(sr * max_ms / 1000.0)
    if b - a > limit:
        b = a + limit

    out = [c[a:b] for c in chans]

    peak = 0.0
    for c in out:
        m = max(abs(v) for v in c)
        if m > peak:
            peak = m
    if peak > 0:
        g = TARGET_PEAK / peak
        out = [[v * g for v in c] for c in out]

    return out, (b - a) / float(sr)


def write_wav_16(path, chans, sr):
    w = wave.open(path, "wb")
    w.setnchannels(len(chans))
    w.setsampwidth(2)
    w.setframerate(sr)

    n = len(chans[0])
    buf = bytearray(n * len(chans) * 2)
    p = 0
    for i in range(n):
        for c in chans:
            v = c[i]
            if v > 1.0: v = 1.0
            elif v < -1.0: v = -1.0
            iv = int(round(v * 32767.0))
            buf[p] = iv & 0xFF
            buf[p + 1] = (iv >> 8) & 0xFF
            p += 2

    w.writeframes(bytes(buf))
    w.close()


# ────────────────────────────── 主流程 ──────────────────────────────

def main():
    if len(sys.argv) < 4:
        print(__doc__)
        raise SystemExit(1)

    src, outdir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]

    threshold = 0.02
    max_count = 0
    if "--threshold" in sys.argv:
        threshold = float(sys.argv[sys.argv.index("--threshold") + 1])
    if "--max" in sys.argv:
        max_count = int(sys.argv[sys.argv.index("--max") + 1])

    if not os.path.isfile(src):
        raise SystemExit("找不到输入文件：" + src)

    print(f"读入：{os.path.basename(src)}")
    chans, sr, ch = read_wav_24(src)
    print(f"  原始规格：{sr} Hz / 24 bit / {ch} 声道 / {len(chans[0]) / sr:.2f} 秒")

    chans, sr = downsample(chans, sr, TARGET_SR)
    print(f"  已降到：{sr} Hz / 16 bit / {ch} 声道（4 阶低通 + 抽取）")

    env, blk = envelope(chans, sr)
    regions = find_regions(env, blk, sr, threshold_ratio=threshold)

    # 再过一道：局部峰值太低的丢掉。真正的枪声不会是全曲最响的十几分之一。
    if regions:
        gmax = max(env)
        regions = [r for r in regions
                   if max(env[r[0] // blk: max(r[0] // blk + 1, r[1] // blk)]) >= gmax * 0.08]

    print(f"  检测到 {len(regions)} 发（阈值 {threshold:.0%}）")

    if not regions:
        raise SystemExit("一发都没检测到，试试 --threshold 0.005")

    if max_count and len(regions) > max_count:
        regions = regions[:max_count]

    os.makedirs(outdir, exist_ok=True)

    print(f"\n{'序号':<6}{'时长':>8}  文件")
    for i, (a, b) in enumerate(regions, 1):
        data, dur = slice_and_normalize(chans, sr, a, b)
        name = f"{prefix}_{i:02d}.wav"
        path = os.path.join(outdir, name)
        write_wav_16(path, data, sr)
        flag = ""
        if dur > 2.5:
            flag = "  ⚠ 偏长，可能含下一发"
        elif dur < 0.15:
            flag = "  ⚠ 偏短，可能切坏了"
        print(f"{i:<6}{dur:>7.2f}s  {name}{flag}")

    print(f"\n已写入：{outdir}")
    print("下一步：Unity 里等它导入，然后把这些 wav 拖进对应的 WeaponAudio 配置的 Close Shots 数组。")


if __name__ == "__main__":
    main()
