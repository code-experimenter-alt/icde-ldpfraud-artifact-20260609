#!/usr/bin/env python3
"""Generate publication-quality PDF/PNG figures for the experiment section."""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "experiments" / "results"
RUN_ID = Path("/home/fu/current_icde_nitro_run_id.txt").read_text(encoding="utf-8").strip()
NITRO = ROOT / "experiments" / "aws_nitro" / "results" / RUN_ID
FIGURES = ROOT / "figures"

PALETTE = {
    "BRR": "#2F5D9B",
    "OUE": "#219E8C",
    "OLH": "#E28E2C",
    "NoVerify": "#7B7F86",
    "DirectAttest": "#1B9E77",
    "RejectMismatch": "#0B7285",
    "TEEOnly": "#6C9BCF",
    "AuditSlash": "#F4A261",
    "StrongDeposit": "#9B6ACD",
    "ReputationOnly": "#577590",
    "TEE-PoW": "#E76F51",
    "Deposit+PoW": "#2A9D8F",
    "accent": "#D1495B",
    "deep": "#264653",
    "gold": "#E9C46A",
}

MECH_ORDER = [
    "NoVerify",
    "DirectAttest",
    "RejectMismatch",
    "TEEOnly",
    "AuditSlash",
    "StrongDeposit",
    "ReputationOnly",
    "TEE-PoW",
    "Deposit+PoW",
]

MARKET_LINE_ORDER = ["NoVerify", "DirectAttest", "TEEOnly", "StrongDeposit", "TEE-PoW", "Deposit+PoW"]


def display_label(name: object) -> str:
    text = str(name)
    return "SealedHybrid" if text == "Deposit+PoW" else text


def setup_style() -> None:
    sns.set_theme(context="paper", style="whitegrid")
    mpl.rcParams.update(
        {
            "figure.dpi": 150,
            "savefig.dpi": 360,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "font.family": "DejaVu Sans",
            "font.size": 8.5,
            "axes.labelsize": 8.5,
            "axes.titlesize": 9.5,
            "axes.linewidth": 0.7,
            "axes.edgecolor": "#3A3A3A",
            "grid.color": "#E7E9EF",
            "grid.linewidth": 0.6,
            "legend.frameon": False,
            "legend.fontsize": 7.6,
            "xtick.labelsize": 7.8,
            "ytick.labelsize": 7.8,
        }
    )


def save(fig: plt.Figure, name: str) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / f"{name}.pdf", bbox_inches="tight")
    fig.savefig(FIGURES / f"{name}.png", bbox_inches="tight")
    plt.close(fig)


