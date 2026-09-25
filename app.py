"""Streamlit companion app for the Hallertau automa.

Run with:  streamlit run app/app.py   (or `streamlit run app.py` inside app/)

The app is self-contained: the deck, config and test statistics are in data/,
the icons in images/ (copies made by `python sync_app.py` in the project).

Pick the number of automas and a difficulty per automa in the sidebar;
changing them starts a new game (after a confirmation while a game is running).
Each automa gets its own shuffled deck (specs/cards.csv). The next card is
drawn face down; click it to reveal it. Per card the player plays it with 1, 2
or 3 workers, takes tools when a tools row cannot be activated, or discards it.
At the end of every round and of the game the app shows a report compared with
the last test runs (output/test_stats.json).
"""

import base64
import json
import random

import streamlit as st

import reports
from card_component import automa_card
from deck import APP_DIR, ROMAN, load_config, load_deck

CONFIG = load_config()
DECK = load_deck(CONFIG)
ROUNDS = CONFIG["rounds"]
START_WORKERS = CONFIG["start_workers"]
MAX_WORKERS = CONFIG["max_workers_after_round"]
TOOLS_RULE = CONFIG["tools_rule"]
LEVELS = CONFIG["levels"]  # end of game points for sheep, tools and cards per level
MAX_AUTOMAS = 4  # 3 for play, 4 to test the automa scoring

st.set_page_config(page_title="Hallertau automa", page_icon=":material/agriculture:",
                   layout="wide")


# --------------------------------------------------------------------------
# Game logic (session state callbacks)
# --------------------------------------------------------------------------

def new_automa(level):
    draw = DECK[:]
    random.shuffle(draw)
    a = {"level": level, "draw": draw, "discard": [], "current": None,
         "workers": START_WORKERS, "available": START_WORKERS, "sheep": 0, "tools": 0,
         "cards": 0, "bonuses": 0, "log": [], "draws": 0, "revealed": False,
         "history": []}
    start_round_stats(a)
    draw_next(a, reveal=False)
    return a


def new_game(n, levels, bonuses):
    st.session_state.automas = [new_automa(levels[i]) for i in range(n)]
    st.session_state.bonuses = bonuses
    st.session_state.round = 1
    # Index of the automa holding the first player token; None = a human player.
    st.session_state.first_player = None
    st.session_state.settings = {"n": n, "levels": list(levels[:n]),
                                 "bonuses": bonuses}
    st.session_state.started = False
    st.session_state.game_over = False
    st.session_state.report_round = None


def start_round_stats(a):
    a["round_stats"] = {"start_workers": a["workers"], "plays": 0, "placed": 0,
                        "gained": 0, "sheep": 0, "tools": 0, "cards": 0,
                        "bonuses": 0}


def score(a):
    """End-of-game points at the automa's difficulty (bonuses only if enabled)."""
    lv = LEVELS[a["level"]]
    return (a["sheep"] * lv["sheep"] + a["tools"] * lv["tool"] + a["cards"] * lv["card"]
            + (a["bonuses"] * lv.get("bonus", 0) if st.session_state.bonuses else 0))


def draw_next(a, reveal):
    """Draw the next card; face down (reveal=False) hides the automa's next move."""
    if a["current"] is not None:
        a["discard"].append(a["current"])
    if not a["draw"]:
        a["draw"], a["discard"] = a["discard"], []
        random.shuffle(a["draw"])
        a["log"].append("Deck reshuffled.")
    a["current"] = a["draw"].pop()
    a["draws"] += 1
    a["revealed"] = reveal


def finish_turn(a):
    """After a play or tools: next card face down, or done for the round."""
    if a["available"] > 0:
        draw_next(a, reveal=False)
    else:
        a["discard"].append(a["current"])
        a["current"] = None


def discard(i):
    st.session_state.started = True
    # The automa is still looking for its action: show the next card directly.
    draw_next(st.session_state.automas[i], reveal=True)


def reveal(i):
    st.session_state.started = True
    st.session_state.automas[i]["revealed"] = True


