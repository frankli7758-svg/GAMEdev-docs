#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
合成一套"换弹音效"占位素材（48kHz / 16bit / 立体声）。

⚠️ 这些是**程序合成的**，不是录音。
   Boom Library 的 Tactical Guns Designed 版只包含枪声，
   换弹/操作声在 Construction Kit 里（$139），或者去 Sonnsoniss GDC 免费包里翻。
   本脚本的作用是让换弹链路今天就能跑通、时序能对上动画；
   拿到真实录音后，**用同名 wav 覆盖掉即可，代码和配置都不用动**。

合成思路（游戏音效行业常见的"金属撞击"配方）：
   金属声 = 短促噪声爆发 × 快速衰减包络 → 几个不成谐波关系的带通滤波器
   再加一个低频"闷响"提供重量感。
   这三个要素凑齐，听起来就是"金属件被撞了一下"，而不是"电子滴答"。

输出 5 段（对应换弹动画的 5 个动作）：
   1_release  弹匣卡榫释放   —— 清脆的高频"咔"
   2_magout   弹匣滑出/掉落   —— 摩擦声 + 低闷响
   3_magin    新弹匣插入      —— 闷响 + 金属卡到位
   4_seat     拍实/推到位     —— 两声短促"咔咔"
   5_bolt     拉枪机          —— 摩擦 + 硬脆"锵" + 弹簧余音

用法：
    python Tools/make_reload_sfx.py <输出目录> [--metal 3200] [--prefix g36_reload]
