---
title: Getting started with Product Analytics
source_url: https://posthog.com/docs/product-analytics/start-here
section: product-analytics
---

# Getting started with Product Analytics

## Capture your first event

To get started with Product Analytics, the first step is to install the PostHog SDK to start capturing events within your application.

Autocapture is on by default. Pageviews, clicks, form submissions, and session data are tracked automatically.

Call `posthog.capture()` to capture custom events and properties:

```javascript
posthog.capture('signup_completed', { plan: 'pro' })
```

SDKs are available for Web, Next.js, React Native, React, Node.js, Flutter, Python, PHP, Ruby, Go, Android, iOS, Java, Rust, Elixir, .NET, and more, plus a direct API.

For a customized setup, run the AI wizard with one command to automatically set up autocapture, custom events, and more:

```
npx @posthog/wizard
```

## Create insights and dashboards

With PostHog connected, the app automatically sends events. Query the full event stream to analyze product data and user behavior. Combine related events into actions to create any kind of metric needed. Create insights and dashboards to visualize trends, funnels, and retention. Event data can also be queried with SQL for more flexibility.

## Identify users and groups

Linking events to specific users enables building a full picture of how they're using the product across sessions, devices, and platforms:

```javascript
posthog.identify(
  'max@hedgehogmail.com',  // user's unique identifier
  { name: 'Max Hedgehog' } // additional person properties
);
```

Events can also be aggregated into groups to track organization behavior at the company, team, or project level:

```javascript
posthog.group(
  'company',
  'company_id_in_your_db',
  { name: 'PostHog' } // additional group properties
);
```

## Analyze data with MCP and AI

Connect the PostHog MCP server to let agents query data and run analysis. PostHog AI can also answer questions, create insights, and build dashboards directly.

## Integrate your tech stack

- **Session Replay**: Click any data point in funnels, retention charts, or user paths and land directly in a playlist of session recordings for the users behind that number. Session Replay runs on the same events already captured.
- **Feature Flags**: Roll out or revert code updates using product events as release conditions.
- **Data Warehouse**: Use the Data Warehouse as a single source of truth for customer data, syncing product data with external sources like Stripe, HubSpot, Zendesk, and more.

## Pricing

- No credit card required to start
- First 1 million events per month are free
- Above 1 million, usage-based pricing at $0.000015/event with discounts
- Billing limits can be set to avoid surprise charges