def format_axes(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(length=3, width=0.6, color="#4A4A4A")


def rows(path: str) -> pd.DataFrame:
    return pd.read_csv(RESULTS / path)


def figure_valuation() -> None:
    df = rows("valuation_curves.csv")
    mask = (
        ((df["protocol"] == "brr") & (df["domain"] == 2))
        | ((df["protocol"] == "oue") & (df["domain"] == 32))
        | ((df["protocol"] == "olh") & (df["domain"] == 1024))
    )
    df = df[(df["n"] == 100000) & mask].copy()
    df["Protocol"] = df["protocol"].map({"brr": "BRR", "oue": "OUE", "olh": "OLH"})
    df["Workload"] = df["Protocol"] + "  d=" + df["domain"].astype(str)
    colors = [PALETTE["BRR"], PALETTE["OUE"], PALETTE["OLH"]]

    fig, ax = plt.subplots(figsize=(3.45, 2.45))
    for (label, g), color in zip(df.groupby("Workload", sort=False), colors):
        ax.plot(g["epsilon_h"], g["value"], marker="o", lw=1.9, ms=4.2, color=color, label=label)
    ax.set_xscale("log", base=2)
    ax.set_xticks([0.2, 0.5, 1, 2, 4, 8])
    ax.set_xticklabels(["0.2", "0.5", "1", "2", "4", "8"])
    ax.set_xlabel(r"Realized budget $\epsilon_h$")
    ax.set_ylabel("Workload value")
    ax.set_ylim(-3, 104)
    ax.legend(loc="lower right", ncol=1)
    format_axes(ax)
    save(fig, "valuation_curves")


def figure_premium_heatmap() -> None:
    df = rows("fraud_premiums.csv")
    df = df[(df["n"] == 100000) & (df["domain"] == 32) & (df["protocol"] == "oue")]
    mat = df.pivot(index="epsilon_h", columns="epsilon_c", values="premium").reindex(index=[0.2, 0.5, 1, 2, 4, 8], columns=[0.2, 0.5, 1, 2, 4, 8])

    fig, ax = plt.subplots(figsize=(3.45, 2.75))
    cmap = sns.light_palette(PALETTE["accent"], as_cmap=True)
    sns.heatmap(mat, ax=ax, cmap=cmap, linewidths=0.7, linecolor="white", annot=True, fmt=".1f", cbar_kws={"label": "Premium"}, mask=mat.isna())
    ax.set_xlabel(r"Claimed budget $\epsilon_c$")
    ax.set_ylabel(r"Realized budget $\epsilon_h$")
    ax.set_title("OUE premium, n=100k, d=32", pad=5)
    save(fig, "fraud_premium_heatmap")


def figure_architecture() -> None:
    fig, ax = plt.subplots(figsize=(7.2, 1.9))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 2)
    ax.axis("off")
    blocks = [
        (0.25, 0.82, 1.25, 0.55, "Local record\nx", PALETTE["BRR"]),
        (2.05, 0.68, 1.85, 0.82, "TEE-sealed\nLDP oracle", PALETTE["OUE"]),
        (4.45, 0.82, 1.35, 0.55, "Seller host\nPoW", PALETTE["accent"]),
        (6.35, 0.72, 1.65, 0.74, "Market verifier\npricing", PALETTE["deep"]),
        (8.55, 0.82, 1.25, 0.55, "Buyer\nworkload", PALETTE["gold"]),
    ]
    for x, y, w, h, label, color in blocks:
        patch = mpl.patches.FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.04,rounding_size=0.06",
            facecolor=mpl.colors.to_rgba(color, 0.14),
            edgecolor=color,
            linewidth=1.25,
        )
        ax.add_patch(patch)
        ax.text(x + w / 2, y + h / 2, label, ha="center", va="center", fontsize=8.5, color="#1F2933")
    arrows = [
        (1.55, 1.08, 1.95, 1.08, "local input"),
        (3.95, 1.08, 4.35, 1.08, r"$y,u,k,\mathrm{att}$"),
        (5.85, 1.08, 6.25, 1.08, r"$\nu$"),
        (8.05, 1.08, 8.45, 1.08, "accepted reports"),
    ]
    for x1, y1, x2, y2, label in arrows:
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops={"arrowstyle": "->", "lw": 1.0, "color": "#39424E"})
        ax.text((x1 + x2) / 2, y1 + 0.18, label, ha="center", va="bottom", fontsize=7.4, color="#39424E")
    ax.text(2.98, 0.24, r"sealed: $\epsilon_h$, RNG, policy, counter", ha="center", va="center", fontsize=7.8, color="#39424E")
    ax.plot([2.98, 2.98], [0.38, 0.67], color="#9AA3AF", lw=0.8, linestyle="--")
    save(fig, "architecture_diagram")


