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
| creative-director   | THIRD step - create creative directions + campaign routes|
| social-media-writer | FOURTH step - generate 4 ready-to-paste posts            |

CRITICAL: When using the Task tool, set subagent_type to EXACTLY one of: "brief-analyzer", "market-researcher", "creative-director", "social-media-writer"
NEVER use subagent_type="general-purpose" - always use the specific agent for the task.

=== WORKFLOW ===
1) Use subagent_type="brief-analyzer" to analyze the brief
2) Present brief to user and ask for confirmation ("Is this accurate?")
3) If confirmed, use subagent_type="market-researcher" for research
4) Summarize research for user; ask if they want to proceed
5) Use subagent_type="creative-director" to produce 3-4 approved creative directions + campaign routes
6) Present routes; user chooses what to develop further
7) Use subagent_type="social-media-writer" to generate 4 ready-to-paste posts for selected routes

=== QUALITY BAR ===
- Brief: concrete audience + goal + offer + constraints; assumptions clearly labeled.
- Research: includes at least 1 counterintuitive insight or overlooked opportunity and clear creative implications.
- Creative directions: 3-4 distinct tensions/hooks, differentiated vs competitors.
- Campaign routes: each ties back to a specific direction + insight; includes why it will outperform typical competitor content.
- Posts: 4 ready-to-paste posts, one per route, platform-appropriate.

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
- Produce 3-4 APPROVED creative directions.
- Kill anything generic, cliché, or indistinguishable from competitors.
- For each direction, generate a campaign route.

For each direction, include:
- Direction Name (3-6 words)
- Core Tension (the conflict that makes it interesting)
- Hook (one-line creative premise)
- Differentiation (why competitors can't easily copy this)
- Proof/Support Needed (what we must credibly show)
- Best Channels (1-3) + why
- Guardrails (what NOT to do)

For each campaign route, include:
- Route Title
- Which creative direction it uses (name)
- Core insight it leverages (1 sentence)
- Big idea (one-line creative hook)
- Why this outperforms typical competitor content (1-2 bullets)
- Visual suggestion (simple, specific)
- Optional: 1 hashtag set (3-7 tags) if relevant

Output format:
=== APPROVED CREATIVE DIRECTIONS ===
1) ...
2) ...
3) ...
(4) ...

=== CAMPAIGN ROUTES ===
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

Input you will receive includes APPROVED CREATIVE DIRECTIONS, CAMPAIGN ROUTES, and the USER'S CHOSEN ROUTE.
Generate exactly 4 ready-to-paste social media posts for the chosen route.

CRITICAL:
- All 4 posts must be for the SAME chosen route
- Each post must explore a DIFFERENT ANGLE of that route (e.g., problem-focused, benefit-focused, social proof, urgency, storytelling, question-based, contrarian take)
- No two posts should feel similar - vary the hook, tone, and approach

For each post:
- Choose ONE platform best suited: X/Twitter OR LinkedIn OR Instagram OR Facebook
- Write the complete post text ready to copy and paste
- Include hashtags if relevant (3-7 tags)
- State the angle used

Output format:
=== POST 1 (Platform: [platform]) ===
[Angle: angle name]
[Full post text ready to paste]

=== POST 2 (Platform: [platform]) ===
[Angle: angle name]
[Full post text ready to paste]

=== POST 3 (Platform: [platform]) ===
[Angle: angle name]
[Full post text ready to paste]

=== POST 4 (Platform: [platform]) ===
[Angle: angle name]
[Full post text ready to paste]

