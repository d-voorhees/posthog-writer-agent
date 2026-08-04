---
title: How to control which sessions you record
source_url: https://posthog.com/docs/session-replay/how-to-control-which-sessions-you-record
section: session-replay
---

# How to control which sessions you record

Most users should initialize PostHog with default settings (recording starts automatically) and use URL triggers, event triggers, feature flags, or sampling to control what gets recorded. Manual start/stop control is only needed for advanced use cases.

## Programmatically start and stop recordings

Set `disable_session_recording: true` in your config to prevent automatic recording, then manually control with `posthog.startSessionRecording()` and `posthog.stopSessionRecording()`.

```javascript
posthog.init('<ph_project_token>', {
  api_host: 'https://us.i.posthog.com',
  disable_session_recording: true,
})
```

By default, `startSessionRecording` obeys any ingestion controls already set (sampling, other controls). Override options can be passed to change this:

```javascript
posthog.startSessionRecording(true) // start ignoring all ingestion controls
posthog.startSessionRecording({
  sampling: true || false,
  linked_flag: true || false,
  url_trigger: true || false,
  event_trigger: true || false
})
```

This pattern also supports recording or ignoring specific screens (e.g., stop recording on a payment or settings screen, resume elsewhere), implemented via navigation lifecycle hooks on each platform (web, iOS, Android, React Native, Flutter).

## With URL trigger conditions

Recordings can be set to start only once a user visits a certain page. After the URL matches, recording continues even after they leave that page. The client keeps an in-memory buffer so activity leading up to the trigger is still visible.

## With Event trigger conditions

Recordings can start once a particular event is captured, continuing for the rest of the session. Supported on Web (posthog-js 1.186.0+), iOS (3.48.0+), Android (3.40.1+), React Native (4.52.0+), Flutter (5.25.0+).

**Triggering on exceptions**: if using error tracking, exception events can be selected as an event trigger to start session recording when an error occurs.

### How the trigger buffer works

While waiting for a trigger, the client takes a full snapshot once per minute. Only data from the most recent snapshot up to when the trigger fires is kept, meaning the buffer contains up to 1 minute of pre-trigger activity. Full page navigations clear the buffer and start over.

## With feature flags

A feature flag can control whether sessions are recorded. Recordings are only collected for users when the flag is enabled for them. Create a boolean or multivariate flag, then link it in the replay ingestion settings under "Enable recordings using feature flag."

## Sampling

Sampling records a percentage of all sessions, configured on the replay ingestion settings page. Supported on Web (posthog-js 1.85.0+), Android (3.34.0+), iOS (3.42.0+), React Native (4.37.0+), Flutter (5.26.0+).

Recommendation: start with capturing 100% of sessions and decrease as needed to understand recording volume and data collection.

### How sampling works

Sampling is deterministic based on session ID. PostHog converts the session ID into a number between 0 and 1 via a hash function, compared to the configured sample rate. The same session ID always produces the same number, so the recording decision is consistent throughout the session's lifetime, even across page refreshes.

## Combining controls

Multiple trigger types (event, URL, feature flag, sampling) can be combined with "any matching" or "all matching" logic.

**Warning**: 100% sampling combined with "any" matching records every session regardless of other conditions, since the sampling condition alone matches everything. Lower the sample rate or switch to "all" matching to fix this.

## Trigger groups

Trigger groups allow multiple independent combinations of URL triggers, event triggers, feature flags, sample rate, minimum duration, and match type to be active simultaneously. A session is recorded if it matches any trigger group. Example: one group recording 100% of checkout page sessions, another recording 10% of all site sessions, another recording any session with an exception event.

Legacy trigger settings (configured outside of trigger groups) can be automatically converted to trigger groups via "Create from legacy triggers" in the replay ingestion settings.

## Minimum duration

A minimum duration can be set so sessions shorter than the threshold aren't recorded (useful for filtering out quick bounces).

**Legacy mode** (default): checks against total session age from session start. Limitation: if a user visits multiple pages with full page refreshes, the in-memory buffer may be cleared by navigation, causing missed early-session data.

**Strict mode** (available 1.291.0+, will become default in a future release): checks against actual buffered recording data (first to last timestamp), not session age. Recording only sends once the minimum duration of continuous data exists in the buffer. More accurate for filtering short sessions but may miss more data from users who bounce quickly across multiple pages.

## Billing limits

A billing limit can be set on session replay; PostHog stops ingesting recordings once the limit is reached.