def figure_disclosure_frontier() -> None:
    df = rows("goal0_disclosure_regimes.csv").copy()
    df["coverage_pct"] = df["ic_coverage"] * 100
    order = [
        "DirectAttest",
        "RejectMismatch",
        "StrongDeposit",
        "Deposit+PoW",
        "TEE-PoW",
        "AuditSlash",
        "ReputationOnly",
        "TEEOnly",
    ]
    df = df.set_index("regime").reindex(order).reset_index()
    fig, ax = plt.subplots(figsize=(3.55, 2.85))
    colors = [PALETTE.get(m, "#6B7280") for m in df["regime"]]
    y = np.arange(len(df))
    ax.barh(y, df["coverage_pct"], color=colors, height=0.62)
    for y, row in enumerate(df.itertuples(index=False)):
        ax.text(min(row.coverage_pct + 1.2, 96.5), y, f"{row.coverage_pct:.0f}%", va="center", fontsize=7.2)
        ax.text(2.0, y, f"{row.disclosure_bits:.1f} bits", va="center", ha="left", fontsize=6.7, color="#FFFFFF", fontweight="bold")
    ax.set_yticks(np.arange(len(df)))
    ax.set_yticklabels([display_label(m) for m in df["regime"]])
    ax.set_xlabel("IC coverage (%)")
    ax.set_xlim(0, 108)
    ax.invert_yaxis()
    ax.set_ylabel("")
    format_axes(ax)
    save(fig, "disclosure_frontier")


def figure_nitro_latency() -> None:
    df = pd.read_csv(NITRO / "nitro_measurements.csv")
    phases = pd.DataFrame(
        {
            "phase": ["Oracle", "Attestation", "Vsock", "PoW"],
            "mean_ms": [
                df["oracle_elapsed_ns"].mean() / 1e6,
                df["attestation_elapsed_ns"].mean() / 1e6,
                df["round_trip_ns"].mean() / 1e6,
                df["pow_ns"].mean() / 1e6,
            ],
            "p95_ms": [
                df["oracle_elapsed_ns"].quantile(0.95) / 1e6,
                df["attestation_elapsed_ns"].quantile(0.95) / 1e6,
                df["round_trip_ns"].quantile(0.95) / 1e6,
                df["pow_ns"].quantile(0.95) / 1e6,
            ],
        }
    )
    fig, ax = plt.subplots(figsize=(3.45, 2.45))
    colors = [PALETTE["deep"], PALETTE["OUE"], PALETTE["BRR"], PALETTE["accent"]]
    ax.bar(phases["phase"], phases["mean_ms"], color=colors, width=0.62)
    ax.scatter(phases["phase"], phases["p95_ms"], color="#111111", s=18, zorder=3, label="p95")
    for x, y in enumerate(phases["mean_ms"]):
        ax.text(x, y + (1.6 if y > 10 else 0.18), f"{y:.2f}", ha="center", va="bottom", fontsize=7)
    ax.set_ylabel("Latency (ms)")
    ax.set_ylim(0, max(phases["p95_ms"]) * 1.18)
    ax.legend(loc="upper left")
    format_axes(ax)
    save(fig, "nitro_latency")


def figure_pow_calibration() -> None:
    df = rows("goal3_pow_calibration.csv")
    fig, ax = plt.subplots(figsize=(3.45, 2.55))
    ax.plot(df["k_bits"], df["mean_ms"], marker="o", color=PALETTE["accent"], lw=1.8, label="Mean")
    ax.plot(df["k_bits"], df["p95_ms"], marker="s", color=PALETTE["deep"], lw=1.6, label="p95")
    ax.axvspan(14, 16, color=PALETTE["gold"], alpha=0.24, lw=0)
    ax.text(15, df["mean_ms"].min() * 1.7, "honest\nbaseline", ha="center", va="bottom", fontsize=7.4, color="#6B5A20")
    ax.set_yscale("log")
    ax.set_xticks([10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30])
    ax.set_xlabel("PoW difficulty k (bits)")
    ax.set_ylabel("Solve time (ms, log)")
    ax.legend(loc="upper left")
    format_axes(ax)
    save(fig, "pow_calibration")


def figure_pow_deadline() -> None:
    df = rows("goal3_deadline_acceptance.csv")
    mat = df.pivot(index="deadline_sec", columns="k_bits", values="accept_prob").sort_index(ascending=False)
    fig, ax = plt.subplots(figsize=(3.45, 2.35))
    sns.heatmap(mat, ax=ax, cmap="viridis", vmin=0, vmax=1, linewidths=0.35, linecolor="white", cbar_kws={"label": "Accept prob."})
    ax.set_xlabel("PoW difficulty k")
    ax.set_ylabel("Deadline (s)")
    save(fig, "pow_deadline_heatmap")