IMPORTANT:
- Do not ask questions.
- No explanations, no commentary, no suggestions.
- Just the 4 posts ready to copy and paste.
- No generic filler. No "engage your audience" language.
- Each post MUST have a distinct angle - if they feel similar, rewrite.
""".strip()

# ---------------------------
# Agent endpoint
# ---------------------------
@agent("creative-marketing-strategist", title="Creative Marketing Agent", auth=True)
async def chat(context):
    from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, AgentDefinition, AssistantMessage, TextBlock

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
        # max_budget_usd=0.50,  # Cost ceiling to prevent runaway token usage
        # max_turns=15,  # Limit conversation turns
        agents={
            "brief-analyzer": AgentDefinition(
                description="REQUIRED for step 1. Analyzes and structures marketing briefs. Always use this agent FIRST when given any marketing brief or campaign request. Do not use general-purpose for brief analysis.",
                prompt=BRIEF_ANALYZER_PROMPT,
                model="sonnet",
                tools=[],
            ),
            "market-researcher": AgentDefinition(
                description="REQUIRED for step 2. Performs market research including competitor analysis, audience insights, and trend analysis. Use this after brief-analyzer. Do not use general-purpose for market research.",
                prompt=MARKET_RESEARCHER_PROMPT,
                model="sonnet",
                tools=["WebSearch", "WebFetch"],
            ),
            "creative-director": AgentDefinition(
                description="REQUIRED for step 3. Creates 3-4 differentiated creative directions AND campaign routes from research. Use this after market-researcher. Do not use general-purpose for creative direction.",
                prompt=CREATIVE_DIRECTOR_PROMPT,
                model="sonnet",
                tools=[],
            ),
            "social-media-writer": AgentDefinition(
                description="REQUIRED for step 4. Generates 4 ready-to-paste social media posts tied to approved campaign routes. Use this after creative-director and user route selection. Do not use general-purpose for content writing.",
                prompt=SOCIAL_MEDIA_WRITER_PROMPT,
                model="sonnet",
                tools=["WebSearch", "WebFetch"],
            ),
        },
    )

    # Buffer for main agent text (to handle text that precedes Task delegation)
    main_agent_buffer = []

    # Stream responses using ClaudeSDKClient for bidirectional streaming
    async with ClaudeSDKClient(options=options) as client:
        await client.query(user_message)

        async for message in client.receive_response():
            msg_type = type(message).__name__

            # DEBUG - log all message types and attributes
            print(f"\n[DEBUG] msg_type={msg_type}")
            print(f"[DEBUG] message attrs: {[a for a in dir(message) if not a.startswith('_')]}")

            if isinstance(message, AssistantMessage):
                parent_id = getattr(message, "parent_tool_use_id", None)
                print(f"[DEBUG] parent_tool_use_id={parent_id}")
                print(f"[DEBUG] buffer_len={len(main_agent_buffer)}")
                print(f"[DEBUG] content blocks: {len(message.content)}")
                for i, block in enumerate(message.content):
                    block_type = type(block).__name__
                    print(f"[DEBUG]   block[{i}]: {block_type}")
                    if block_type == "ToolUseBlock":
                        print(f"[DEBUG]     tool_name={getattr(block, 'name', None)}")
                        tool_input = getattr(block, "input", {}) or {}
                        if block.name == "Task":
                            print(f"[DEBUG]     subagent_type={tool_input.get('subagent_type')}")
            else:
                # Log non-AssistantMessage details
                print(f"[DEBUG] non-assistant message: {message}")

            # Skip non-assistant messages
            if not isinstance(message, AssistantMessage):
                continue

            parent_id = getattr(message, "parent_tool_use_id", None)
            content = message.content or []

            # Check if this is a Task delegation
            task_info = None
            for block in content:
                if type(block).__name__ == "ToolUseBlock" and block.name == "Task":
                    tool_input = getattr(block, "input", {}) or {}
                    subagent = tool_input.get("subagent_type", "unknown")
                    description = tool_input.get("description", "")
                    prompt = tool_input.get("prompt", "")
                    task_info = (subagent, description, prompt)

            # Main agent messages (parent_id is None)
            if parent_id is None:
                if task_info:
                    # Task delegation - format buffered text + delegation + prompt as code block
                    subagent, description, prompt = task_info
                    buffered = "".join(main_agent_buffer).strip()
                    main_agent_buffer.clear()

                    # Build the delegation block
                    parts = []
                    if buffered:
                        parts.append(f"💭 {buffered}")
                    parts.append(f"🔄 Delegating to: {subagent} - {description}")
                    if prompt:
                        parts.append(f"\n📝 Prompt to subagent:\n{prompt}")

                    yield f"\n```\n{chr(10).join(parts)}\n```\n"
                    continue

                # Collect main agent text into buffer (might precede a Task)
                for block in content:
                    if isinstance(block, TextBlock):
                        main_agent_buffer.append(block.text)
                continue

            # Messages from subagents (parent_id is set)
            # Flush any buffered main agent text (without code block - it's just context)
            if main_agent_buffer:
                buffered = "".join(main_agent_buffer).strip()
                main_agent_buffer.clear()
                if buffered:
                    yield f"\n{buffered}\n\n"

            # Stream subagent output normally
            for block in content:
                if isinstance(block, TextBlock):
                    yield block.text

    # Flush any remaining buffered text at the end (main agent's final response)
    if main_agent_buffer:
        buffered = "".join(main_agent_buffer).strip()
        if buffered:
            yield buffered


agent.deploy(prod=False)
# agent.local()
# agent.deploy(prod=True)
