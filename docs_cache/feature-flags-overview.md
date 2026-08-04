---
title: Feature flags - Overview
source_url: https://posthog.com/docs/feature-flags
section: feature-flags
---

# Feature flags

Toggle features for cohorts or individuals to test the impact before rolling out to everyone.

## Overview

Feature flags let you toggle features on or off for specific users, groups, or percentages of traffic without redeploying code. They're the foundation for safe rollouts, A/B testing, and remote configuration.

Common use cases include:

- **Phased rollouts** — Ship to 5% of users, monitor, then gradually increase
- **Kill switches** — Instantly disable a broken feature without redeploying
- **Targeting** — Show features to specific users, teams, or organizations
- **A/B testing** — Run experiments with multivariate flags and track results
- **Remote config** — Send JSON payloads to configure behavior server-side
- **Beta programs** — Let users opt in to early access features

## All the features you expect

- Boolean flags
- Multivariate flags
- Percentage rollouts
- User and group targeting
- Server-side local evaluation
- Client-side bootstrapping
- Remote config / payloads
- Scheduled flag changes
- Feature flag dependencies
- Early access management
- Multi-project flags
- Property overrides
- Evaluation contexts

## Even better in the PostHog ecosystem

- **Experiments**: Run A/B tests powered by feature flags with statistical significance tracking
- **Session replay**: Watch recordings of users interacting with flagged features to understand impact
- **Product analytics**: Track how flagged features affect conversion, retention, and revenue
- **Error tracking**: Roll back flagged features when they cause exceptions for users
- **Surveys**: Collect feedback from users who have specific feature flags enabled
- **Data warehouse**: Query flag evaluation data alongside product data with SQL
