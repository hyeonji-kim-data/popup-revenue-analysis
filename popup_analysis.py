"""
Global Beauty Pop-up Campaign - Statistical Validation (basic statistics)

Analysis flow
  STEP 1. Correlation      : Do footfall and revenue move together?
  STEP 2. One-way ANOVA    : Do means really differ by location and event type?
  STEP 3. Two-way ANOVA    : Is there a "location x event type" combination effect?
  STEP 4. Multiple regression : Holding other variables fixed, what drives revenue?
  STEP 5. Confidence intervals : Can the RPV ranking of combinations be trusted?

Requirements: pip install pandas numpy scipy statsmodels matplotlib
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
import statsmodels.api as sm
import statsmodels.formula.api as smf
import os

DATA_PATH = "data/popup_events_clean.csv"   # <- change to your file path
pd.set_option("display.width", 200)
# Run from this file's folder, so the paths work wherever the terminal is
os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.makedirs("figures", exist_ok=True)   # create the figures folder if missing


# ---------------------------------------
# STEP 0. Load data & derived variables
# ---------------------------------------
df = pd.read_csv(DATA_PATH)

# RPV (revenue per visitor) = revenue / total footfall over the event
# total footfall = average daily footfall x lease days (lease days = event duration)
df["rpv"] = df["revenue_usd"] / (df["avg_daily_footfall"] * df["lease_length_days"])

# Season: group the start month into seasons (used as a control variable in the regression)
month = pd.to_datetime(df["start_date"]).dt.month
df["season"] = month.map({12: "Winter", 1: "Winter", 2: "Winter",
                          3: "Spring", 4: "Spring", 5: "Spring",
                          6: "Summer", 7: "Summer", 8: "Summer",
                          9: "Fall", 10: "Fall", 11: "Fall"})

print(f"Data: {len(df)} rows")


# ---------------------------------------
# STEP 1. Correlation
# To test with numbers the assumption that "higher traffic means higher revenue".
# Correlation r ranges from -1 to 1. Close to 0 means the two variables do not move together.
# p-value < 0.05 means the relationship is unlikely to be due to chance.
# ---------------------------------------
print("\n[STEP 1] Correlation")
for col in ["avg_daily_footfall", "price_usd", "lease_length_days"]:
    r, p = stats.pearsonr(df[col], df["revenue_usd"])
    print(f"  revenue vs {col:20s}: r = {r:+.3f}, p = {p:.3f}")


# ---------------------------------------
# STEP 2. One-way ANOVA
# Why? With three or more groups, tests the hypothesis "all means are equal" in one go.
# Even if group means look different, p >= 0.05 means the gap may be due to chance.
# ---------------------------------------
def one_way_anova(y, group):
    samples = [g[y] for _, g in df.groupby(group)]
    return stats.f_oneway(*samples).pvalue

print("\n[STEP 2] One-way ANOVA p-values")
for y in ["avg_daily_footfall", "revenue_usd", "rpv", "sell_through_pct"]:
    print(f"  {y:20s} | by location p = {one_way_anova(y, 'location_type'):.4f}"
          f" | by event type p = {one_way_anova(y, 'event_type'):.4f}")

print("\nMeans by location")
print(df.groupby("location_type")[["avg_daily_footfall", "lease_length_days", "revenue_usd", "rpv"]]
        .mean().round(2).sort_values("rpv", ascending=False))
print("\nMeans by event type")
print(df.groupby("event_type")[["revenue_usd", "sell_through_pct", "units_sold"]]
        .mean().round(1).sort_values("revenue_usd", ascending=False))

# Compute the two numbers used in the conclusions
# 1) Footfall needed for similar revenue: busiest location vs. location with the highest RPV
loc_mean = df.groupby("location_type")[["avg_daily_footfall", "revenue_usd", "rpv"]].mean()
busiest = loc_mean["avg_daily_footfall"].idxmax()
best_rpv = loc_mean["rpv"].idxmax()
ratio = loc_mean.loc[busiest, "avg_daily_footfall"] / loc_mean.loc[best_rpv, "avg_daily_footfall"]
print(f"\n[Check] {busiest} has {ratio:.2f}x the footfall of {best_rpv} "
      f"(revenue: {loc_mean.loc[busiest, 'revenue_usd']:,.0f} vs {loc_mean.loc[best_rpv, 'revenue_usd']:,.0f} USD)")

# 2) Sell-through gap by event type: Flash Event vs Mall Kiosk
st = df.groupby("event_type")["sell_through_pct"].mean()
print(f"[Check] Sell-through Flash Event {st['Flash Event']:.1f}% vs Mall Kiosk {st['Mall Kiosk']:.1f}% "
      f"-> gap {st['Flash Event'] - st['Mall Kiosk']:+.1f}%p")


# ---------------------------------------
# STEP 3. Two-way ANOVA
# Why? To test the earlier claim of a "best combination (location x event type)".
# The key is the p-value of the interaction term (location:event):
#   p < 0.05  -> some combinations have a special effect of their own
#   p >= 0.05 -> no combination effect (location and event type act separately)
# ---------------------------------------
print("\n[STEP 3] Two-way ANOVA - RPV")
model_2way = smf.ols("rpv ~ C(location_type) * C(event_type)", data=df).fit()
print(sm.stats.anova_lm(model_2way, typ=2).round(4))


# ---------------------------------------
# STEP 4. Multiple regression
# Why? Comparing group means mixes in the effects of other variables
#     (e.g., expensive products may happen to be concentrated in one location).
#     Regression estimates each variable's effect while holding the others fixed.
# Interpretation:
#   - Numeric coefficient: change in revenue (USD) when the variable increases by 1
#   - Categorical coefficient: revenue difference (USD) from the reference group (Mall Kiosk)
#   - R²: share of revenue variation explained by the model
# ---------------------------------------
print("\n[STEP 4] Multiple regression - revenue")
formula = ("revenue_usd ~ price_usd + avg_daily_footfall + lease_length_days"
           " + C(event_type, Treatment('Mall Kiosk')) + C(location_type)"
           " + C(brand) + C(category) + C(region) + C(season)")
model = smf.ols(formula, data=df).fit()

# Compare with a price-only model -> how much explanatory power the other variables add
model_price_only = smf.ols("revenue_usd ~ price_usd", data=df).fit()
print(f"  Price-only model R² = {model_price_only.rsquared:.3f}")
print(f"  Full model       R² = {model.rsquared:.3f}")

# Significance of each variable group at once (p-value per variable)
print("\n  Significance by variable (p < 0.05 = affects revenue)")
print(sm.stats.anova_lm(model, typ=2)[["PR(>F)"]].round(4))

print("\n  Key coefficients (95% confidence interval)")
ci = model.conf_int()
for name in model.params.index:
    if name in ["price_usd", "avg_daily_footfall", "lease_length_days"] or "event_type" in name:
        label = name.split("T.")[-1].rstrip("]")
        print(f"  {label:22s}: {model.params[name]:>10,.0f}  "
              f"[{ci.loc[name, 0]:>10,.0f} ~ {ci.loc[name, 1]:>10,.0f}]  p = {model.pvalues[name]:.3f}")


# ---------------------------------------
# STEP 5. 95% confidence interval of mean RPV for each combination
# Even the top-ranked combination is not clearly "first" if its interval overlaps with others.
# Formula: mean ± 1.96 × standard error,  standard error = standard deviation / √n
# ---------------------------------------
print("\n[STEP 5] 95% CI of RPV by combination")
cell = (df.groupby(["location_type", "event_type"])["rpv"]
          .agg(n="count", mean="mean", sd="std").reset_index())
cell["se"] = cell["sd"] / np.sqrt(cell["n"])
cell["ci_lo"] = cell["mean"] - 1.96 * cell["se"]
cell["ci_hi"] = cell["mean"] + 1.96 * cell["se"]
cell = cell.sort_values("mean", ascending=False).reset_index(drop=True)
print(cell[["location_type", "event_type", "n", "mean", "ci_lo", "ci_hi"]].round(2).to_string())

top = cell.iloc[0]
n_overlap = (cell.loc[1:, "ci_hi"] >= top["ci_lo"]).sum()
print(f"\n  Combinations whose CI overlaps with the top combination: {n_overlap}")


# ---------------------------------------
# Visualization 
# ---------------------------------------
# Figure 1: footfall / revenue / RPV by location, side by side
loc = df.groupby("location_type")[["avg_daily_footfall", "revenue_usd", "rpv"]].mean()
loc = loc.sort_values("avg_daily_footfall")
p_foot = one_way_anova("avg_daily_footfall", "location_type")
p_rev = one_way_anova("revenue_usd", "location_type")

fig, axes = plt.subplots(1, 3, figsize=(14, 4.2), sharey=True)
panels = [("avg_daily_footfall", f"Avg daily footfall (p<0.001)", "#9aa5b1"),
          ("revenue_usd", f"Avg revenue (p={p_rev:.2f}, no difference)", "#2f6f73"),
          ("rpv", "RPV = revenue / total footfall (USD)", "#d1495b")]
for ax, (col, title, color) in zip(axes, panels):
    ax.barh(loc.index, loc[col], color=color)
    ax.set_title(title, fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
axes[1].xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v/1000:.0f}K"))
fig.suptitle("Same revenue, different footfall → RPV gap comes from footfall", fontsize=13)
plt.tight_layout()
plt.savefig("figures/fig1_location_footfall_revenue.png", dpi=200)

# Figure 2: sell-through vs revenue by event type (mean ± 95% CI)
def mean_ci(y):
    g = df.groupby("event_type")[y].agg(["mean", "std", "count"])
    g["err"] = 1.96 * g["std"] / np.sqrt(g["count"])
    return g.sort_values("mean")

fig, axes = plt.subplots(1, 2, figsize=(12, 3.8), sharey=False)
for ax, y, title, color in [
        (axes[0], "sell_through_pct",
         "Sell-through % (p<0.001)", "#2f6f73"),
        (axes[1], "revenue_usd",
         f"Revenue USD (p={one_way_anova('revenue_usd', 'event_type'):.2f}, no difference)", "#9aa5b1")]:
    g = mean_ci(y)
    ax.errorbar(g["mean"], g.index, xerr=g["err"], fmt="o", color=color, ecolor="#c9ced6", capsize=4)
    ax.set_title(title, fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
axes[1].xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v/1000:.0f}K"))
fig.suptitle("Event type changes sell-through, but not revenue (mean ± 95% CI)", fontsize=13)
plt.tight_layout()
plt.savefig("figures/fig2_event_type.png", dpi=200)

# Figure 3: mean RPV + 95% CI by combination
c = cell.sort_values("mean")
labels = c["location_type"] + " × " + c["event_type"] + "  (n=" + c["n"].astype(str) + ")"
fig, ax = plt.subplots(figsize=(8, 8))
ax.errorbar(c["mean"], labels, xerr=1.96 * c["se"], fmt="o", color="#d1495b", ecolor="#c9ced6", capsize=3)
ax.axvline(df["rpv"].mean(), color="grey", ls="--", lw=1, label="overall mean")
ax.set_xlabel("Mean RPV, USD per visitor (95% CI)")
ax.set_title("RPV by Location × Event type")
ax.legend(loc="lower right")
ax.spines[["top", "right"]].set_visible(False)
plt.tight_layout()
plt.savefig("figures/fig3_combo_rpv_ci.png", dpi=200)

print("\nFigures saved to figures/: fig1, fig2, fig3")