def figure_ic_coverage() -> None:
    df = rows("goal4_ic_summary.csv")
    df = df[df["mechanism"].isin(MECH_ORDER)]
    display = (
        df.groupby("mechanism", as_index=False)["ic_coverage"]
        .max()
        .set_index("mechanism")
        .reindex(MECH_ORDER)
    )
    fig, ax = plt.subplots(figsize=(3.65, 3.1))
    colors = [PALETTE[m] for m in display.index]
    y = np.arange(len(display))
    ax.barh(y, display["ic_coverage"] * 100, color=colors, height=0.58)
    for y, val in enumerate(display["ic_coverage"] * 100):
        ax.text(min(val + 1.2, 99.2), y, f"{val:.0f}%", va="center", fontsize=7.3)
    ax.set_yticks(np.arange(len(display)))
    ax.set_yticklabels([display_label(m) for m in display.index])
    ax.set_xlabel("Best IC coverage (%)")
    ax.set_xlim(0, 108)
    format_axes(ax)
    save(fig, "ic_coverage")

    heat = df[df["mechanism"] == "Deposit+PoW"].pivot(index="lambda", columns="deposit_multiplier", values="ic_coverage")
    fig, ax = plt.subplots(figsize=(3.45, 2.35))
    sns.heatmap(heat, ax=ax, cmap=sns.light_palette(PALETTE["OUE"], as_cmap=True), vmin=0, vmax=1, annot=True, fmt=".0%", linewidths=0.55, linecolor="white", cbar_kws={"label": "IC coverage"})
    ax.set_xlabel("Deposit multiplier")
    ax.set_ylabel(r"PoW sensitivity $\lambda$")
    save(fig, "ic_coverage_heatmap")


def figure_market_utility() -> None:
    df = rows("goal5_market_utility.csv")
    agg = df.groupby(["rho", "mechanism"], as_index=False).agg(
        buyer_utility=("buyer_utility", "mean"),
        efficiency=("efficiency", "mean"),
        accepted_fraud_rate=("accepted_fraud_rate", "mean"),
    )
    order = MARKET_LINE_ORDER
    fig, axes = plt.subplots(1, 3, figsize=(7.25, 2.25), sharex=True)
    metrics = [
        ("buyer_utility", "Buyer utility"),
        ("efficiency", "Efficiency"),
        ("accepted_fraud_rate", "Accepted fraud"),
    ]
    for ax, (metric, label) in zip(axes, metrics):
        for mech in order:
            g = agg[agg["mechanism"] == mech]
            ax.plot(g["rho"], g[metric], marker="o", lw=1.6, ms=3.5, color=PALETTE[mech], label=display_label(mech))
        ax.set_xlabel("Fraudulent seller fraction")
        ax.set_ylabel(label)
        if metric != "buyer_utility":
            ax.set_ylim(0, 1.03)
        format_axes(ax)
    axes[0].legend(loc="lower left", bbox_to_anchor=(0.0, 1.02), ncol=3, columnspacing=0.9, handletextpad=0.35)
    save(fig, "market_utility")

    rho = 0.7
    snap = (
        agg[np.isclose(agg["rho"], rho)]
        .set_index("mechanism")
        .reindex(MECH_ORDER)
        .reset_index()
    )
    snap = snap.sort_values("accepted_fraud_rate", ascending=False)
    fig, ax = plt.subplots(figsize=(3.45, 2.85))
    y = np.arange(len(snap))
    ax.barh(y, snap["accepted_fraud_rate"], color=[PALETTE[m] for m in snap["mechanism"]], height=0.62)
    ax.set_yticks(y)
    ax.set_yticklabels([display_label(m) for m in snap["mechanism"]])
    for y, row in enumerate(snap.itertuples(index=False)):
        x = max(row.accepted_fraud_rate, 0.012)
        ax.text(x + 0.014, y, f"U={row.buyer_utility:.1f}", va="center", fontsize=7.0)
    ax.set_xlabel(r"Accepted fraud at $\rho=0.7$")
    ax.set_xlim(0, 0.72)
    ax.invert_yaxis()
    format_axes(ax)
    save(fig, "market_baselines")


