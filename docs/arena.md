# Arena

The arena compares the production model with candidate models on real
conversations, without the user knowing which model wrote which answer.

On a small share of turns, the user's message is answered twice, side by side,
by the production model (the **champion**) and by one **challenger**. The user
picks the answer they prefer; that answer is kept in the conversation and the
pick is counted. Over time, the results page shows whether a challenger is
preferred to the champion.

## Turning it on

1. Enable the `arena` feature flag (see `FEATURE_FLAGS`). It can be enabled
   for everyone, or dynamically for a cohort through PostHog.
2. In the Django admin, create an **Arena experiment**:
   - **Champion**: the model conversations are pinned to, usually
     `LLM_DEFAULT_MODEL_HRID`.
   - **Challengers**: the models to compare with it. Each one must be an active
     model of the [LLM configuration](llm-configuration.md) with the same tool
     list as the champion, so the comparison is about the model, not the tools.
   - **Sampling rate**: the share of eligible turns that become arena turns.
   - **Daily cap per user**: the maximum number of arena turns a user sees in
     24 hours.
3. Tick **Is active**. Only one experiment can be active at a time.

## When a turn becomes an arena turn

The client asks `POST /chats/{id}/arena/draw/` before sending a message. The
turn is compared only when all of these hold:

- the flag is on for the user and an experiment is active;
- the conversation is pinned to the champion (a new conversation is first
  pinned to the model the user selected, as on a normal turn; a conversation
  on another model is never compared, and the results page counts these as
  "refused draws");
- the champion is not marked unhealthy;
- the message carries no document to parse (images are fine): both sides
  would otherwise index the same document at the same time;
- the random draw falls under the sampling rate and the user is under the
  daily cap;
- at least one challenger is healthy and, when the turn carries an image, can
  read images.

One challenger is then drawn at random, and the side (left or right) each model
is shown on is shuffled.

## What the user sees

The two answers stream side by side as "Answer A" and "Answer B". Model names
are never sent to the client, and the assistant's self-description is
anonymised during an arena turn. Once both answers are complete, the user picks
one with the vote bar: the chosen answer moves into the conversation and a
short card thanks them, with their vote count.

The first time a user sees an arena turn, one sentence above it explains what
is happening.

## Answers are never lost

- The champion's answer is written to the conversation as soon as it is
  complete. If the user leaves or reloads without voting, or a new message
  reaches the conversation from another tab or device, that answer stays. A
  vote for the challenger swaps it in.
- On screen, the conversation cannot go on while a comparison waits for a vote:
  sending a message asks the user to pick an answer first.
- A comparison left without a vote is shown again, with its vote bar, when the
  conversation is reopened.
- If either side fails, the comparison is closed and the champion's answer is
  kept when it exists. When there is no answer at all, the user's message is
  kept and an error is shown, as on a failed normal turn.
- Tools with side effects outside the conversation (presentation generation)
  are disabled on both sides, so the answer that is not picked leaves nothing
  behind.

## Results

Each experiment has a **Results** page in the admin, readable by superusers and
by users with the `chat.view_arena_results` permission. For each challenger, it
shows the number of votes, its win rate against the champion and the 95% Wilson
interval of that rate. A row is marked **indicative** until it has
`min_votes_for_conclusion` votes and its interval excludes 50%.

## Retention

Comparisons keep copies of both answers and of the conversation at the time of
the draw. They are erased, together with the link to the user and the
conversation, when the conversation or the user is deleted. The
`purge_arena_content` management command applies the same erasure to
comparisons older than 90 days. Votes and metrics (tokens, latency, CO₂) are
kept, without any personal link.

Celery beat runs it daily once `ARENA_PURGE_CONTENT_CRON` is set to a
five-field cron string, evaluated in UTC (see [Celery](celery.md#periodic-tasks)).
It is off by default, like the other periodic tasks: set it on every deployment
that enables the Arena, and keep `backend.celeryBeat.enabled: true` in Helm.

```bash
ARENA_PURGE_CONTENT_CRON="0 3 * * *"
```

To run it once by hand:

```bash
python manage.py purge_arena_content
```
