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


# ---------------------------
# Claude session store (in-memory)
# ---------------------------
# NOTE:
# - Works great for agent.local() and single-container deploys.
# - If you scale to multiple replicas, use Redis/DB for shared session storage.
CLAUDE_SESSIONS: dict[str, str] = {}


def conversation_key_from_context(context) -> str:
    """
    Derive a stable conversation key.
    Best: authenticated user id (if auth=True in Cycls and JWT user exists).
    Otherwise: read a client-provided conversation_id from message metadata (recommended).
    Fallback: a single shared key (fine for local dev, bad for multi-user).
    """
    # 1) Authenticated user id (best)
    if getattr(context, "user", None) and getattr(context.user, "id", None):
        return f"user:{context.user.id}"

    # 2) Client-provided conversation id (recommended for auth=False)
    last = context.messages[-1] if context.messages else {}
    metadata = last.get("metadata") or {}
    conv_id = metadata.get("conversation_id")
    if conv_id:
        return f"conv:{conv_id}"

    # 3) Weak fallback (all anon users share one session)
    return "anon:default"


def extract_stream_text(message):
    """
    Best-effort extraction of text from Claude Agent SDK streamed message objects.
    Yields text chunks only; ignores init/system metadata.
    """
    if hasattr(message, "text") and message.text:
        yield message.text
        return

    if hasattr(message, "content"):
        content = message.content
        if isinstance(content, str) and content:
            yield content
            return
        if isinstance(content, list):
            for block in content:
                if hasattr(block, "text") and block.text:
                    yield block.text
                elif isinstance(block, dict) and block.get("text"):
                    yield block["text"]
            return

    if isinstance(message, str) and message:
        yield message


MAIN_AGENT_PROMPT = """
You are a Creative Marketing Strategist coordinating a multi-step workflow.

Core principles:
- You are responsible for output quality and strategic coherence.
- Prefer specificity over generic marketing talk.
- Ensure a clear chain: Brief → Research Insights → Creative Directions → Campaign Routes.
- If any stage output is generic, inconsistent, or unusable, re-run that stage once with stricter constraints.
- Do not advance stages unless the current stage meets the quality bar.

Workflow (gated):
1) Delegate to 'brief-analyzer'
2) Present brief to user and ask for confirmation ("Is this accurate?")
3) If confirmed, delegate to 'market-researcher'
4) Summarize research for user; ask if they want to proceed
5) Delegate to 'creative-director' to produce 3-4 approved creative directions
6) Delegate to 'social-media-writer' to generate 4 campaign routes based on approved directions
7) Present routes; user chooses what to develop further

Quality bar to advance:
- Brief: concrete audience + goal + offer + constraints; assumptions clearly labeled.
- Research: includes at least 1 counterintuitive insight or overlooked opportunity and clear creative implications.
- Creative directions: 3-4 distinct tensions/hooks, differentiated vs competitors.
- Campaign routes: each ties back to a specific direction + insight; includes why it will outperform typical competitor content.

Communication style:
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
@agent("marketing-agent", title="Creative Marketing Agent", auth=False)
async def chat(context):
    from claude_agent_sdk import query, ClaudeAgentOptions, AgentDefinition

    # Ensure ANTHROPIC_API_KEY is in env (Claude Agent SDK reads env)
    api_key = get_env("ANTHROPIC_API_KEY")
    if api_key:
        os.environ["ANTHROPIC_API_KEY"] = api_key

    # Latest user message
    user_message = context.messages[-1]["content"] if context.messages else ""

    # Session resumption
    convo_key = conversation_key_from_context(context)
    resume_id = CLAUDE_SESSIONS.get(convo_key)

    # Configure main agent + subagent
    options = ClaudeAgentOptions(
        model="claude-haiku-4-5",
        system_prompt=MAIN_AGENT_PROMPT,
        allowed_tools=["Task"],
        agents={
            "brief-analyzer": AgentDefinition(
                description="Marketing brief analyzer and structurer.",
                prompt=BRIEF_ANALYZER_PROMPT,
                model="claude-haiku-4-5",
            ),
            "market-researcher": AgentDefinition(
                description="Market research specialist for competitor/audience/trends and creative implications.",
                prompt=MARKET_RESEARCHER_PROMPT,
                model="claude-haiku-4-5",
            ),
            "creative-director": AgentDefinition(
                description="Creative Director who approves 3-4 differentiated creative directions from research.",
                prompt=CREATIVE_DIRECTOR_PROMPT,
                model="claude-haiku-4-5",
            ),
            "social-media-writer": AgentDefinition(
                description="Social media writer who generates campaign routes tied to approved creative directions.",
                prompt=SOCIAL_MEDIA_WRITER_PROMPT,
                model="claude-haiku-4-5",
            ),
        },        
        # Resume prior session if known (memory)
        resume=resume_id,
    )

    async for message in query(prompt=user_message, options=options):

        # print(message) # dump all of the output

        # Capture session_id from init system message (official pattern)
        if hasattr(message, "subtype") and message.subtype == "init":
            sid = (getattr(message, "data", None) or {}).get("session_id")
            if sid:
                CLAUDE_SESSIONS[convo_key] = sid
            continue  # don't stream init metadata

        # Skip user-role messages (these are internal prompts to subagents)
        if hasattr(message, "role") and message.role == "user":
            continue

        # Skip tool_use messages (main agent delegating to subagents)
        if hasattr(message, "content") and message.content:
            is_tool_use_only = True
            for block in message.content:
                block_type = getattr(block, "type", None)
                if block_type == "tool_use":
                    if getattr(block, "name", None) == "Task":
                        subagent_type = block.input.get("subagent_type", "unknown")
                        print(f"\n Subagent invoked: {subagent_type}")
                elif block_type == "text":
                    is_tool_use_only = False
            if is_tool_use_only and any(
                getattr(b, "type", None) == "tool_use" for b in message.content
            ):
                continue

        # Skip tool_result messages (internal responses)
        if hasattr(message, "type") and message.type == "tool_result":
            continue

        # Check if this message is from within a subagent's context
        if hasattr(message, "parent_tool_use_id") and message.parent_tool_use_id:
            print("  (running inside subagent)")

        # Stream text chunks
        for text in extract_stream_text(message):
            yield text


# agent.deploy(prod=False)
agent.local()
# agent.deploy(prod=True)