def figure_marketing_workloads() -> None:
    audience = rows("goal1b_audience_count.csv")
    reach = rows("goal1b_segment_reach.csv")
    conversion = rows("goal1b_conversion_sketch.csv")
    disclosure = rows("goal1b_disclosure_frontier.csv")

    bucket_order = ["head", "mid", "tail", "long-tail"]
    aud = audience.groupby(["epsilon_h", "frequency_bucket"], as_index=False)["relative_error"].mean()
    fig, ax = plt.subplots(figsize=(3.45, 2.45))
    for bucket, color in zip(bucket_order, ["#1B9E77", "#2F5D9B", "#E28E2C", "#D1495B"]):
        g = aud[aud["frequency_bucket"] == bucket]
        ax.plot(g["epsilon_h"], g["relative_error"], marker="o", lw=1.6, ms=3.7, color=color, label=bucket)
    ax.set_xscale("log", base=2)
    ax.set_xticks([0.5, 1, 2, 4, 8])
    ax.set_xticklabels(["0.5", "1", "2", "4", "8"])
    ax.set_xlabel(r"Realized budget $\epsilon_h$")
    ax.set_ylabel("Audience relative error")
    ax.legend(loc="upper right")
    format_axes(ax)
    save(fig, "marketing_audience_error")

    agg = reach.groupby(["frequency_bucket", "epsilon_h"], as_index=False)["relative_error"].mean()
    fig, ax = plt.subplots(figsize=(3.45, 2.45))
    sns.barplot(data=agg[agg["epsilon_h"].isin([1.0, 2.0, 4.0])], x="frequency_bucket", y="relative_error", hue="epsilon_h", order=bucket_order, palette=["#6C9BCF", "#219E8C", "#E9C46A"], ax=ax)
    ax.set_xlabel("Segment frequency bucket")
    ax.set_ylabel("Reach relative error")
    ax.legend(title=r"$\epsilon_h$", loc="upper left")
    format_axes(ax)
    save(fig, "marketing_reach_error")

    conv = conversion.groupby("epsilon_h", as_index=False).agg(decision_regret=("decision_regret", "mean"), top20_overlap=("top20_overlap", "mean"), buyer_utility=("buyer_utility", "mean"))
    fig, axes = plt.subplots(1, 2, figsize=(5.1, 2.25))
    axes[0].plot(conv["epsilon_h"], conv["decision_regret"], marker="o", lw=1.7, color=PALETTE["accent"])
    axes[0].set_xscale("log", base=2)
    axes[0].set_xticks([0.5, 1, 2, 4, 8])
    axes[0].set_xticklabels(["0.5", "1", "2", "4", "8"])
    axes[0].set_xlabel(r"$\epsilon_h$")
    axes[0].set_ylabel("Decision regret")
    axes[1].plot(conv["epsilon_h"], conv["top20_overlap"], marker="s", lw=1.7, color=PALETTE["deep"])
    axes[1].set_xscale("log", base=2)
    axes[1].set_xticks([0.5, 1, 2, 4, 8])
    axes[1].set_xticklabels(["0.5", "1", "2", "4", "8"])
    axes[1].set_xlabel(r"$\epsilon_h$")
    axes[1].set_ylabel("Top-20 overlap")
    axes[1].set_ylim(0, 1.02)
    for ax in axes:
        format_axes(ax)
    save(fig, "marketing_conversion_regret")

    fig, ax = plt.subplots(figsize=(3.45, 2.45))
    for row in disclosure.itertuples(index=False):
        color = PALETTE.get(row.mechanism, "#6B7280")
        ax.scatter(float(row.leakage_bits), float(row.accepted_fraud_rate), s=55, color=color, label=display_label(row.mechanism))
        ax.text(float(row.leakage_bits) + 0.035, float(row.accepted_fraud_rate) + 0.008, display_label(row.mechanism), fontsize=6.8)
    ax.set_xlabel("Budget-disclosure leakage (bits)")
    ax.set_ylabel("Accepted fraud rate")
    ax.set_xlim(1.35, 4.25)
    ax.set_ylim(-0.02, 0.50)
    format_axes(ax)
    save(fig, "marketing_disclosure_frontier")


