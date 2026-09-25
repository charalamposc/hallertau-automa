"""Flippable automa card (Streamlit custom component v2).

The card is shown face down; clicking it flips it over with an animation and
sends a `flipped` trigger back to Python. A new card (new `token`) is placed
face down again without animation.
"""

from collections.abc import Callable
from pathlib import Path

import streamlit as st

_HTML = """
<div class="hc-scene">
  <div class="hc-flip">
    <div class="hc-face hc-back">
      <div class="hc-back-frame">
        <div class="hc-back-title">Hallertau</div>
        <div class="hc-back-emblem">A</div>
        <div class="hc-back-title">Automa</div>
        <div class="hc-back-hint">Click to reveal</div>
      </div>
    </div>
    <div class="hc-face hc-front"></div>
  </div>
</div>
"""

_FLIP_CSS = """
.hc-scene { width: 300px; aspect-ratio: 63 / 88; perspective: 1200px; }
.hc-flip {
  position: relative; width: 100%; height: 100%;
  transform-style: preserve-3d;
  transition: transform .7s cubic-bezier(.3, .7, .3, 1);
  cursor: pointer;
}
.hc-flip.revealed { transform: rotateY(180deg); cursor: default; }
.hc-flip.no-anim { transition: none; }
.hc-face {
  position: absolute; inset: 0;
  backface-visibility: hidden; -webkit-backface-visibility: hidden;
}
.hc-front { transform: rotateY(180deg); }
.hc-front .hc-card { width: 100%; height: 100%; }

.hc-back {
  box-sizing: border-box;
  padding: 12px;
  border: 3px solid #C8962E;
  border-radius: 16px;
  background:
    repeating-linear-gradient(45deg, rgba(255,255,255,.05) 0 8px, transparent 8px 16px),
    radial-gradient(circle at 50% 45%, #4F7942, #2B4A26 75%);
  box-shadow: 0 6px 18px rgba(0, 0, 0, .35);
}
.hc-flip:not(.revealed):hover .hc-back { box-shadow: 0 10px 26px rgba(0, 0, 0, .5); }
.hc-back-frame {
  height: 100%; box-sizing: border-box;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 14px;
  border: 1.5px solid rgba(200, 150, 46, .8);
  border-radius: 10px;
  color: #F3E3B5;
  font-family: Georgia, "Times New Roman", serif;
}
.hc-back-title { font-size: 26px; letter-spacing: 3px; text-transform: uppercase; }
.hc-back-emblem {
  width: 84px; height: 84px;
  display: flex; align-items: center; justify-content: center;
  border: 3px solid #C8962E; border-radius: 50%;
  background: #FBF6EA; color: #2B4A26;
  font-size: 44px; font-weight: 700;
}
.hc-back-hint {
  margin-top: 10px;
  font: 12px/1 "Source Sans Pro", Helvetica, Arial, sans-serif;
  color: rgba(243, 227, 181, .75);
}
"""

_JS = """
export default function (component) {
  const { data, parentElement, setTriggerValue } = component
  const flip = parentElement.querySelector(".hc-flip")
  const front = parentElement.querySelector(".hc-front")
  if (!flip || !front) return

  front.innerHTML = (data && data.front) || ""
  const token = (data && data.token) || ""
  const revealed = !!(data && data.revealed)

  if (flip.dataset.token !== token) {
    // A new card: put it in place without playing the flip animation.
    flip.dataset.token = token
    flip.classList.add("no-anim")
    flip.classList.toggle("revealed", revealed)
    void flip.offsetWidth
    flip.classList.remove("no-anim")
  } else if (revealed) {
    flip.classList.add("revealed")
  }

  flip.onclick = () => {
    if (flip.classList.contains("revealed")) return
    flip.classList.add("revealed")
    setTriggerValue("flipped", true)
  }
}
"""

_CARD = st.components.v2.component(
    "hallertau_automa_card",
    html=_HTML,
    css=(Path(__file__).parent / "card.css").read_text() + _FLIP_CSS,
    js=_JS,
)


def automa_card(front_html: str, token: str, revealed: bool, *, key: str,
                on_flip: Callable[[], None]):
    """Show a card face down (click flips it) or face up when `revealed`."""
    return _CARD(data={"front": front_html, "token": token, "revealed": revealed},
                 key=key, on_flipped_change=on_flip)