"""

import wave
import math
import os
import sys
import random

SR = 48000


# ────────────────────────────── 基础工具 ──────────────────────────────

def biquad(sig, fc, q, kind="bandpass"):
    """RBJ 双二阶滤波器（bandpass / lowpass）"""
    w0 = 2.0 * math.pi * fc / SR
    cosw = math.cos(w0)
    alpha = math.sin(w0) / (2.0 * q)

    if kind == "bandpass":
        b0 = alpha
        b1 = 0.0
        b2 = -alpha
    else:  # lowpass
        b0 = (1.0 - cosw) * 0.5
        b1 = 1.0 - cosw
        b2 = b0

    a0 = 1.0 + alpha
    a1 = -2.0 * cosw
    a2 = 1.0 - alpha

    b0 /= a0; b1 /= a0; b2 /= a0
    a1 /= a0; a2 /= a0

    out = [0.0] * len(sig)
    x1 = x2 = y1 = y2 = 0.0
    for i, x in enumerate(sig):
        y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2 = x1; x1 = x
        y2 = y1; y1 = y
        out[i] = y
    return out


def noise(n, seed):
    rnd = random.Random(seed)
    return [rnd.uniform(-1.0, 1.0) for _ in range(n)]


def env_exp(n, attack_ms, decay_ms):
    """起音线性上升 + 指数衰减"""
    a = max(1, int(SR * attack_ms / 1000.0))
    d = max(1, int(SR * decay_ms / 1000.0))
    out = [0.0] * n
    for i in range(n):
        if i < a:
            out[i] = i / float(a)
        else:
            out[i] = math.exp(-(i - a) / float(d))
    return out


def apply_env(sig, e):
    return [s * g for s, g in zip(sig, e)]


def sine(n, freq, decay_ms, seed=0):
    d = max(1, int(SR * decay_ms / 1000.0))
    phase = random.Random(seed).uniform(0, 6.28)
    return [math.sin(2 * math.pi * freq * i / SR + phase) * math.exp(-i / float(d))
            for i in range(n)]


def metal(n, base_fc, decay_ms, seed, spread=1.0):
    """
    金属撞击：噪声过 3 个不成谐波关系的带通。
    比例 1 / 2.17 / 3.79 是刻意选的——整数倍会听起来像音高，非整数倍才像金属。
    """
    src = noise(n, seed)
    total = [0.0] * n

    for ratio, q, gain in ((1.0, 7.0, 1.0), (2.17, 9.0, 0.55), (3.79, 12.0, 0.3)):
        fc = base_fc * ratio * spread
        if fc >= SR * 0.45:
            continue
        band = biquad(src, fc, q, "bandpass")
        total = [t + b * gain for t, b in zip(total, band)]

    return apply_env(total, env_exp(n, 0.3, decay_ms))


def thud(n, freq, decay_ms, seed=0):
    """低频闷响：正弦 + 低通噪声，提供重量感"""
    body = sine(n, freq, decay_ms, seed)
    air = apply_env(biquad(noise(n, seed + 7), freq * 3.5, 0.9, "lowpass"),
                    env_exp(n, 0.5, decay_ms * 0.8))
    return [b * 0.8 + a * 0.5 for b, a in zip(body, air)]


def scrape(n, fc, attack_ms, decay_ms, seed, q=1.1):
    """摩擦声：带通噪声 + 较慢的起音"""
    band = biquad(noise(n, seed), fc, q, "bandpass")
    return apply_env(band, env_exp(n, attack_ms, decay_ms))


def mix_into(dst, src, offset, gain=1.0):
    for i, v in enumerate(src):
        j = offset + i
        if 0 <= j < len(dst):
            dst[j] += v * gain
    return dst


def normalize(sig, peak):
    m = max(abs(v) for v in sig) if sig else 0.0
    if m <= 0:
        return sig
    g = peak / m
    return [v * g for v in sig]


def pad(sig, n):
    return sig + [0.0] * (n - len(sig)) if len(sig) < n else sig[:n]


def widen(left, right, delay_ms=0.7, gain=0.35):
    """给左右声道一点点时间差，听起来才是"立体声的金属"而不是单声道贴片"""
    d = int(SR * delay_ms / 1000.0)
    r2 = list(right)
    for i in range(len(left)):
        j = i - d
        if j >= 0:
            r2[i] += left[j] * gain
    return left, r2


# ────────────────────────────── 五个动作 ──────────────────────────────

def build_release(metal_fc, seed):
    """弹匣卡榫释放：短促清脆"""
    n = int(SR * 0.05)
    out = [0.0] * n
    mix_into(out, metal(n, metal_fc * 1.45, 4, seed), 0, 1.0)
    mix_into(out, metal(n, metal_fc * 0.55, 8, seed + 1), 0, 0.35)
    return out, 0.42


def build_magout(metal_fc, seed):
    """弹匣滑出 + 掉落"""
    n = int(SR * 0.22)
    out = [0.0] * n
    mix_into(out, scrape(n, metal_fc * 0.6, 6, 55, seed), 0, 0.7)
    mix_into(out, thud(n, 105, 45, seed + 3), int(SR * 0.10), 0.45)
    mix_into(out, metal(n, metal_fc * 0.85, 10, seed + 5), int(SR * 0.11), 0.25)
    return out, 0.42


def build_magin(metal_fc, seed):
    """新弹匣插入：闷响 + 卡到位"""
    n = int(SR * 0.20)
    out = [0.0] * n
    mix_into(out, thud(n, 92, 55, seed), 0, 0.9)
    mix_into(out, metal(n, metal_fc * 0.9, 12, seed + 2), 0, 0.3)
    mix_into(out, metal(n, metal_fc * 1.3, 6, seed + 4), int(SR * 0.085), 0.85)
    return out, 0.5


def build_seat(metal_fc, seed):
    """拍实：两声咔"""
    n = int(SR * 0.16)
    out = [0.0] * n
    mix_into(out, metal(n, metal_fc * 1.1, 7, seed), 0, 0.55)
    mix_into(out, metal(n, metal_fc * 1.35, 6, seed + 2), int(SR * 0.048), 1.0)
    mix_into(out, thud(n, 120, 30, seed + 4), int(SR * 0.050), 0.35)
    return out, 0.48


def build_bolt(metal_fc, seed):
    """拉枪机：摩擦 → 硬脆撞击 → 弹簧余音"""
    n = int(SR * 0.30)
    out = [0.0] * n
    # 往后拉的那一段摩擦
    mix_into(out, scrape(n, metal_fc * 0.55, 25, 45, seed), 0, 0.5)
    # 松手，枪机回位撞击
    mix_into(out, metal(n, metal_fc * 0.95, 16, seed + 2), int(SR * 0.10), 1.0)
    mix_into(out, metal(n, metal_fc * 1.6, 9, seed + 3), int(SR * 0.10), 0.5)
    mix_into(out, thud(n, 140, 40, seed + 6), int(SR * 0.10), 0.4)
    # 弹簧余音
    mix_into(out, sine(n, metal_fc * 1.2, 90, seed + 8), int(SR * 0.105), 0.12)
    return out, 0.55


def build_trigger_click(metal_fc, seed):
    """
    空仓扣扳机：击锤落下的空响。
    比换弹的卡榫声更干、更短、更高——没有后续的弹匣动作，只有一个"嗒"。
    """
    n = int(SR * 0.07)
    out = [0.0] * n
    # 击锤/扳机
    mix_into(out, metal(n, metal_fc * 1.75, 3, seed), 0, 1.0)
    mix_into(out, metal(n, metal_fc * 0.8, 6, seed + 1), 0, 0.35)
    # 扳机复位（很轻的第二下）
    mix_into(out, metal(n, metal_fc * 1.2, 4, seed + 4), int(SR * 0.032), 0.22)
    return out, 0.30


BUILDERS = [
    ("1_release", build_release),
    ("2_magout", build_magout),
    ("3_magin", build_magin),
    ("4_seat", build_seat),
    ("5_bolt", build_bolt),
]


# ────────────────────────────── 写出 ──────────────────────────────

def write_stereo(path, left, right):
    n = max(len(left), len(right))
    left = pad(left, n)
    right = pad(right, n)

    w = wave.open(path, "wb")
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)

    buf = bytearray(n * 4)
    p = 0
    for i in range(n):
        for v in (left[i], right[i]):
            if v > 1.0: v = 1.0
            elif v < -1.0: v = -1.0
            iv = int(round(v * 32767.0))
            buf[p] = iv & 0xFF
            buf[p + 1] = (iv >> 8) & 0xFF
            p += 2

    w.writeframes(bytes(buf))
    w.close()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)

    outdir = sys.argv[1]
    metal_fc = 3200.0
    prefix = "reload"

    if "--metal" in sys.argv:
        metal_fc = float(sys.argv[sys.argv.index("--metal") + 1])
    if "--prefix" in sys.argv:
        prefix = sys.argv[sys.argv.index("--prefix") + 1]

    os.makedirs(outdir, exist_ok=True)

    # --mech：只生成空仓扣扳机的那一下（给 WeaponAudioProfile.mechanical 用）
    if "--mech" in sys.argv:
        left, target = build_trigger_click(metal_fc, seed=2000)
        right = [v * 0.85 for v in left]
        left, right = widen([v * 0.92 for v in left], right)
        left = normalize(left, target)
        right = normalize(right, target * 0.97)

        fname = f"{prefix}_mech_dryfire.wav"
        write_stereo(os.path.join(outdir, fname), left, right)
        print(f"{fname:<34}{len(left) / float(SR):>7.3f}s{target:>8.2f}")
        return

    print(f"金属基频 {metal_fc:.0f} Hz，输出到 {outdir}\n")
    print(f"{'文件':<34}{'时长':>8}{'峰值':>8}")

    for i, (name, builder) in enumerate(BUILDERS):
        left, target = builder(metal_fc, seed=1000 + i * 17)

        # 右声道用不同随机种子（避免"双单声道"听起来是贴片）
        right = [v * 0.85 for v in left]
        left, right = widen([v * 0.92 for v in left], right)

        left = normalize(left, target)
        right = normalize(right, target * 0.97)

        fname = f"{prefix}_{name}.wav"
        path = os.path.join(outdir, fname)
        write_stereo(path, left, right)

        dur = len(left) / float(SR)
        print(f"{fname:<34}{dur:>7.3f}s{target:>8.2f}")

    print("\n⚠️ 这是合成占位音效。拿到真实录音后用同名文件覆盖即可，不用改代码。")


if __name__ == "__main__":
    main()