def figure_robustness() -> None:
    df = rows("goal6_robustness.csv")
    labels = {
        "difficulty_bucket_width": "Bucket width",
        "hash_rate_cv": "Hash-rate CV",
        "verifier_cache_ttl_sec": "Cache TTL",
        "attestation_failure_prob": "Attest fail",
        "deposit_share": "Deposit share",
    }
    fig, ax = plt.subplots(figsize=(3.45, 2.65))
    palette = sns.color_palette("Set2", n_colors=df["ablation"].nunique())
    for color, (abl, g) in zip(palette, df.groupby("ablation", sort=False)):
        ax.plot(g["p95_latency_ms"], g["ic_coverage"] * 100, marker="o", lw=1.5, ms=4, color=color, label=labels.get(abl, abl))
    ax.set_xlabel("p95 latency (ms)")
    ax.set_ylabel("IC coverage (%)")
    ax.set_xlim(left=0)
    ax.set_ylim(65, 100)
    ax.legend(loc="lower right")
    format_axes(ax)
    save(fig, "robustness_ablation")


def figure_throughput_cost() -> None:
    df = rows("goal7_throughput_cost.csv")
    df["accepted_rps"] = pd.to_numeric(df["accepted_rps"])
    df["cost_per_million_usd"] = pd.to_numeric(df["cost_per_million_usd"])
    source = df.get("source", pd.Series(dtype=str)).astype(str)
    measured = source.str.startswith("measured-aws-nitro").any()
    if measured:
        phase_order = [
            "phase_direct_1m_k0",
            "phase_teeonly_1m_k0",
            "phase_teepow_250k_pow15",
            "phase_hybrid_500k_pow14",
            "phase_correctness_10k_pow15",
        ]
        labels = {
            "phase_direct_1m_k0": "Direct\n1M",
            "phase_teeonly_1m_k0": "TEEOnly\n1M",
            "phase_teepow_250k_pow15": "TEE-PoW\n250k",
            "phase_hybrid_500k_pow14": "Hybrid\n500k",
            "phase_correctness_10k_pow15": "Correct.\n10k",
        }
        df = df.copy()
        df["_order"] = df["phase"].map({name: idx for idx, name in enumerate(phase_order)}).fillna(len(phase_order))
        df = df.sort_values(["_order", "mechanism"])
        x = np.arange(len(df))
        colors = [PALETTE.get(m, PALETTE["deep"]) for m in df["mechanism"]]

        fig, axes = plt.subplots(2, 1, figsize=(3.45, 3.25), sharex=True)
        axes[0].bar(x, df["accepted_rps"], color=colors, width=0.66)
        axes[0].set_ylabel("Reports/s")
        axes[0].set_yscale("log")
        axes[1].bar(x, df["cost_per_million_usd"], color=colors, width=0.66)
        axes[1].set_ylabel("USD per million")
        axes[1].set_yscale("log")
        axes[1].set_xticks(x)
        axes[1].set_xticklabels([labels.get(p, str(p).replace("_", "\n")) for p in df["phase"]], rotation=0)
        for ax in axes:
            format_axes(ax)
        save(fig, "throughput_cost")
        return

    df = df[df["batch_size"] == 128]
    order = ["NoVerify", "DirectAttest", "TEEOnly", "TEE-PoW", "Deposit+PoW"]
    fig, axes = plt.subplots(2, 1, figsize=(3.45, 3.25), sharex=True)
    for mech in order:
        g = df[df["mechanism"] == mech]
        axes[0].plot(g["concurrency"], g["accepted_rps"], marker="o", lw=1.6, ms=3.7, color=PALETTE[mech], label=display_label(mech))
        axes[1].plot(g["concurrency"], g["cost_per_million_usd"], marker="o", lw=1.6, ms=3.7, color=PALETTE[mech], label=display_label(mech))
    axes[0].set_ylabel("Pipeline reports/s")
    axes[1].set_xlabel("Concurrency")
    axes[1].set_ylabel("USD per million")
    axes[1].set_yscale("log")
    for ax in axes:
        ax.set_xticks([1, 4, 8, 16, 32])
        format_axes(ax)
    axes[0].legend(loc="lower left", bbox_to_anchor=(0.0, 1.02), ncol=2, columnspacing=0.8, handletextpad=0.35)
    save(fig, "throughput_cost")


