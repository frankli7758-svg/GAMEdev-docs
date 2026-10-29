#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
从 Boom Library "Gun Handling (WAV)" 里切出单次操作音，转成游戏可用规格，
并直接铺成换弹分段的命名规范（扔进 Assets/Audio/Weapons/<枪>/ 就能被
`音频/③ 按目录自动填充音效数组` 认出来）。

为什么需要它：
    Gun Handling 包里每个 wav 不是"一次操作"，而是一串重复操作
    （HK G36 Mag Out 01 是 14.9 秒、里面拔了 6 次弹匣），规格 96kHz/24bit。
    游戏里要的是"一次操作一个文件"，而且要能在多个变体之间随机轮播。

和 cut_gun_sounds.py 的区别（别混用）：
    · cut_gun_sounds.py 是切**枪声**，每个片段峰值归一到 -3dBFS
    · 这个是切**操作声**，**保留整批的原始相对电平**，只做整批统一增益
      原因：真实换弹里"插弹匣"本来就比"保险开关"响得多，逐个归一化会把这个
      精心设计过的层次抹平，听起来每个动作一样重，反而假。

映射（源关键词 → 换弹动作词）：
    Mag Out          → magout  （按卡榫 + 弹匣滑出）
    Mag In           → magin   （插入 + 拍实）
    Cocking Handle   → bolt    （拉枪机，G36 的叫法）
    Charging Handle  → bolt    （同上，M16 的叫法）
    Dry Fire         → 空仓咔哒（进 mechanical 数组）
    *Unload*         → 跳过（空仓换弹专用的重拉，暂时用不上）
    Safety On Off    → 跳过（留给以后做保险开关）

输出命名（末尾一段必须是动作词，自动填充工具靠它推时间点）：
    <前缀>_reload_<slot>_v<n>_<动作>.wav
    <前缀>_mech_dryfire_v<n>.wav

用法：
    python Tools/import_gun_handling.py <源枪目录> <输出目录> <前缀> [--clean]

例：
    python Tools/import_gun_handling.py \
        "D:/Game/GAMEdev/BOOM Library Gun Handling (WAV)/HK G36" \
        "D:/Game/GAMEdev/ZombieExtraction/Assets/Audio/Weapons/G36C" g36 --clean
