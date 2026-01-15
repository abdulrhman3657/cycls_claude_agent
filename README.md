# Creative Marketing Agent

A multi-agent marketing workflow powered by Claude AI and the Cycls framework. This agent orchestrates specialized subagents to analyze briefs, conduct market research, develop creative directions, and generate social media content.

## Features

- **Brief Analyzer** - Extracts and structures marketing briefs with strategic risks assessment
- **Market Researcher** - Provides market overview, competitor landscape, and audience insights
- **Creative Director** - Produces 3-4 differentiated creative directions
- **Social Media Writer** - Generates campaign routes with sample posts

## Requirements

- `cycls==0.0.2.62`
- `claude-agent-sdk`


## Usage

The agent runs a gated workflow:
1. User submits a marketing brief
2. Brief Analyzer structures the brief and asks for confirmation
3. Market Researcher provides insights with creative implications
4. Creative Director produces approved creative directions
5. Social Media Writer generates 4 campaign routes
6. User selects routes to develop further

## Architecture

The main agent coordinates 4 specialized subagents using the Claude Agent SDK's Task tool. Each subagent has a focused prompt and returns text-only responses.