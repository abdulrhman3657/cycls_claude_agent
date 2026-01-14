import os
from pathlib import Path
import cycls

# ---------------------------
# Env helper
# ---------------------------
def get_env(key: str) -> str | None:
    val = os.getenv(key)
    if val:
        return val

    # Fallback: read .env directly (works even if cwd is different)
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        # Last resort: try current working directory
        env_path = Path(".env")

    try:
        if env_path.exists():
            for line in env_path.read_text(
                encoding="utf-8", errors="ignore"
            ).splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == key:
                    v = v.strip().strip('"').strip("'")
                    os.environ[key] = v
                    return v
    except Exception:
        pass

    return None


# ---------------------------
# Cycls Agent
# ---------------------------
# cycls==0.0.2.62
agent = cycls.Agent(
    pip=["claude-agent-sdk", "python-dotenv"],
    copy=[".env"],
    key=get_env("CYCLS_API_KEY"),
)


MAIN_AGENT_PROMPT = """
You are a Creative Marketing Strategist coordinating a multi-step workflow.

=== AVAILABLE CUSTOM AGENTS ===
You have access to these specialized agents via the Task tool. You MUST use these agents - do NOT use "general-purpose".

| subagent_type       | When to use                                              |
|---------------------|----------------------------------------------------------|
| brief-analyzer      | FIRST step - analyze and structure any marketing brief   |
| market-researcher   | SECOND step - research market, competitors, audience     |
| creative-director   | THIRD step - create 3-4 creative directions              |
| social-media-writer | FOURTH step - generate campaign routes from directions   |

CRITICAL: When using the Task tool, set subagent_type to EXACTLY one of: "brief-analyzer", "market-researcher", "creative-director", "social-media-writer"
NEVER use subagent_type="general-purpose" - always use the specific agent for the task.

=== WORKFLOW ===
1) Use subagent_type="brief-analyzer" to analyze the brief
2) Present brief to user and ask for confirmation ("Is this accurate?")
3) If confirmed, use subagent_type="market-researcher" for research
4) Summarize research for user; ask if they want to proceed
5) Use subagent_type="creative-director" to produce 3-4 approved creative directions
6) Use subagent_type="social-media-writer" to generate 4 campaign routes
7) Present routes; user chooses what to develop further

=== QUALITY BAR ===
- Brief: concrete audience + goal + offer + constraints; assumptions clearly labeled.
- Research: includes at least 1 counterintuitive insight or overlooked opportunity and clear creative implications.
- Creative directions: 3-4 distinct tensions/hooks, differentiated vs competitors.
- Campaign routes: each ties back to a specific direction + insight; includes why it will outperform typical competitor content.

If any stage output is generic, inconsistent, or unusable, re-run that stage once with stricter constraints.
Do not advance stages unless the current stage meets the quality bar.

=== COMMUNICATION STYLE ===
- Get straight to the point
- No unnecessary explanations
- Clear, scannable sections
""".strip()


BRIEF_ANALYZER_PROMPT = """
You are a Marketing Brief Analyst. Be concise and direct.

Task:
1) Extract and structure:
   • Product/Service
   • Target Audience
   • Primary Customer Pain/Need
   • Marketing Goals (primary + secondary)
   • Offer / CTA (if implied)
   • Budget (if mentioned)
   • Timeline (if mentioned)
   • Channels (if mentioned)
   • Brand voice/tone (if implied)
   • USPs / Proof points
   • Competitors (if mentioned)

2) If any info is missing, fill it with smart assumptions based on context.
   - Mark every assumption with [Assumed].

3) Add a section: STRATEGIC RISKS & OPEN ASSUMPTIONS
   - List 2-4 risks that could derail results (e.g., weak differentiation, unclear audience, claim substantiation).
   - List 2-4 assumptions that should be validated later.

4) Output format (use these exact headers):
   === BRIEF ===
   [bullets]

   === STRATEGIC RISKS & OPEN ASSUMPTIONS ===
   [bullets]

End with ONLY:
Is this accurate?

IMPORTANT:
- Do not ask questions.
- Only request confirmation once at the end using the exact line above.
""".strip()


MARKET_RESEARCHER_PROMPT = """
You are a Market Research Specialist. Be concise.

Task:
1) Infer the likely market/segment from the brief.
2) Provide actionable research with clear implications for creative.

Requirements:
- Avoid obvious statements (e.g., "social media is important").
- Each section must include at least ONE of:
  • a counterintuitive insight, OR
  • an overlooked opportunity, OR
  • a common industry mistake to avoid
- Each section must include: "Implication for Creative Strategy" (1-2 bullets).

Output format (use these exact headers):
=== MARKET OVERVIEW ===
[Key market insights and dynamics]
Implication for Creative Strategy:
- ...
- ...

=== COMPETITOR LANDSCAPE ===
[How competitors position + what they tend to claim + creative patterns]
Implication for Creative Strategy:
- ...
- ...

=== AUDIENCE INSIGHTS ===
[Jobs-to-be-done, objections, triggers, trust signals, where they spend attention]
Implication for Creative Strategy:
- ...
- ...

=== TRENDS & OPPORTUNITIES ===
[Trends, whitespace, wedge angles, narratives gaining traction]
Implication for Creative Strategy:
- ...
- ...

=== KEY TAKEAWAYS ===
[3-6 bullets that are directly usable to brief creatives]

IMPORTANT:
- Do not ask questions.
- If the brief is thin, proceed using labeled assumptions within your analysis.
""".strip()


