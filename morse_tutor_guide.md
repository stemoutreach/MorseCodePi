# MorseCodePi — Morse Code Tutor for Raspberry Pi

This project turns your Raspberry Pi into a **Morse code listening + practice tutor**:

- **Type a letter** on your keyboard → the Pi **plays the Morse code** on a buzzer  
- Then you can **repeat it** using a straight key (momentary switch) → the program **scores your attempt**
- While you key, you get **sidetone** (the buzzer sounds as long as the key is held)

This guide explains **setup, usage, controls, and how the code works**.

---

## Hardware

### Required
- Raspberry Pi (tested with Pi 4)
- **Active buzzer** on **GPIO17**
- **Straight key / momentary switch** on **GPIO23**
- Jumper wires

### Notes on buzzers
This code version is written for an **active buzzer** (ON/OFF beeps).  
Active buzzers have a **fixed pitch** (you can’t change the tone frequency in software).

---

## Wiring

### Buzzer (active) — GPIO17
- Buzzer **+** → **GPIO17** (physical pin **11**)
- Buzzer **–** → **GND** (physical pin **6** or any ground)

### Key (straight key / button) — GPIO23
- One terminal → **GPIO23** (physical pin **16**)
- Other terminal → **GND**

The program uses `pull_up=True`, so the input is:
- **HIGH** when not pressed  
- **LOW** when pressed (connected to ground)

---

## Software setup

Install dependencies:

```bash
sudo apt-get update
sudo apt-get install -y python3-gpiozero
```

The script uses:
- `gpiozero` for GPIO (buzzer + button)
- `tkinter` for a small keypress window when running in Thonny (usually preinstalled on Raspberry Pi OS)

If tkinter is missing:

```bash
sudo apt-get install -y python3-tk
```

---

## Run the program

### Option A — Run in Thonny (recommended for beginners)
1. Open Thonny
2. Open `morse_tutor.py`
3. Click **Run**
4. A small window appears — click it, then type

### Option B — Run from Terminal
```bash
python3 morse_tutor.py
```

If stdin is a real terminal (TTY), the script can run in terminal mode.  
If not (like Thonny), it automatically uses the GUI window.

---

## Controls

### In the GUI window
- **Type letters/numbers/punctuation** to play Morse
- **Space** = word gap (7 units of silence)
- **ESC** = quit
- **Practice Mode toggle:**
  - **F1** toggles practice mode
  - **Ctrl+P** toggles practice mode  
    (This exists so you can still practice the letter **P** by typing `p`.)

### Practice behavior
When practice mode is ON:
1. You type a character
2. The buzzer plays the Morse for that character
3. The window shows what is **expected**:
   - **Pretty**: `·` for dot, `−` for dash
   - **Words**: `DOT` / `DASH`
4. You key it back using the straight key
5. The program displays **what it heard** and whether it matches

---

## How timing works (Morse rules)

The script uses a base timing unit called `UNIT`:

- **Dot** = 1 × `UNIT`
- **Dash** = 3 × `UNIT`
- Gap between dot/dash within a letter = 1 × `UNIT`
- Gap between letters = 3 × `UNIT`
- Gap between words = 7 × `UNIT`

You can slow down or speed up the whole system by changing:

```python
UNIT = 0.12
```

---

## How the code works

### 1) Morse mapping
A dictionary maps characters to Morse strings:

```python
MORSE = { "A": ".-", "B": "-...", ... }
```

### 2) Playback (buzzer)
`play_morse(code)` loops over each symbol in the pattern and calls `play_symbol()`:

- Dot → buzzer ON for `1*UNIT`
- Dash → buzzer ON for `3*UNIT`
- Adds a `1*UNIT` gap between elements
- Adds remaining delay to make the letter gap `3*UNIT`

### 3) Sidetone while keying
During practice capture, the code temporarily attaches callbacks:

- `keyer.when_pressed` → buzzer ON
- `keyer.when_released` → buzzer OFF

So you hear the tone while you hold the key down.

### 4) Accurate key sensing (edge timing)
To measure dot vs dash correctly, the program captures **press and release edges**:

- `wait_for_press_edge()` returns the timestamp when the key transitions to pressed
- `wait_for_release_edge()` returns the timestamp when it transitions to released

Press duration is:

```
duration = t_release - t_press
```

Then the script classifies:
- **Dot** if duration < `DOT_DASH_CUTOFF`
- **Dash** otherwise

### 5) End-of-letter detection
After each release, it waits for another press:
- If there’s **no press for `END_IDLE_UNITS * UNIT`**, the attempt is considered complete.

### 6) Expected pattern display
Two helper functions format Morse for readability:
- `morse_pretty(".-")` → `· −`
- `morse_words(".-")` → `DOT DASH`

---

## Tuning / Calibration

If it feels too strict or too fast, adjust these:

### Make it slower
```python
UNIT = 0.15
```

### Make dot/dash classification more forgiving
If you tend to hold dots a little long, increase the cutoff:

```python
DOT_DASH_CUTOFF = 3.0 * UNIT
```

### Give yourself longer pauses between elements
If you need more time before the program “ends the letter”:

```python
END_IDLE_UNITS = 4.0
```

---

## Troubleshooting

### “No sound”
- Confirm the buzzer is an **active buzzer** and wired to **GPIO17 + GND**
- Confirm GPIO pin numbering (BCM vs physical): the code uses **BCM GPIO17**
- Try a quick buzzer test:

```python
from gpiozero import Buzzer
import time
b = Buzzer(17)
b.on(); time.sleep(0.2); b.off()
```

### “Sidetone sounds, but scoring is wrong”
- Slow down (`UNIT = 0.15`)
- Increase cutoff (`DOT_DASH_CUTOFF = 3.0 * UNIT`)
- Ensure the key is cleanly wired between **GPIO23** and **GND**

### “The program doesn’t react to typing”
- If running in Thonny: click inside the GUI window first
- If running in Terminal: make sure the terminal is focused

### “Practice mode toggle blocks typing P”
- Use **F1** or **Ctrl+P** to toggle practice mode
- Then type `p` normally to practice the letter P

---

## Suggested repo layout

A simple structure for GitHub:

```
MorseCodePi/
  README.md
  docs/
    morse_tutor_guide.md
  src/
    morse_tutor.py
```

---

## Next ideas (optional)
- Random-letter drills (levels: E/T → A/N → full alphabet)
- Scoring + streaks + accuracy %
- Word mode (“SOS”, “HELLO”, “CODE”, etc.)
- Passive buzzer / PWM tone pitch control (requires hardware change)
