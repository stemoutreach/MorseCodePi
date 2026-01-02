#!/usr/bin/env python3
import sys
import time
import threading
import queue
from gpiozero import Buzzer, Button

# -----------------------------
# CONFIG
# -----------------------------
BUZZER_GPIO = 17
KEYER_GPIO  = 23

UNIT = 0.12  # seconds per dot unit (try 0.15 while learning)

START_KEY_TIMEOUT = 8.0          # seconds to start keying after playback
END_IDLE_UNITS    = 3.0          # >= 3 units of silence ends the attempt

# More forgiving cutoff than 2.0*UNIT (helps beginners)
DOT_DASH_CUTOFF   = 2.5 * UNIT   # < cutoff => dot, >= cutoff => dash

POLL_DT      = 0.001  # 1ms sampling
BOUNCE_TIME  = 0.03   # mechanical key debounce

SIDETONE_ENABLED = True          # buzzer ON while key is held
MIN_PRESS = 0.03                # ignore ultra-short presses (bounce/noise)

DEBUG_KEYING = False            # set True to see raw press timings

MORSE = {
    "A": ".-",    "B": "-...",  "C": "-.-.",  "D": "-..",   "E": ".",
    "F": "..-.",  "G": "--.",   "H": "....",  "I": "..",    "J": ".---",
    "K": "-.-",   "L": ".-..",  "M": "--",    "N": "-.",    "O": "---",
    "P": ".--.",  "Q": "--.-",  "R": ".-.",   "S": "...",   "T": "-",
    "U": "..-",   "V": "...-",  "W": ".--",   "X": "-..-",  "Y": "-.--",
    "Z": "--..",
    "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-",
    "5": ".....", "6": "-....", "7": "--...", "8": "---..", "9": "----.",
    ".": ".-.-.-", ",": "--..--", "?": "..--..", "/": "-..-.",
    "-": "-....-", "(": "-.--.", ")": "-.--.-",
}


# -----------------------------
# MORSE DISPLAY HELPERS
# -----------------------------
def morse_pretty(code: str) -> str:
    """Return Morse using nice dot/dash symbols for display."""
    return code.replace(".", "·").replace("-", "−")

def morse_words(code: str) -> str:
    """Return Morse as words (DOT / DASH) for beginners."""
    return " ".join("DOT" if s == "." else "DASH" for s in code)

# -----------------------------
# GPIO DEVICES
# -----------------------------
buzzer = Buzzer(BUZZER_GPIO)
keyer  = Button(KEYER_GPIO, pull_up=True, bounce_time=BOUNCE_TIME)

# -----------------------------
# MORSE PLAYBACK
# -----------------------------
def buzz(duration_s: float):
    buzzer.on()
    time.sleep(duration_s)
    buzzer.off()

def play_symbol(sym: str):
    if sym == ".":
        buzz(1 * UNIT)
    elif sym == "-":
        buzz(3 * UNIT)
    time.sleep(1 * UNIT)  # intra-element gap

def play_morse(code: str):
    for sym in code:
        play_symbol(sym)
    time.sleep(2 * UNIT)  # completes letter gap (3 units total)

def feedback_ok():
    buzz(0.06); time.sleep(0.06); buzz(0.06)

def feedback_bad():
    buzz(0.25)

# -----------------------------
# SIDETONE
# -----------------------------
def enable_sidetone():
    prev_pressed = keyer.when_pressed
    prev_released = keyer.when_released

    def _on():
        buzzer.on()

    def _off():
        buzzer.off()

    keyer.when_pressed = _on
    keyer.when_released = _off
    buzzer.off()
    return prev_pressed, prev_released

def restore_key_callbacks(prev_pressed, prev_released):
    keyer.when_pressed = prev_pressed
    keyer.when_released = prev_released
    buzzer.off()

# -----------------------------
# EDGE-BASED WAIT HELPERS (FIX)
# -----------------------------
def wait_for_press_edge(timeout_s: float) -> float | None:
    """
    Return timestamp when the key transitions to pressed, or None on timeout.
    """
    t0 = time.monotonic()
    prev = keyer.is_pressed
    while time.monotonic() - t0 < timeout_s:
        cur = keyer.is_pressed
        if cur and not prev:
            return time.monotonic()
        prev = cur
        time.sleep(POLL_DT)
    return None

def wait_for_release_edge(timeout_s: float = 10.0) -> float | None:
    """
    Return timestamp when the key transitions to released, or None on timeout.
    """
    t0 = time.monotonic()
    prev = keyer.is_pressed
    while time.monotonic() - t0 < timeout_s:
        cur = keyer.is_pressed
        if (not cur) and prev:
            return time.monotonic()
        prev = cur
        time.sleep(POLL_DT)
    return None

# -----------------------------
# KEYER CAPTURE (ACCURATE)
# -----------------------------
def record_keying():
    """
    Record one keyed letter attempt.
    Ends when silence >= END_IDLE_UNITS * UNIT after a release.
    Returns (captured_symbols, press_durations_seconds_list)
    """
    prev_pressed = prev_released = None
    if SIDETONE_ENABLED:
        prev_pressed, prev_released = enable_sidetone()

    try:
        # Wait for the first press edge
        t_press = wait_for_press_edge(START_KEY_TIMEOUT)
        if t_press is None:
            return "", []

        captured = []
        durations = []

        while True:
            # Wait for release edge (end of this element)
            t_release = wait_for_release_edge(timeout_s=10.0)
            if t_release is None:
                break

            dur = t_release - t_press
            if dur < MIN_PRESS:
                # ignore tiny bounce
                if DEBUG_KEYING:
                    print(f"[debug] ignored press {dur*1000:.1f} ms")
            else:
                sym = "." if dur < DOT_DASH_CUTOFF else "-"
                captured.append(sym)
                durations.append(dur)

                if DEBUG_KEYING:
                    u = dur / UNIT
                    print(f"[debug] press {dur*1000:.1f} ms ({u:.2f}u) => {sym}")

            # Wait for next press edge; if none within end gap => done
            end_gap_s = END_IDLE_UNITS * UNIT
            t_next = wait_for_press_edge(end_gap_s)
            if t_next is None:
                break
            t_press = t_next

        return "".join(captured), durations

    finally:
        if SIDETONE_ENABLED and prev_pressed is not None:
            restore_key_callbacks(prev_pressed, prev_released)
        else:
            buzzer.off()

