---
title: Best practices for production-ready flags
source_url: https://posthog.com/docs/feature-flags/best-practices
section: feature-flags
---

# Best practices for production-ready flags

## Checklist

- Call `identify()` before evaluating flags — the hash uses the wrong ID otherwise. This is the most common input problem.
- Evaluate flags server-side with local evaluation — explicit inputs, your data right there, no workarounds.
- Bootstrap client-side flags — client-side evaluation is async. Bootstrap to eliminate the gap.
- Handle `undefined` explicitly — it means "not evaluated yet," not `false`.
- Evaluate once, record the result — a flag is a one-time signal. Re-evaluate only on meaningful state changes.
- Evaluate where the data lives — if the data is on your server, evaluate there.
- Choose evaluation context deliberately — "server and client" is the default for compatibility, not because it's the right choice for your flag.
- Clean up flags that have done their job — a flag at 100% is done. Remove it or archive it.
- Disable client-side evaluation for server-side flags — don't let the client SDK re-evaluate what your server already decided.
- Use a reverse proxy — prevent ad blockers from disabling your flags.
- Call your flag in as few places as possible — wrap in a single function if used in multiple places.
- Name flags clearly — descriptive names, types, positive language.
- Roll out progressively — start small, monitor, then increase.

**The mental model**: Flags are pure functions — same flag key + same distinct ID = same result, always. Unexpected results are almost always input problems — if the result changed, an input changed.

## Flags are pure functions

A flag hashes two things: the flag key and the distinct ID, and returns a deterministic result. Same inputs, same output, every time.

```
hash("my-experiment", "user-123") → 0.31 → always 0.31
```

PostHog layers property targeting (does this user match?), rollout percentage (is their position below the threshold?), and variant assignment on top of that hash.

### How the hash works

PostHog uses SHA-1:

```
hash_key = "{flag_key}.{distinct_id}"
position = parseInt(sha1(hash_key).slice(0, 15), 16) / LONG_SCALE  → float in [0, 1]
in_rollout = position <= rollout_percentage / 100
```

If the flag has property targeting, PostHog first checks whether the person matches the conditions. If they don't match, the hash never runs, the flag returns `false`.

## Unexpected results are almost always input problems

If a flag returns something unexpected, the flag is fine — the problem is in the inputs. Something about the identity, the properties, or the flag definition wasn't what you assumed.

In order of likelihood when something goes wrong:

1. **Input problems** (most common) — wrong distinct ID, missing properties, changed flag definition
2. **Output problems** — the flag returned the right value but the code misread it (e.g. `undefined` treated as `false`)
3. **Actual incidents** — check status.posthog.com. With server-side local evaluation, the SDK evaluates against cached flag definitions locally, so PostHog being unreachable doesn't affect already-cached flags.

## Resolve identity before evaluating flags

Identity is the most common input problem. The hash takes two inputs: the flag key (stable) and the distinct ID (your responsibility). If the distinct ID is wrong at the moment of evaluation, the hash produces a valid but incorrect result.

Call `identify()` before any flag evaluation in auth flows. If you can't guarantee that timing, bootstrap with the stable ID at init so the distinct ID is correct from the first millisecond.

**SPA-specific timing**: In single-page applications, `identify()` and event captures often fire from different components during the same navigation in unpredictable order. Call `identify()` before the navigation that mounts post-auth components.

### Don't rely on flag persistence to fix identity gaps

Experience continuity (flag persistence across authentication) couples flag evaluation with database writes, every evaluation reads and writes to the DB to persist the result. This mixes evaluation and storage concerns, causes known bugs where values can still change after `identify()`, and means no support for local evaluation and slower flag responses.

The better fix: make persistence unnecessary via device bucketing for single-device consistency, or design your identity flow so the distinct ID never changes.

## Evaluation architecture

### Evaluate once, not continuously

A flag is a one-time signal, not a continuous dependency. Evaluate it once, record the result, serve from that recording. Re-evaluating on every request creates cost, latency, and the conditions for "flipping."

### Evaluate where the data lives

If you target a flag on a server-known property, evaluate the flag from the same place that has that knowledge, your server. If you evaluate client-side instead, the SDK needs to fetch that property via a round-trip.

### Server-side local evaluation is the recommended default

- All inputs are explicit — you pass the distinct ID and properties directly
- Your data is right there — no syncing, no fetching
- No workarounds needed — client-side evaluation often requires `setPersonPropertiesForFlags()`, `onFeatureFlags()`, and bootstrap to bridge the gap

### Have the value before you need it

Client-side flag evaluation is async. Any flag check before that completes returns `undefined`, not `false`. Bootstrap is the fix: evaluate flags server-side and pass values to the client at init.

### `undefined` is not "flag is off" nor `false`

`posthog.getFeatureFlag()` returns `undefined` before flags load, meaning "not evaluated yet," not "flag is off." Handle it with bootstrap (preferred) or `onFeatureFlags()`.

## Flag hygiene

### Choose a flag type intentionally

Every flag is configured as client-side, server-side, or both. New flags default to "server and client" for backwards compatibility, a safe starting point, not a recommendation. Pick the context based on where the flag is actually consumed.

### Clean up flags that have done their job

A flag set to 100% with no property targeting has finished its job. Remove it and hardcode the winning path, or at minimum archive it so it stops being evaluated.

### Disable client-side evaluation for server-side flags

If a flag is evaluated server-side and passed to the frontend through application logic, disable it on the client SDK to avoid duplicating work.

### Use a reverse proxy

Ad blockers can disable feature flags, leading users to see the wrong version of the app. Deploy a reverse proxy so requests go through your own domain.

### Call your flag in as few places as possible

Wrap a flag used in multiple places in a single function to avoid inconsistent removal later.

### Name flags clearly

Use descriptive names (`is_v2_billing_dashboard_enabled` over `is_dashboard_enabled`), suffix with purpose (`new-billing-experiment` vs `new-billing-release`), reflect the return type, and use positive language for booleans.

### Roll out progressively

Start at 5-10% of users, monitor metrics, then gradually increase.

### Use dependencies for complex rollouts

Feature flag dependencies let one flag's activation depend on another flag's state. Keep dependency chains simple and avoid circular dependencies.

### Be careful with "Latest" person properties

Properties like "Latest Current URL" update with every new event. If you target a flag on one of these, the flag value can change with every event. Capture a stable person property once instead (e.g. `first_landing_page` via `$set_once`).
