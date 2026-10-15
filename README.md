# Circle Draw

A small English-language web app for a random participant draw, built around a
doubly linked circular list in Python. Use **Pick a winner** for a one-off draw,
or **Last one standing** to remove one random participant each round. Save and
restore named checkpoints during the current server session.

## Run

Requires Python 3.10 or newer. No third-party packages are needed.

```powershell
python main.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). To choose a different port,
run `python main.py --port 8080`.

## Test

```powershell
python -m unittest discover -s tests -v
```

The participant ring is circular in both directions. Each draw chooses a random
step count and direction (or follows the selected direction), traverses the
linked participants, and either selects or removes the landed-on participant.
Checkpoints and the round state are held in memory and reset when the server
process exits.
