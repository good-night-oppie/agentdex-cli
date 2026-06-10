import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.colors as mcolors
import numpy as np
from matplotlib.patches import FancyBboxPatch

# ── Data ──────────────────────────────────────────────────────────────────────
benchmarks = {
    "SWE-bench Verified": {
        "models": [
            "A-EVOLVE\n(Ours)",
            "Baseline\n(Opus 4.6)",
            "#11 mini-SWE\n+Opus 4.6",
        ],
        "scores": [76.8, 74.2, 75.6],
        "types":  ["ours", "baseline", "other"],
    },
    "MCP-Atlas": {
        "models": [
            "A-EVOLVE\n(Ours)",
            "Baseline\n(Opus 4.6)",
            "#2 Claude\nOpus 4.5",
            "#3 Gemini\n2.5 Pro",
        ],
        "scores": [79.4, 76.0, 62.3, 53.2],
        "types":  ["ours", "baseline", "other", "other"],
    },
    "Terminal-Bench 2.0": {
        "models": [
            "A-EVOLVE\n(Ours)",
            "Baseline\n(Opus 4.6)",
            "#7 Capy\n+Opus 4.6",
        ],
        "scores": [76.5, 63.5, 75.3],
        "types":  ["ours", "baseline", "other"],
    },
    "SkillsBench": {
        "models": [
            "A-EVOLVE\n(Ours)",
            "Baseline\n(No-skill)",
            "Self generated",
        ],  
        "scores": [34.9, 19.7, 21.6],
        "types":  ["ours", "baseline", "other"],
    },
}

rank_badges = {
    "SWE-bench Verified": "~#5",
    "MCP-Atlas": "#1",
    "Terminal-Bench 2.0": "#7",
    "SkillsBench": "#2",
}

# ── Gradient color definitions (bottom_color, top_color) ──────────────────────
GRAD_OURS     = ("#F06878", "#C01030")   # light coral → deep red (dark on top)
GRAD_BASELINE = ("#F8C0C8", "#D06070")   # pale pink → muted rose (dark on top)
GRAD_GRAYS    = [
    ("#C8C8D4", "#888898"),  # light → dark gray
    ("#D0D0DC", "#9090A0"),
    ("#D8D8E2", "#9898A8"),
    ("#E0E0E8", "#A0A0B0"),
]

def get_gradient_colors(t, comp_idx=0):
    if t == "ours":     return GRAD_OURS
    if t == "baseline": return GRAD_BASELINE
    return GRAD_GRAYS[comp_idx % len(GRAD_GRAYS)]

def label_color(t):
    if t == "ours":     return "#D02040"
    if t == "baseline": return "#D06070"
    return "#444444"

def draw_gradient_bar(ax, x_center, height, width, bottom_col, top_col, y_base=0):
    """Draw a single bar with a smooth vertical gradient."""
    n_segments = 256
    left = x_center - width / 2
    right = x_center + width / 2

    # Create a vertical gradient image
    bc = np.array(mcolors.to_rgb(bottom_col))
    tc = np.array(mcolors.to_rgb(top_col))
    gradient = np.linspace(bc, tc, n_segments).reshape(n_segments, 1, 3)

    ax.imshow(gradient, aspect="auto",
              extent=[left, right, y_base, y_base + height],
              origin="lower", zorder=3, interpolation="bicubic")

# ── Global layout constants ───────────────────────────────────────────────────
MAX_BARS = 4
BAR_WIDTH = 0.58
# total x-span for all panels is the same: [0, MAX_BARS-1] with bars at integer positions
X_SPAN = MAX_BARS - 1  # 5

fig, axes = plt.subplots(2, 2, figsize=(17, 12.5), facecolor="white")
axes = axes.flatten()

for idx, (name, data) in enumerate(benchmarks.items()):
    ax = axes[idx]
    models = data["models"]
    scores = data["scores"]
    types  = data["types"]
    n = len(models)

    # Center the bars within the fixed MAX_BARS span
    # Bars are spaced 1.0 apart, centered within [0, X_SPAN]
    total_span = (n - 1)  # spacing between first and last bar
    offset = (X_SPAN - total_span) / 2
    x = np.arange(n) + offset

    # Assign gradient colors
    comp_counter = 0
    grad_colors, lbl_colors = [], []
    for t in types:
        if t == "other":
            grad_colors.append(get_gradient_colors(t, comp_counter))
            comp_counter += 1
        else:
            grad_colors.append(get_gradient_colors(t))
        lbl_colors.append(label_color(t))

    # y-axis range
    y_min = min(scores) - 8
    y_max = max(scores) + 10
    y_base = max(0, y_min)
    ax.set_ylim(y_base, y_max)
    ax.set_xlim(-0.5, X_SPAN + 0.5)

    # Draw gradient bars
    for i, (xi, score) in enumerate(zip(x, scores)):
        bot_c, top_c = grad_colors[i]
        draw_gradient_bar(ax, xi, score - y_base, BAR_WIDTH, bot_c, top_c, y_base=y_base)

    # Score labels on top
    for i, (xi, score) in enumerate(zip(x, scores)):
        ax.text(xi, score + 0.4, f"{score}%", ha="center", va="bottom",
                fontsize=21, fontweight="bold", color=lbl_colors[i])

    # X-tick model labels
    ax.set_xticks(x)
    ax.set_xticklabels(models, fontsize=17, fontweight="bold")
    for tick_label, lc in zip(ax.get_xticklabels(), lbl_colors):
        tick_label.set_color(lc)

    # Benchmark title
    ax.set_xlabel(name, fontsize=24, fontweight="bold", labelpad=18, color="#333")

    # Rank badge
    badge = rank_badges.get(name, "")
    if badge:
        badge_color = "#D02040" if badge in ("#1", "#2") else "#666666"
        ax.text(0.97, 0.95, badge, transform=ax.transAxes, fontsize=22,
                fontweight="bold", ha="right", va="top", color=badge_color,
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                          edgecolor=badge_color, alpha=0.9, linewidth=1.5))

    # Axis styling
    ax.set_yticks([])
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color("#DDDDDD")
    ax.tick_params(bottom=False)
    ax.set_facecolor("white")
    ax.yaxis.grid(True, color="#F0F0F0", linewidth=0.5, zorder=1)

# ── Legend ─────────────────────────────────────────────────────────────────────
legend_patches = [
    mpatches.Patch(color="#E03050", label="A-EVOLVE (Ours)"),
    mpatches.Patch(color="#F0A0B0", label="Baseline (no evolution)"),
    mpatches.Patch(color="#B0B0BC", label="Leaderboard entries"),
]
fig.legend(handles=legend_patches, loc="upper center", ncol=3,
           fontsize=19, frameon=False, bbox_to_anchor=(0.5, 0.99))

plt.tight_layout(rect=[0, 0, 1, 0.95], pad=3.0)
plt.savefig("./a_evolve_benchmarks.png", dpi=200,
            bbox_inches="tight", facecolor="white")
plt.savefig("./a_evolve_benchmarks.pdf",
            bbox_inches="tight", facecolor="white")
print("Done!")