"""

import os
import sys
import glob
import math
import importlib.util

# 复用切枪声那套读取 / 降采样 / 包络检测，避免两份实现漂移
_spec = importlib.util.spec_from_file_location(
    "cg", os.path.join(os.path.dirname(os.path.abspath(__file__)), "cut_gun_sounds.py"))
cg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cg)

TARGET_SR = 48000
BATCH_PEAK = 0.891      # -1 dBFS，整批统一提到这里，相对关系不动

# 段峰值低于本文件最大峰值的这个比例就丢弃（0.22 ≈ -13 dB）
MIN_PEAK_RATIO = 0.22

# 同一动作的多个变体之间，低于"该动作最响那个"的这个比例也丢弃（0.5 ≈ -6 dB）
#
# 为什么需要这一层：同一把枪的 Mag Out 录了好几次，力度本来会有差异，
# 但 BOOM 这批录素材里有的次数明显偏轻（实测 G36 的三个 Mag Out 是
# -7.6 / -16.7 / -15.2 dB，相差 14 dB）。做进游戏后随机轮播就是
# "有时咔一声、有时几乎没声"，玩家会觉得音效坏了。
# 真实人手重复同一个动作不会差 14 dB，所以过轻的那几条本来就是废素材。
GROUP_PEAK_RATIO = 0.5

# 每段最长时长（毫秒）。
#
# ⚠️ 不要随手改成 300 这种值（2026-10-27 20:25 试过，失败）：
# 这批操作声的**重音在后段** —— "Mag In" 是「插入的咚」+「拍实到位的咔」两声，
# 最响的那声在 0.3~0.4 秒处。把每段硬裁到 280ms 会把重音切掉，
# 实测 g36_reload_3_v1_magin 从 -3.8 dB 掉到 -15.9 dB，听起来变成一声闷响。
#
# 所以这里只设一个"防呆上限"，避免把下一段操作吃进来。真正的时长匹配
# 由「换弹时长 vs 时间点」解决（见 WeaponAudioFiller.ReloadTiming 的注释）。
MAX_CLIP_MS = 800

# (源文件名关键词, 必须排除的词, 动作词, 换弹 slot, 每个动作取几段)
RULES = [
    ("Mag Out",         None,     "magout",  2, 3),
    ("Mag In",          None,     "magin",   3, 3),
    ("Cocking Handle",  "Unload", "bolt",    5, 3),
    ("Charging Handle", "Unload", "bolt",    5, 3),
]

DRY_FIRE_KEYWORD = "Dry Fire"


def pick_source(folder, keyword, exclude):
    """同一条规则可能匹配到 01 / 02 两个文件：优先立体声（02），没有就用第一个"""
    hits = []
    for f in glob.glob(os.path.join(folder, "*.wav")):
        name = os.path.basename(f)
        if keyword.lower() not in name.lower():
            continue
        if exclude and exclude.lower() in name.lower():
            continue
        hits.append(f)

    if not hits:
        return None

    stereo = [f for f in hits if " 02" in os.path.basename(f)]
    return sorted(stereo or hits)[0]


def detect_regions(path, threshold=0.04, min_ms=70):
    """读一个文件，返回 (降采样后的声道数据, 采样率, 每个操作段的峰值列表)

    min_ms 是可调的：拔弹匣、拉枪机是几百毫秒的连续动作，用 70ms 过滤毛刺正好；
    但 Dry Fire（空击发）本身只有 40~60ms，用 70ms 会把它们全丢掉。
    """
    chans, sr, _ = cg.read_wav_24(path)
    chans, sr = cg.downsample(chans, sr, TARGET_SR)

    env, blk = cg.envelope(chans, sr)
    if not env:
        return chans, sr, []

    regions = cg.find_regions(env, blk, sr, threshold_ratio=threshold, merge_ms=300, min_ms=min_ms)

    scored = []
    for a, b in regions:
        seg = [c[a:b] for c in chans]
        peak = 0.0
        for c in seg:
            if len(c) == 0:
                continue
            m = max(abs(v) for v in c)
            if m > peak:
                peak = m
        scored.append({"start": a, "end": b, "peak": peak})

    return chans, sr, scored


def slice_region(chans, sr, start, end, pre_ms=15, tail_ms=200, max_ms=MAX_CLIP_MS,
                 fade_in_ms=5, fade_out_ms=20):
    """切一段，前后留余量。**不做归一化** —— 电平统一交给整批增益处理

    首尾各加一小段淡入淡出：
      · 淡入：包络检测的起点可能落在一个还在响的位置（实测 m4_reload_5_v2_bolt
        起点就有 -33 dB 的能量），直接切会"啪"一声
      · 淡出：正常情况尾音是自然衰减的，这一步是保险
    """
    a = max(0, start - int(sr * pre_ms / 1000.0))
    b = min(len(chans[0]), end + int(sr * tail_ms / 1000.0))

    limit = int(sr * max_ms / 1000.0)
    if b - a > limit:
        b = a + limit

    out = [c[a:b] for c in chans]
    n = len(out[0]) if out else 0

    if n > 0:
        fi = min(n, int(sr * fade_in_ms / 1000.0))
        fo = min(n, int(sr * fade_out_ms / 1000.0))

        for c in out:
            for i in range(fi):
                c[i] *= i / fi
            for i in range(fo):
                c[n - 1 - i] *= i / fo

    return out, (b - a) / float(sr)


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        raise SystemExit(1)

    src_dir, out_dir, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    clean = "--clean" in sys.argv

    if not os.path.isdir(src_dir):
        raise SystemExit("找不到源目录：" + src_dir)

    os.makedirs(out_dir, exist_ok=True)

    # ── 1. 收集要切的东西 ──
    # (动作词, slot, 每个动作取几段, 源文件, 归类, min_ms, tail_ms)
    jobs = []

    for keyword, exclude, action, slot, per_action in RULES:
        source = pick_source(src_dir, keyword, exclude)
        if not source:
            continue
        jobs.append((action, slot, per_action, source, "reload", 70, 200))

    dry = pick_source(src_dir, DRY_FIRE_KEYWORD, None)
    if dry:
        # 空击发只有 40~60ms：最短时长必须放宽到 20ms，否则全被当毛刺丢掉
        jobs.append(("dryfire", 0, 3, dry, "mech", 20, 120))

    if not jobs:
        raise SystemExit("一条规则都没匹配上，检查目录是不是 Gun Handling 的结构")

    # ── 2. 逐个切，先都留在内存里（要等全局峰值算增益）──
    pieces = []        # (输出文件名, 声道数据)

    for action, slot, count, source, kind, min_ms, tail_ms in jobs:
        name = os.path.basename(source)
        print(f"\n读入：{name}")
        chans, sr, regions = detect_regions(source, min_ms=min_ms)
        print(f"  时长 {len(chans[0]) / sr:.1f}s，检测到 {len(regions)} 段")

        if not regions:
            print("  ⚠ 一段都没切出来，跳过")
            continue

        # 丢掉电平过低的段：它们要么是母带里的杂音（手碰枪、衣料摩擦），
        # 要么是"一次操作被包络低谷劈成两半"的后半截。
        # 判定用**相对本文件最大峰值的比例**，因为不同枪、不同动作的绝对电平本来就不同。
        file_max = max(r["peak"] for r in regions)
        usable = [r for r in regions if r["peak"] >= file_max * MIN_PEAK_RATIO]

        if len(usable) < len(regions):
            print(f"  丢弃 {len(regions) - len(usable)} 段电平过低的（杂音或切坏的一半）")
        if not usable:
            usable = regions

        # 按峰值降序挑最完整的几段
        picked = sorted(usable, key=lambda r: r["peak"], reverse=True)[:count]

        # 再滤掉组内明显偏轻的（见 GROUP_PEAK_RATIO 的说明）。
        # 放在"挑前 N 段"之后：先保证挑到的是完整操作，再保证它们电平接近。
        if picked:
            group_max = picked[0]["peak"]
            before = len(picked)
            picked = [r for r in picked if r["peak"] >= group_max * GROUP_PEAK_RATIO]
            if len(picked) < before:
                print(f"  组内丢弃 {before - len(picked)} 段（比同组最响的轻 {-20 * math.log10(GROUP_PEAK_RATIO):.0f} dB 以上）")

        picked.sort(key=lambda r: r["start"])

        for i, r in enumerate(picked, 1):
            data, dur = slice_region(chans, sr, r["start"], r["end"], tail_ms=tail_ms)

            if kind == "reload":
                fname = f"{prefix}_reload_{slot}_v{i}_{action}.wav"
            else:
                fname = f"{prefix}_mech_{action}_v{i}.wav"

            pieces.append((fname, data, dur, r["peak"]))

    if not pieces:
        raise SystemExit("什么都没切出来")

    # ── 3. 整批统一增益（保住相对电平）──
    batch_max = max(p[3] for p in pieces)
    gain = (BATCH_PEAK / batch_max) if batch_max > 0 else 1.0
    print(f"\n整批最大峰值 {batch_max:.3f} → 增益 ×{gain:.2f}"
          f"（{20 * math.log10(gain):+.1f} dB，相对关系保留）")

    # ── 4. 清掉同前缀的旧文件（合成的占位换弹声就在里面）──
    if clean:
        removed = 0
        for pattern in (f"{prefix}_reload_*.wav", f"{prefix}_mech_*.wav"):
            for old in glob.glob(os.path.join(out_dir, pattern)):
                os.remove(old)
                removed += 1
        if removed:
            print(f"已清理 {removed} 个旧的换弹 / 机械声文件")

    # ── 5. 写盘 ──
    print(f"\n{'时长':>7}  文件")
    for fname, data, dur, peak in pieces:
        scaled = [[v * gain for v in c] for c in data]
        cg.write_wav_16(os.path.join(out_dir, fname), scaled, TARGET_SR)
        print(f"{dur:>6.2f}s  {fname}")

    print(f"\n已写入：{out_dir}")
    print("下一步：Unity 里等导入，然后跑『音频 / ③ 按目录自动填充音效数组』。")


if __name__ == "__main__":
    main()
