"""Round and end-of-game reports for the Hallertau automa app.

Probabilities come from the last test runs: `test_run.py --games N` writes
output/test_stats.json with the score distribution per difficulty level (final
and after every round). The reports compare each automa with those numbers.
"""

import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from generate_cards import ROMAN

STATS_PATH = Path(__file__).resolve().parent.parent / "output" / "test_stats.json"

ACTUAL_COLOR = "#2F6FB0"   # the automa's own line
EXPECTED_COLOR = "#8A8A8A"  # test-run median and band


@st.cache_data
def _read_stats(path, mtime):
    return json.loads(Path(path).read_text())


def load_stats():
    """Statistics of the last test runs, or None if test_run.py was not run yet."""
    if not STATS_PATH.is_file():
        return None
    return _read_stats(str(STATS_PATH), STATS_PATH.stat().st_mtime)


def stats_caption(stats, config, bonuses=None):
    if stats is None:
        return ("No test statistics yet - run `test_run.py --games 2000` to get the "
                "expected ranges in these reports.")
    text = (f"Expected ranges from the last test runs: {stats['games']} simulated games "
            f"with {stats['automas']} automas ({stats['created'].replace('T', ' ')}).")
    if (stats.get("tools_rule"), stats.get("tools_space_mode")) != \
            (config["tools_rule"], config.get("tools_space_mode")):
        text += " The rules changed since then - run the test again."
    elif bonuses is not None and stats.get("bonuses", True) != bonuses:
        text += (" The test runs were " + ("with" if stats.get("bonuses", True)
                                           else "without")
                 + " bonuses, this game is " + ("with" if bonuses else "without")
                 + " - the expected ranges differ slightly.")
    return text


def expected(stats, level, round_idx):
    """(p5, median, p95) of the running score after a round, or None."""
    if stats is None:
        return None
    s = stats["rounds"][round_idx]["score"].get(level)
    return (s["p5"], s["p50"], s["p95"]) if s else None


def share_below(stats, level, score):
    """Share of the test games in which the automa scored less than `score`."""
    q = stats["final"][level]["quantiles"]
    return sum(v < score for v in q) / len(q)


def _position(value, band):
    if band is None:
        return ""
    lo, _, hi = band
    return "below" if value < lo else "above" if value > hi else "on track"


# --------------------------------------------------------------------------
# Round report
# --------------------------------------------------------------------------

