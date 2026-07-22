---
name: kthais-nextjs
description: Next.js conventions and patterns for KTHAIS projects. Use when building or modifying Next.js apps in the KTHAIS ecosystem.
---

# KTHAIS Next.js

Conventions for Next.js projects in the KTHAIS organization.

## When to use

Apply this skill when creating or changing Next.js applications under KTHAIS.

## Guidelines

<!-- Replace with organization-specific conventions. -->

- Prefer the App Router.
- Keep `page.tsx` thin: default-export a component from `@/components/...` when that pattern is used in the repo.
- Follow existing project structure and TypeScript settings.
- Prefer server components by default; add `"use client"` only when needed.