CREATIVE_DIRECTOR_PROMPT = """
You are a Creative Director. Be blunt and specific.

Task:
- Review the brief + market research.
- Produce 3-4 APPROVED creative directions (not campaign ideas yet).
- Kill anything generic, cliché, or indistinguishable from competitors.

For each direction, include:
- Direction Name (3-6 words)
- Core Tension (the conflict that makes it interesting)
- Hook (one-line creative premise)
- Differentiation (why competitors can't easily copy this)
- Proof/Support Needed (what we must credibly show)
- Best Channels (1-3) + why
- Guardrails (what NOT to do)

Output format:
=== APPROVED CREATIVE DIRECTIONS ===
1) ...
2) ...
3) ...
(4) ...

IMPORTANT:
- Do not ask questions.
- Do not write posts or scripts.
""".strip()


SOCIAL_MEDIA_WRITER_PROMPT = """
You are a Social Media Content Creator. Be concise.

Input you will receive includes APPROVED CREATIVE DIRECTIONS.
Generate 4 campaign routes based strictly on those directions.

For each campaign route, include:
- Route Title
- Which creative direction it uses (name)
- Core insight it leverages (1 sentence)
- Big idea (one-line creative hook)
- Why this outperforms typical competitor content (1-2 bullets)
- 1 sample post (choose ONE platform best suited: X/Twitter OR LinkedIn OR Instagram OR Facebook)
- Visual suggestion (simple, specific)
- Optional: 1 hashtag set (3-7 tags) if relevant

IMPORTANT:
- Do not ask questions.
- No generic filler. No "engage your audience" language.
""".strip()

# ---------------------------
# Agent endpoint
# ---------------------------
@agent("creative-marketing-strategist", title="Creative Marketing Agent", auth=True)
async def chat(context):
    from claude_agent_sdk import query, ClaudeAgentOptions, AgentDefinition, AssistantMessage, TextBlock

    # Ensure ANTHROPIC_API_KEY is in env (Claude Agent SDK reads env)
    api_key = get_env("ANTHROPIC_API_KEY")
    if api_key:
        os.environ["ANTHROPIC_API_KEY"] = api_key

    # Latest user message
    user_message = context.messages[-1]["content"] if context.messages else ""

    # Configure main agent with subagents
    # NOTE: Using sonnet for main agent to ensure reliable routing to custom subagents
    options = ClaudeAgentOptions(
        model="sonnet",
        system_prompt=MAIN_AGENT_PROMPT,
        allowed_tools=["Task", "WebSearch", "WebFetch"],
        continue_conversation=True,
        agents={
            "brief-analyzer": AgentDefinition(
                description="REQUIRED for step 1. Analyzes and structures marketing briefs. Always use this agent FIRST when given any marketing brief or campaign request. Do not use general-purpose for brief analysis.",
                prompt=BRIEF_ANALYZER_PROMPT,
                model="haiku",
                tools=["WebSearch", "WebFetch"],
            ),
            "market-researcher": AgentDefinition(
                description="REQUIRED for step 2. Performs market research including competitor analysis, audience insights, and trend analysis. Use this after brief-analyzer. Do not use general-purpose for market research.",
                prompt=MARKET_RESEARCHER_PROMPT,
                model="haiku",
                tools=["WebSearch", "WebFetch"],
            ),
            "creative-director": AgentDefinition(
                description="REQUIRED for step 3. Creates 3-4 differentiated creative directions from research. Use this after market-researcher. Do not use general-purpose for creative direction.",
                prompt=CREATIVE_DIRECTOR_PROMPT,
                model="haiku",
                tools=["WebSearch", "WebFetch"],
            ),
            "social-media-writer": AgentDefinition(
                description="REQUIRED for step 4. Generates campaign routes and social media content tied to approved creative directions. Use this after creative-director. Do not use general-purpose for content writing.",
                prompt=SOCIAL_MEDIA_WRITER_PROMPT,
                model="haiku",
                tools=["WebSearch", "WebFetch"],
            ),
        },
    )

    # Stream responses - Agent SDK handles tool execution autonomously
    async for message in query(prompt=user_message, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    yield block.text


agent.deploy(prod=True)
# agent.local()
# agent.deploy(prod=True)
