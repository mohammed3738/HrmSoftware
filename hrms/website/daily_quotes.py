"""Short, original reflections for the daily employee dashboard."""


_OPENINGS = (
    "Make space for a good question.", "Give a colleague your full attention.",
    "Start with a clear purpose.", "Look for the next small improvement.",
    "Give credit for the quiet work.", "Ask what would make the next step easier.",
    "Share what you learned yesterday.", "Bring curiosity to a familiar task.",
    "Make the handover clear.", "Take a moment to listen.",
    "Choose one thing to finish well.", "Notice what someone else does well.",
    "Turn a useful idea into a small experiment.", "Leave room for another perspective.",
    "Make a difficult task a little simpler.", "Name the outcome before you start.",
    "Offer help where it counts.",
)

_CLOSINGS = (
    "Small steps add up.", "Care shows in the details.", "Clarity helps everyone move forward.",
    "Good work grows through practice.", "Progress begins with attention.", "Trust grows one exchange at a time.",
    "Every contribution matters.", "A fresh perspective can help.", "Thoughtful work travels further.",
    "Steady effort builds skill.", "Teams learn in small moments.", "Patience makes room for insight.",
    "Good judgment grows with reflection.", "Understanding is worth the time.", "Shared knowledge grows.",
    "Simple habits support good work.", "Listening is part of leading.", "Focus gives ideas room.",
    "A little preparation goes a long way.", "Kindness belongs at work.", "Quality starts with care.",
    "Clear words save time.", "Consistency makes progress visible.",
)


def daily_work_quote(day):
    # Coprime sequence lengths give 391 distinct daily pairs, including across New Year.
    index = day.toordinal()
    return f"{_OPENINGS[index % len(_OPENINGS)]} {_CLOSINGS[index % len(_CLOSINGS)]}"