def figure_attacker_strategy() -> None:
    df = rows("goal8_attacker_strategies.csv")
    selected = df[(df["deposit_multiplier"] == 1.0) | (df["mechanism"].isin(["NoVerify", "DirectAttest", "TEEOnly", "ReputationOnly", "TEE-PoW"]))]
    fig, ax = plt.subplots(figsize=(3.45, 2.55))
    for mech in ["NoVerify", "DirectAttest", "TEEOnly", "ReputationOnly", "TEE-PoW", "Deposit+PoW"]:
        g = selected[selected["mechanism"] == mech]
        g = g.groupby("lambda", as_index=False)["accepted_fraud_rate"].mean()
        ax.plot(g["lambda"], g["accepted_fraud_rate"], marker="o", lw=1.6, ms=3.8, color=PALETTE[mech], label=display_label(mech))
    ax.set_xlabel(r"PoW sensitivity $\lambda$")
    ax.set_ylabel("Accepted fraud rate")
    ax.set_ylim(0, 1.0)
    ax.legend(loc="upper right")
    format_axes(ax)
    save(fig, "attacker_strategy")


def figure_replay_confusion() -> None:
    df = rows("goal8_confusion_matrix.csv")
    cols = ["full_verifier", "no_counter_check", "no_pcr_check", "no_pow_binding"]
    mat = df[cols].replace({"reject": 0, "unsupported": 0.5, "accept": 1}).to_numpy(dtype=float)
    fig, ax = plt.subplots(figsize=(3.45, 2.9))
    cmap = mpl.colors.ListedColormap(["#D1495B", "#A9ADB8", "#2A9D8F"])
    norm = mpl.colors.BoundaryNorm([-0.01, 0.25, 0.75, 1.01], cmap.N)
    ax.imshow(mat, cmap=cmap, norm=norm, aspect="auto")
    ax.set_yticks(range(len(df)))
    ax.set_yticklabels(df["case"])
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels(["Full", "No ctr", "No PCR", "No PoW"], rotation=25, ha="right")
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            label = "A" if mat[i, j] > 0.75 else ("O" if mat[i, j] > 0.25 else "R")
            ax.text(j, i, label, ha="center", va="center", color="white", fontsize=7.2, fontweight="bold")
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    save(fig, "replay_confusion")


def main() -> None:
    setup_style()
    figure_architecture()
    figure_valuation()
    figure_premium_heatmap()
    figure_disclosure_frontier()
    figure_nitro_latency()
    figure_pow_calibration()
    figure_pow_deadline()
    figure_ic_coverage()
    figure_marketing_workloads()
    figure_market_utility()
    figure_robustness()
    figure_throughput_cost()
    figure_attacker_strategy()
    figure_replay_confusion()
    print(f"Wrote PDF and PNG figures to {FIGURES}")


if __name__ == "__main__":
    main()
