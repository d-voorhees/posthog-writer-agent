---
title: Schema management
source_url: https://posthog.com/docs/product-analytics/schema-management
section: product-analytics
---

# Schema management

Schema management lets you define and enforce the structure of your events using typed property groups. This helps document expected properties, provides type safety in your code, and makes your analytics implementation more maintainable.

## Creating events

Event definitions can be created before any events are actually captured. This is useful for:

- Defining your event schema before writing instrumentation code
- Generating typed definitions for events that haven't been captured yet
- Documenting expected events for your team
- Ensuring consistency across your codebase from day one

To create an event:

1. Go to **Data Management** > **Events**
2. Click **Create event**
3. Enter the event name (e.g., "user_signed_up")
4. Optionally add a description, owner, and tags

**Note**: Event names cannot be changed after creation, so choose carefully. Events created this way show "-" for First seen and Last seen until the first event is actually captured.

## Creating property groups

Property groups are reusable collections of typed properties that can be attached to one or more events.

1. Navigate to **Data Management** > **Property Groups**
2. Click **New Property Group**
3. Give the group a name (e.g., `Order Information`)
4. Add properties with their types: Name, Type (String, Number, Boolean, or Object), Required, and Description

Property groups can be reused across multiple events, making it easy to maintain consistent schemas.

## Adding schemas to events

Once property groups and events exist, attach property groups to events:

1. Go to **Data Management** > **Events**
2. Select an event
3. In the **Schema** section, click **Add Property Group**
4. Choose from existing property groups or create a new one

Events can have multiple property groups, and each group's properties are included in the generated types.

## Downloading your schema with the CLI

The PostHog CLI generates language definitions from configured schemas.

Install: `npm install -g @posthog/cli`

Authenticate: `posthog-cli login` (opens browser to authorize)

Download schema (currently experimental, `exp` prefix will be removed once stable):

```
posthog-cli exp schema pull
```

The CLI fetches event schemas, prompts for an output file path, generates typed definitions, and updates `posthog.json` with the schema hash. Choose an output location accessible from application code (e.g., `src/lib/posthog-typed.ts`).

Both `posthog.json` and `posthog-typed.<extension>` should be committed to version control so the whole team has consistent types and can track schema changes over time.

Check sync status: `posthog-cli exp schema status`

## Using typed events in your app

Once the schema is downloaded, import and use the generated PostHog client:

```typescript
import posthog from './posthog-typed'

posthog.capture('button_clicked', {
  button_name: 'signup',      // Type-checked
  click_count: 5,             // Type-checked
})

// Bypass type checking when needed:
posthog.captureRaw('dynamic_event', { whatever: 'data' })
```

This provides type safety (properties validated against schema), autocomplete, inline documentation of required properties, and flexibility (standard SDK functionality remains available for gradual migration).

## Best practices

- **Define events upfront**: create event definitions before implementing instrumentation for type safety from day one
- **Start with your most important events**: define schemas for critical conversion events first
- **Use descriptive property groups**: name groups by purpose (e.g., "E-commerce Properties", "User Context")
- **Don't over-schema**: not every event needs a schema, use them where type safety adds value
- **Commit generated types**: always commit `posthog.json` and `posthog-typed.<extension>` to version control
