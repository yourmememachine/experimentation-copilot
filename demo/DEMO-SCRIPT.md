# Demo video — script and shot list (target 2:45, hard limit 3:00)

Narration is recorded in my own voice. The screen capture (demo/demo-capture.mp4) is recorded without narration; the voice track is the one step I record myself and drop over the capture.

## Shot list

| # | Time | Screen | Narration (read as written) |
| --- | --- | --- | --- |
| 1 | 0:00–0:20 | Copilot home screen, prompt box empty | "Setting up an experiment in a dashboard takes a dozen careful steps, and old flags pile up until nobody knows what's safe to remove. I built Experimentation Copilot to handle the whole lifecycle." |
| 2 | 0:20–0:50 | Type the prompt: "Test a new checkout button colour green vs blue for 20% of users, success is checkout_completed" → plan card appears | "I just describe the test in plain English. The copilot turns it into a full experiment plan: a multivariate flag, green as control and blue as the variant, twenty percent of users split fifty-fifty inside the experiment, checkout_completed as the success metric — with the hypothesis written out." |
| 3 | 0:50–1:15 | Guardrails panel; a 95%-traffic prompt is blocked; return to the good plan | "Before anything ships, guardrails check the plan. Traffic over ninety percent is blocked without approval, an experiment with no metric can't be created, and the current state is snapshotted so I can roll back. Nothing reaches production until I approve it." |
| 4 | 1:15–1:40 | Tick approval, click Approve & Apply; flag appears in the flags table | "I approve it, and the copilot creates the flag in Flagsmith, starting at the first rollout step. From here Flagsmith serves the variants and splits the traffic." |
| 5 | 1:40–2:15 | Results panel: simulate traffic, results table, winner named; Approve & roll out winner | "When results come in, the copilot compares the variants and names a winner — or says inconclusive if there isn't enough data. With my approval, it graduates the winner to one hundred percent in Flagsmith." |
| 6 | 2:15–2:45 | Stale-flag cleanup view; archive one stale flag with approval; rollback button | "The cleanup view scores every flag for staleness and tells me exactly why, and I can archive one right here with approval. And if anything goes wrong, one click rolls it back from the snapshot. That's Experimentation Copilot." |

## Recording notes

- Capture at 1080p, browser zoom 125% so text is readable.
- Demo mode data is fine on camera: the seeded flags are the ones named in the README.
- Keep the whole cut under 3:00 — the rules cap the video at 3 minutes.
- TODO (mine): record the six narration lines as one voice track, lay it over the capture, export, upload, and paste the link into the README.
