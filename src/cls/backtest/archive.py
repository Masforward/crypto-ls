"""存档：每次运行落盘到独立目录，含配置摘要和版本号，保证可追溯复现。"""
import datetime
import json
import os
import subprocess

import pandas as pd


def git_commit():
    """当前代码版本号（git commit hash），拿不到返回 unknown。"""
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                             text=True, check=False)
        return out.stdout.strip()[:8] if out.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def save_run(snapshots, position_snapshots, fills, config, out_root="backtest_runs"):
    """存档：独立目录（时间戳 + 配置摘要）+ 快照/持仓/成交 + 配置 + 版本号。

    返回目录路径。
    """
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    cfg_digest = hashlib_digest(config)
    run_dir = os.path.join(out_root, f"{ts}_{cfg_digest}")
    os.makedirs(run_dir, exist_ok=True)

    # 落盘三类记录
    snapshots.to_csv(os.path.join(run_dir, "snapshots.csv"), encoding="utf-8-sig")
    if fills is not None and len(fills):
        fills.to_csv(os.path.join(run_dir, "fills.csv"), encoding="utf-8-sig")
    pos_df = pd.DataFrame(position_snapshots, columns=["time", "positions"])
    pos_df.to_csv(os.path.join(run_dir, "positions.csv"), index=False, encoding="utf-8-sig")

    # 完整配置 + 版本号
    with open(os.path.join(run_dir, "config.json"), "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False, default=str)
    with open(os.path.join(run_dir, "version.txt"), "w", encoding="utf-8") as f:
        f.write(git_commit() + "\n")

    return run_dir


def hashlib_digest(config):
    """配置摘要（用于目录名，保证同名配置可辨识）。"""
    import hashlib
    s = json.dumps(config, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:8]