def play(i, workers):
    st.session_state.started = True
    a = st.session_state.automas[i]
    rs = a["round_stats"]
    r = st.session_state.round - 1
    card = a["current"]
    a["available"] -= workers
    sheep = card["sheep"][r]
    a["sheep"] += sheep
    rs["plays"] += 1
    rs["placed"] += workers
    rs["sheep"] += sheep
    msg = f"Placed {workers} on {card['action']}. {card['name']}, +{sheep} sheep."
    if card["worker"]:
        if a["workers"] < MAX_WORKERS[r]:
            a["workers"] += 1
            rs["gained"] += 1
            msg += " Gained a worker."
        elif st.session_state.bonuses:
            a["bonuses"] += 1
            rs["bonuses"] += 1
            msg += " Already at max workers: +1 bonus."
        else:
            msg += " Already at max workers: the worker is lost."
    max_cost = card["areas"][r]
    if TOOLS_RULE in ("on_play", "both") and card["tools"][r]:
        a["tools"] += max_cost
        rs["tools"] += max_cost
        msg += f" +{max_cost} tools."
    if card["first_player"]:
        take_first_player(i)
        a["cards"] += 1
        rs["cards"] += 1
        msg += f" Took the first player token and a {card['name'].lower()}."
    a["log"].append(msg)
    finish_turn(a)


def take_tools(i, out_of_workers):
    """Tools row not activated: take tools = max cost, the turn is over.

    The automa loses as many workers as tools it gets (all it has if fewer).
    """
    st.session_state.started = True
    a = st.session_state.automas[i]
    card = a["current"]
    n = card["areas"][st.session_state.round - 1]
    a["tools"] += n
    a["round_stats"]["tools"] += n
    paid = a["available"] if out_of_workers else min(n, a["available"])
    a["available"] -= paid
    why = "Not enough workers for" if out_of_workers else "Not activated:"
    a["log"].append(f"{why} {card['action']}. {card['name']}: took {n} tools and lost "
                    f"{paid} workers.")
    finish_turn(a)


def take_first_player(i):
    prev = st.session_state.first_player
    if prev is not None and prev != i:
        st.session_state.automas[prev]["log"].append(
            f"Lost the first player token to automa {i + 1}.")
    st.session_state.first_player = i


def lose_first_player(i):
    st.session_state.started = True
    st.session_state.first_player = None
    st.session_state.automas[i]["log"].append(
        "Lost the first player token to a human player.")


def record_round():
    """Store what every automa did this round (for the reports)."""
    r = st.session_state.round - 1
    for a in st.session_state.automas:
        a["history"].append({**a["round_stats"], "round": r, "end_workers": a["workers"],
                             "total_sheep": a["sheep"], "total_tools": a["tools"],
                             "total_cards": a["cards"], "total_bonuses": a["bonuses"],
                             "points": score(a)})
    st.session_state.report_round = r


def end_round():
    st.session_state.started = True
    record_round()
    st.session_state.round += 1
    for a in st.session_state.automas:
        a["available"] = a["workers"]
        start_round_stats(a)
        a["log"].append(f"Round {ROMAN[st.session_state.round - 1]} starts.")
        if a["current"] is None:
            draw_next(a, reveal=False)


def end_game():
    record_round()
    st.session_state.game_over = True


def hide_report():
    st.session_state.report_round = None


# --- Sidebar options: changing them starts a new game -----------------------

def remember_levels():
    """Copy the difficulty widgets into level_prefs.

    Streamlit drops the state of widgets that are not shown (e.g. automa 2's
    difficulty while only 1 automa is selected), so the choices are kept here.
    """
    for i in range(MAX_AUTOMAS):
        if f"opt_level_{i}" in st.session_state:
            st.session_state.level_prefs[i] = st.session_state[f"opt_level_{i}"]


def chosen_options():
    remember_levels()
    n = st.session_state.opt_n
    return n, st.session_state.level_prefs[:n], st.session_state.opt_bonuses


def apply_options():
    st.session_state.confirm_new_game = False
    new_game(*chosen_options())


def options_changed():
    if st.session_state.started and not st.session_state.game_over:
        st.session_state.confirm_new_game = True
    else:
        apply_options()


def keep_current_game():
    """Cancel: put the sidebar options back to the running game's settings."""
    s = st.session_state.settings
    st.session_state.opt_n = s["n"]
    st.session_state.opt_bonuses = s["bonuses"]
    for i, level in enumerate(s["levels"]):
        st.session_state[f"opt_level_{i}"] = level
        st.session_state.level_prefs[i] = level
    st.session_state.confirm_new_game = False


@st.dialog("Start a new game?", dismissible=False)
def confirm_new_game():
    st.write("A game is running. Starting a new game with the new options ends it; "
             "its progress is lost.")
    with st.container(horizontal=True):
        st.button("Start new game", type="primary", on_click=apply_options,
                  icon=":material/casino:")
        st.button("Keep current game", on_click=keep_current_game)
    if not st.session_state.confirm_new_game:
        st.rerun()