def round_report(automas, round_idx, stats, config, bonuses=False):
    """Resources and points of every automa at the end of a round."""
    rows = []
    for i, a in enumerate(automas):
        h = a["history"][round_idx]
        band = expected(stats, a["level"], round_idx)
        rows.append({
            "Automa": f"Automa {i + 1}",
            "Difficulty": a["level"].title(),
            "Workers": f"{h['start_workers']} → {h['end_workers']}",
            "Cards played": h["plays"],
            "Sheep": f"{h['total_sheep']} (+{h['sheep']})",
            "Tools": f"{h['total_tools']} (+{h['tools']})",
            "Cards": f"{h['total_cards']} (+{h['cards']})",
            **({"Bonuses": f"{h['total_bonuses']} (+{h['bonuses']})"} if bonuses else {}),
            "Points": h["points"],
            "Expected (test runs)": (f"{band[0]}–{band[2]} (median {band[1]})"
                                     if band else "–"),
            "Position": _position(h["points"], band),
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption("Sheep, tools, cards" + (" and bonuses" if bonuses else "")
               + ": total (+ this round). Expected: 90% of the test games had a score "
               "in this range after this round. " + stats_caption(stats, config, bonuses))


# --------------------------------------------------------------------------
# End of game report
# --------------------------------------------------------------------------

def _points_chart(a, stats, rounds):
    """Running score per round against the test-run median and 90% band."""
    rows = []
    for r in range(rounds):
        band = expected(stats, a["level"], r)
        rows.append({"Round": ROMAN[r], "order": r, "Points": a["history"][r]["points"],
                     "p5": band[0] if band else None, "Median": band[1] if band else None,
                     "p95": band[2] if band else None})
    df = pd.DataFrame(rows)
    x = alt.X("Round:N", sort=[ROMAN[r] for r in range(rounds)], title=None,
              axis=alt.Axis(labelAngle=0))
    y_title = "Points (running total)"
    actual = alt.Chart(df).mark_line(color=ACTUAL_COLOR, strokeWidth=2,
                                     point=alt.OverlayMarkDef(size=64, filled=True,
                                                              color=ACTUAL_COLOR))
    actual = actual.encode(x=x, y=alt.Y("Points:Q", title=y_title),
                           tooltip=["Round", "Points", "Median", "p5", "p95"])
    layers = [actual]
    if stats is not None:
        band = alt.Chart(df).mark_area(color=EXPECTED_COLOR, opacity=0.18).encode(
            x=x, y=alt.Y("p5:Q", title=y_title), y2="p95:Q")
        median = alt.Chart(df).mark_line(color=EXPECTED_COLOR, strokeWidth=2,
                                         strokeDash=[4, 4]).encode(x=x, y="Median:Q")
        layers = [band, median, actual]
    return alt.layer(*layers).properties(height=220)


def final_report(automas, stats, config, levels, bonuses=False):
    rounds = config["rounds"]
    st.header("End of game")
    st.caption(("Played with bonuses. " if bonuses else "Played without bonuses. ")
               + stats_caption(stats, config, bonuses))

    # Final score per automa with its breakdown and analysis.
    cols = st.columns(len(automas))
    for i, (col, a) in enumerate(zip(cols, automas)):
        lv = levels[a["level"]]
        total = a["history"][-1]["points"]
        with col, st.container(border=True):
            st.subheader(f"Automa {i + 1}")
            st.badge(a["level"].title(), color="blue")
            st.metric("Final score", total)
            st.table(pd.DataFrame([
                {"": "Sheep", "Count": a["sheep"], "x": lv["sheep"],
                 "Points": a["sheep"] * lv["sheep"]},
                {"": "Tools", "Count": a["tools"], "x": lv["tool"],
                 "Points": a["tools"] * lv["tool"]},
                {"": "Cards", "Count": a["cards"], "x": lv["card"],
                 "Points": a["cards"] * lv["card"]},
            ] + ([{"": "Bonuses", "Count": a["bonuses"], "x": lv.get("bonus", 0),
                   "Points": a["bonuses"] * lv.get("bonus", 0)}] if bonuses else [])
            ).set_index(""))
            target = lv.get("target")
            if target:
                inside = target[0] <= total <= target[1]
                st.markdown(f"Target {target[0]}–{target[1]}: "
                            + (":green-badge[:material/check: within]" if inside else
                               ":orange-badge[:material/warning: below]"
                               if total < target[0] else
                               ":orange-badge[:material/warning: above]"))
            if stats is not None and a["level"] in stats["final"]:
                f = stats["final"][a["level"]]
                st.markdown(
                    f"Scored more than **{share_below(stats, a['level'], total):.0%}** of "
                    f"the test games at this level (test average {f['mean']:.0f}, median "
                    f"{f['quantiles'][50]}, 90% between {f['quantiles'][5]} and "
                    f"{f['quantiles'][95]}).")
                if f.get("in_target") is not None:
                    st.caption(f"In the test runs {f['in_target']:.0%} of the games at "
                               f"this level ended within the target.")

    # Points per round against the test runs.
    st.subheader("Points per round")
    cols = st.columns(len(automas))
    for i, (col, a) in enumerate(zip(cols, automas)):
        with col:
            st.markdown(f"**Automa {i + 1}** · {a['level'].title()}")
            st.altair_chart(_points_chart(a, stats, rounds), width="stretch")
    st.caption("Solid line: the automa's running score. Dashed line and shaded band: "
               "median and 90% range of the test games at the same difficulty.")

    # Resources and points per round.
    st.subheader("Resources and points per round")
    rows = []
    for i, a in enumerate(automas):
        for h in a["history"]:
            band = expected(stats, a["level"], h["round"])
            rows.append({
                "Automa": f"Automa {i + 1}", "Round": ROMAN[h["round"]],
                "Workers": f"{h['start_workers']} → {h['end_workers']}",
                "Cards played": h["plays"], "Workers placed": h["placed"],
                "Sheep": h["sheep"], "Tools": h["tools"], "Cards": h["cards"],
                "Total sheep": h["total_sheep"], "Total tools": h["total_tools"],
                "Total cards": h["total_cards"],
                **({"Bonuses": h["bonuses"], "Total bonuses": h["total_bonuses"]}
                   if bonuses else {}),
                "Points": h["points"],
                "Expected": f"{band[0]}–{band[2]}" if band else "–",
            })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