def units_str(seconds: float) -> str:
    return f"{seconds/UNIT:.1f}u"

def compare_attempt(expected: str, got: str, durations) -> tuple[bool, str]:
    if not got:
        # Still show what was expected (helpful for beginners)
        return False, (
            f"Expected: {expected}\n"
            f"Pretty  : {morse_pretty(expected)}\n"
            f"Words   : {morse_words(expected)}\n"
            f"❌ No keying detected."
        )

    dur_info = " ".join(units_str(d) for d in durations)
    lines = [
        f"Expected: {expected}",
        f"Pretty  : {morse_pretty(expected)}",
        f"Words   : {morse_words(expected)}",
        f"Got     : {got}",
        f"GotPretty: {morse_pretty(got)}",
        f"GotWords: {morse_words(got)}",
        f"Presses : {dur_info}",
    ]

    if got == expected:
        lines.append("✅ Correct!")
        return True, "\n".join(lines)

    # Hint: first mismatch
    mismatch = None
    for i in range(min(len(expected), len(got))):
        if expected[i] != got[i]:
            mismatch = i
            break

    if mismatch is not None:
        lines.append(f"❌ Mismatch at symbol #{mismatch+1} (expected {expected[mismatch]} got {got[mismatch]})")
    else:
        lines.append(f"❌ Length mismatch (expected {len(expected)} symbols, got {len(got)})")

    return False, "\n".join(lines)
# -----------------------------
# TKINTER GUI MODE (Thonny-safe)
# -----------------------------
def gui_mode():
    import tkinter as tk
    practice_mode = {"on": True}
    busy = {"flag": False}
    q = queue.Queue()

    def set_status(text: str):
        status_var.set(text)

    def do_practice(expected_code: str):
        got, durations = record_keying()
        ok, msg = compare_attempt(expected_code, got, durations)
        q.put((ok, msg))

    def on_key(event):
        if busy["flag"]:
            return

        if event.keysym == "Escape":
            root.destroy()
            return

        # Toggle practice mode:
        # - Press F1 (easy to remember)
        # - Or press Ctrl+P (so you can still practice the letter P)
        if event.keysym == "F1" or ((event.state & 0x4) and (event.keysym.lower() == "p")):
            practice_mode["on"] = not practice_mode["on"]
            set_status(f"Practice mode: {'ON' if practice_mode['on'] else 'OFF'}")
            return

        if event.keysym == "space":
            set_status("Word gap (7 units)")
            time.sleep(7 * UNIT)
            set_status("Ready. Type a letter/number.")
            return

        ch = (event.char or "").upper()
        if not ch:
            return

        code = MORSE.get(ch)
        if not code:
            return

        busy["flag"] = True
        set_status(f"Playing: {ch}\nExpected: {morse_pretty(code)}\nWords: {morse_words(code)}")
        play_morse(code)

        if practice_mode["on"]:
            set_status(f"Key it back:\nExpected: {morse_pretty(code)}\nWords: {morse_words(code)}\nStart within {START_KEY_TIMEOUT:.0f}s...")
            t = threading.Thread(target=do_practice, args=(code,), daemon=True)
            t.start()
        else:
            busy["flag"] = False
            set_status("Ready. Type a letter/number.")

    def poll_results():
        try:
            ok, msg = q.get_nowait()
        except queue.Empty:
            root.after(50, poll_results)
            return

        set_status(msg)
        (feedback_ok() if ok else feedback_bad())
        busy["flag"] = False
        root.after(50, poll_results)

    root = tk.Tk()
    root.title("Morse Tutor (GPIO17 + GPIO23)")

    status_var = tk.StringVar()
    status_var.set(
        f"Ready. Click this window, then type.\n"
        f"ESC quits, F1 toggles practice (or Ctrl+P), space = word gap\n"
        f"Tip: DOT = ·  DASH = −\n"
        f"Buzzer GPIO{BUZZER_GPIO} | Keyer GPIO{KEYER_GPIO} | UNIT={UNIT:.2f}s"
    )

    tk.Label(root, textvariable=status_var, font=("Arial", 14), justify="left", padx=12, pady=12).pack()
    tk.Label(root, text="During practice, buzzer sounds while you press the keyer.\nTip: Use F1 (or Ctrl+P) to toggle practice so you can still practice the letter P.",
             font=("Arial", 11), padx=12, pady=6).pack()

    root.bind("<Key>", on_key)
    root.after(50, poll_results)
    root.mainloop()

def main():
    print("\nMorse Tutor (Raspberry Pi)")
    print(f" - Buzzer: GPIO{BUZZER_GPIO}")
    print(f" - Keyer : GPIO{KEYER_GPIO} (press connects to GND)")
    print(f" - UNIT  : {UNIT:.2f}s (dot=1u, dash=3u)")
    print(f" - Sidetone: {'ON' if SIDETONE_ENABLED else 'OFF'}\n")
    print("Running GUI mode (Thonny-safe). Click the window and type.\n")
    gui_mode()

if __name__ == "__main__":
    try:
        main()
    finally:
        buzzer.off()