# --- Session state initialisation -------------------------------------------

st.session_state.setdefault("opt_n", 1)
st.session_state.setdefault("opt_bonuses", CONFIG.get("bonuses", True))
st.session_state.setdefault("level_prefs", ["medium"] * MAX_AUTOMAS)
st.session_state.setdefault("confirm_new_game", False)

DECK_VERSION = hash(json.dumps([DECK, LEVELS, TOOLS_RULE], sort_keys=True))
if st.session_state.get("deck_version") != DECK_VERSION:
    # First visit, or the cards/config changed while the app was running.
    st.session_state.deck_version = DECK_VERSION
    new_game(*chosen_options())


# --------------------------------------------------------------------------
# Card rendering
# --------------------------------------------------------------------------

def svg_img(svg, width, height):
    """Inline SVG as <img> (st.html's sanitizer strips raw <svg> elements)."""
    data = base64.b64encode(svg.encode()).decode()
    return (f'<img src="data:image/svg+xml;base64,{data}" width="{width}" '
            f'height="{height}" alt="">')


CUBE_IMG = svg_img(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="-11 -11 22 22" '
    'stroke="#2B2118" stroke-width=".8" stroke-linejoin="round">'
    '<path d="M0 -10 L9 -5 L0 0 L-9 -5 Z" fill="#fff"/>'
    '<path d="M-9 -5 L0 0 L0 10 L-9 5 Z" fill="#E4DCCB"/>'
    '<path d="M9 -5 L0 0 L0 10 L9 5 Z" fill="#C9BEA8"/></svg>', 26, 26)


SHEEP_IMG = svg_img(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="-6 -5.5 12 10.5">'
    '<g stroke="#2B2118" stroke-width=".9" stroke-linecap="round">'
    '<line x1="-2.4" y1="1.5" x2="-2.4" y2="4.4"/>'
    '<line x1="1.2" y1="1.5" x2="1.2" y2="4.4"/></g>'
    '<g fill="#fff" stroke="#2B2118" stroke-width=".35">'
    '<circle cx="-3" cy="-.6" r="2.2"/><circle cx="-.8" cy="-1.9" r="2.3"/>'
    '<circle cx="1.5" cy="-1.2" r="2.2"/><circle cx="-1.2" cy=".9" r="2.3"/>'
    '<circle cx="1" cy="1" r="2.2"/><circle cx="-3.2" cy="1.1" r="1.9"/></g>'
    '<g fill="#fff"><circle cx="-3" cy="-.6" r="1.9"/><circle cx="-.8" cy="-1.9" r="2"/>'
    '<circle cx="1.5" cy="-1.2" r="1.9"/><circle cx="-1.2" cy=".9" r="2"/>'
    '<circle cx="1" cy="1" r="1.9"/><circle cx="-3.2" cy="1.1" r="1.6"/></g>'
    '<g fill="#2B2118"><ellipse cx="3.8" cy="-.4" rx="1.2" ry="1.8"/>'
    '<ellipse cx="2.7" cy="-1.7" rx=".7" ry=".5"/></g></svg>', 26, 23)


@st.cache_data
def image_tag(rel_path, css_class=""):
    """Local image as <img> with a data URI (works inside the component)."""
    path = APP_DIR / rel_path
    if not path.is_file():
        return ""
    data = base64.b64encode(path.read_bytes()).decode()
    return (f'<img class="{css_class}" src="data:image/{path.suffix[1:]};base64,{data}" '
            f'alt="">')


def pawn_img(color):
    return svg_img(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 14 18" fill="{color}">'
        f'<circle cx="7" cy="5" r="4"/><rect x="1" y="9" width="12" height="9" '
        f'rx="3"/></svg>', 14, 18)


