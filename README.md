# Creative Marketing Agent

A multi-agent marketing workflow powered by Claude AI and the Cycls framework. This agent orchestrates specialized subagents to analyze briefs, conduct market research, develop creative directions, and generate social media content.

## Features

- **Brief Analyzer** - Extracts and structures marketing briefs with strategic risks assessment
- **Market Researcher** - Provides market overview, competitor landscape, audience insights, and trends with creative implications
- **Creative Director** - Produces 3-4 differentiated creative directions with campaign routes
- **Social Media Writer** - Generates 4 ready-to-paste social media posts

## Requirements

- `cycls==0.0.2.62`
- `claude-agent-sdk`


## Usage

The agent runs a gated workflow with quality checks at each stage:

1. **Brief Analysis** - User submits a marketing brief; Brief Analyzer structures it with assumptions marked and strategic risks identified; asks for confirmation
2. **Market Research** - Market Researcher provides insights with counterintuitive findings and creative implications for each section
3. **Creative Direction** - Creative Director produces 3-4 approved directions with campaign routes; user selects which to develop
4. **Content Generation** - Social Media Writer generates 4 ready-to-paste posts, one per campaign route

If any stage output is generic or unusable, the workflow re-runs that stage with stricter constraints.

## Architecture

The main agent (Sonnet) coordinates 4 specialized subagents via the Claude Agent SDK's Task tool:

| Subagent | Model | Tools | Purpose |
|----------|-------|-------|---------|
| brief-analyzer | Sonnet | None | Structure briefs, identify risks |
| market-researcher | Sonnet | WebSearch, WebFetch | Research market, competitors, audience |
| creative-director | Sonnet | None | Create directions and campaign routes |
| social-media-writer | Sonnet | WebSearch, WebFetch | Generate platform-specific posts |

The main agent has access to `Task`, `WebSearch`, and `WebFetch` tools and enforces a quality bar before advancing stages.