def card_html(card, round_idx):
    quad = CONFIG["quadrants"][card["quadrant"]]
    icon = image_tag(quad.get("icon", "")) or card["quadrant"]
    rows = []
    for r, cost in enumerate(card["areas"]):
        classes = "hc-row" + (" off" if cost is None else "") + \
                  (" now" if r == round_idx else "")
        body = ('<span class="hc-label">no action - draw next card</span>'
                if cost is None else
                f'<span class="hc-pawns" title="max cost {cost}">'
                f'{pawn_img(quad["color"]) * cost}</span>'
                + (f'<span class="hc-tool" title="tools if not activated">'
                   f'{image_tag("images/tools.png", "hc-tool-img")}</span>'
                   if card["tools"][r] else "")
                + f'<span class="hc-sheep" title="{card["sheep"][r]} sheep">'
                f'{SHEEP_IMG * card["sheep"][r]}</span>')
        rows.append(f'<div class="{classes}"><span class="hc-round">{ROMAN[r]}</span>'
                    f'{body}</div>')
    return (
        f'<div class="hc-card" style="--q:{quad["color"]}">'
        f'<div class="hc-head">'
        f'<span class="hc-name">{card["name"]}</span>'
        f'<span class="hc-cube">{CUBE_IMG if card["worker"] else ""}</span>'
        f'<span class="hc-quad"><span class="hc-quad-icon">{icon}</span></span></div>'
        f'{"".join(rows)}'
        f'<div class="hc-foot"><span>Hallertau Automa</span>'
        f'<span>{card["id"]} &nbsp; {card["number"]:02d}/{len(DECK)}</span></div>'
        f'</div>')


# --------------------------------------------------------------------------
# Automa panel
# --------------------------------------------------------------------------

def show_automa(i, a, round_idx):
    lv = LEVELS[a["level"]]
    with st.container(horizontal=True, vertical_alignment="center"):
        st.subheader(f"Automa {i + 1}")
        st.badge(a["level"].title(), color="blue")
    with st.container(horizontal=True):
        st.metric("Available", a["available"], border=True)
        st.metric("Workers", f"{a['workers']} / {MAX_WORKERS[round_idx]}", border=True,
                  help="Owned workers / max at the end of this round")
        st.metric("Points", score(a), border=True,
                  help=f"{a['level'].title()}: {a['sheep']} sheep x {lv['sheep']} + "
                       f"{a['tools']} tools x {lv['tool']} + {a['cards']} cards x "
                       f"{lv['card']}"
                       + (f" + {a['bonuses']} bonuses x {lv.get('bonus', 0)}"
                          if st.session_state.bonuses else ""))
        st.metric("Sheep", a["sheep"], border=True)
        st.metric("Tools", a["tools"], border=True)
        st.metric("Cards", a["cards"], border=True,
                  help="Cards from the card actions 5, 10, 15, 20")
        if st.session_state.bonuses:
            st.metric("Bonuses", a["bonuses"], border=True,
                      help="Workers gained with a cube while at the round's maximum")
        has_token = st.session_state.first_player == i
        st.metric("First player", "Yes" if has_token else "No", border=True,
                  help="Taken by playing a card action (5, 10, 15, 20)")
    st.button("Lose first player token", key=f"lose_fp{i}",
              on_click=lose_first_player, args=(i,), disabled=not has_token,
              icon=":material/flag:",
              help="A human player took a card action and the first player token")

    card = a["current"]
    if card is None:
        st.info("No workers left - this automa is done for the round.",
                icon=":material/bedtime:")
        return

    max_cost = card["areas"][round_idx]
    with st.container(horizontal=True, gap="medium"):
        with st.container(width=300):
            automa_card(card_html(card, round_idx), token=f"{i}-{a['draws']}",
                        revealed=a["revealed"], key=f"card{i}",
                        on_flip=lambda i=i: reveal(i))
        with st.container(width=320):
            if not a["revealed"]:
                st.info("Click the card to reveal the automa's next action.",
                        icon=":material/touch_app:")
            else:
                show_actions(i, a, card, max_cost, round_idx)
            st.caption(f"Deck: {len(a['draw'])} · Discard: {len(a['discard'])}")
            if a["log"]:
                with st.expander("Log"):
                    st.markdown("  \n".join(reversed(a["log"][-15:])))


def show_actions(i, a, card, max_cost, round_idx):
    if max_cost is None:
        st.warning("No action this round - discard the card.",
                   icon=":material/block:")
    else:
        tools_instead = TOOLS_RULE == "not_activated" and card["tools"][round_idx]
        st.success(f"Place workers on **{card['action']}. {card['name']}** "
                   f"if the next free space costs **{max_cost} or less** and "
                   f"the automa has enough workers. Otherwise "
                   + (f"take **{max_cost} tools** and lose {max_cost} workers. "
                      if tools_instead else "discard. ")
                   + f"Scores **{card['sheep'][round_idx]} sheep**."
                   + (f" Gets **{max_cost} tools**."
                      if TOOLS_RULE in ("on_play", "both") and card["tools"][round_idx]
                      else "")
                   + (f" Takes the **first player token** and a **{card['name'].lower()}**."
                      if card["first_player"] else ""),
                   icon=":material/check_circle:")
    with st.container(horizontal=True):
        for w in (1, 2, 3):
            allowed = (max_cost is not None and w <= max_cost
                       and w <= a["available"] and w <= card["spaces"])
            st.button(f"Play {w}", key=f"play{i}-{w}", on_click=play,
                      args=(i, w), disabled=not allowed, type="primary",
                      icon=":material/person:", width="stretch")
    if max_cost is not None and card["tools"][round_idx]:
        if TOOLS_RULE == "not_activated":
            st.button(f"Space too expensive or full: take {max_cost} tools",
                      key=f"tools_space{i}", on_click=take_tools, args=(i, False),
                      icon=":material/construction:", width="stretch",
                      help="Not activated: the automa takes the tools, loses the "
                           "same number of workers and its turn is over")
        if TOOLS_RULE in ("not_activated", "not_enough_workers", "both") \
                and a["available"] < max_cost:
            st.button(f"Not enough workers: take {max_cost} tools", key=f"tools{i}",
                      on_click=take_tools, args=(i, True),
                      icon=":material/construction:", width="stretch",
                      help="The automa takes the tools, loses its last workers and "
                           "is done for this round")
    st.button("Discard card", key=f"discard{i}", on_click=discard, args=(i,),
              icon=":material/skip_next:", width="stretch")


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------

with st.sidebar:
    st.title("Hallertau automa")
    st.number_input("Number of automas", 1, MAX_AUTOMAS, key="opt_n",
                    on_change=options_changed,
                    help="Up to 3 for a game, 4 to test the automa scoring")
    for i in range(st.session_state.opt_n):
        if f"opt_level_{i}" not in st.session_state:  # dropped while hidden
            st.session_state[f"opt_level_{i}"] = st.session_state.level_prefs[i]
        st.segmented_control(f"Automa {i + 1} difficulty", list(LEVELS),
                             key=f"opt_level_{i}", required=True,
                             format_func=str.title, width="stretch",
                             on_change=options_changed)
    st.toggle("Play with bonuses", key="opt_bonuses", on_change=options_changed,
              help="A worker an automa gains while at the round's maximum is kept as "
                   "a bonus (points: " + ", ".join(f"{k} {v.get('bonus', 0)}"
                                                   for k, v in LEVELS.items())
                   + "). Off: the worker is lost.")
    st.button("New game", key="new_game", on_click=options_changed, type="primary",
              icon=":material/casino:", width="stretch")
    st.caption("Changing an option starts a new game.")
    st.divider()
    st.caption(f"Automas start with {START_WORKERS} workers. Space cost: 1st space = 1, "
               "2nd = 2, 3rd = 3. Max workers at the end of each round: "
               + " / ".join(map(str, MAX_WORKERS)) + ". Card actions (5, 10, 15, "
               "20) give the first player token and a card. Points per sheep / tool / "
               "card / bonus: " + ", ".join(
                   f"{k} {v['sheep']}/{v['tool']}/{v['card']}/{v.get('bonus', 0)}"
                   for k, v in LEVELS.items()) + ".")

if st.session_state.confirm_new_game:
    confirm_new_game()

stats = reports.load_stats()
automas = st.session_state.automas

if st.session_state.game_over:
    reports.final_report(automas, stats, CONFIG, LEVELS, st.session_state.bonuses)
    st.button("New game", key="new_game_end", on_click=apply_options, type="primary",
              icon=":material/casino:")
    st.stop()

round_idx = st.session_state.round - 1
with st.container(horizontal=True, vertical_alignment="center"):
    st.header(f"Round {ROMAN[round_idx]}")
    if round_idx < ROUNDS - 1:
        st.button("End round", key="end_round", on_click=end_round,
                  icon=":material/east:")
    else:
        st.button("End game", key="end_game", on_click=end_game, type="primary",
                  icon=":material/flag_circle:")

if st.session_state.report_round is not None:
    r = st.session_state.report_round
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.subheader(f"Round {ROMAN[r]} report")
            st.button("Hide", on_click=hide_report, icon=":material/close:",
                      key="hide_report")
        reports.round_report(automas, r, stats, CONFIG, st.session_state.bonuses)

for i, (col, a) in enumerate(zip(st.columns(len(automas)), automas)):
    with col:
        show_automa(i, a, round_idx)
