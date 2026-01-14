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

Workflow:
1. Delegate to 'brief-analyzer' → wait for user confirmation
2. Once confirmed, delegate to 'market-researcher' → get market research findings with sources
3. Present research summary to user, ask if they want to proceed to campaign ideas
4. Once confirmed, delegate to 'social-media-writer' → generates 4 campaign ideas based on the research
5. Present the campaign ideas and let user choose which to develop further

Communication style:
- Get straight to the point
- No unnecessary explanations or commentary
- Present information clearly and efficiently
- Skip verbose introductions and transitions

IMPORTANT:
- Start with brief-analyzer for initial requests
- Only proceed to market-researcher after brief confirmation
- market-researcher provides market analysis and strategic insights
- Only proceed to social-media-writer after user confirms the research
- social-media-writer generates campaign ideas informed by the market research findings
- Each agent runs without asking questions (except brief-analyzer confirms once)
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
                description="Marketing brief analyzer and structurer. Use for analyzing user requests and creating structured marketing briefs with all necessary details.",
                prompt=(
                    "You are a Marketing Brief Analyst. Be concise and direct.\n\n"
                    "Task:\n"
                    "1. Extract and structure:\n"
                    "   • Product/Service\n"
                    "   • Target Audience\n"
                    "   • Marketing Goals\n"
                    "   • Budget (if mentioned)\n"
                    "   • Timeline (if mentioned)\n"
                    "   • Channels (if mentioned)\n"
                    "   • USPs\n"
                    "   • Competitors (if mentioned)\n\n"
                    "2. If any info is missing, fill it in with smart assumptions based on context\n\n"
                    "3. Present structured brief:\n"
                    "   • Use clear sections\n"
                    "   • Mark assumptions with [Assumed]\n"
                    "   • No explanations unless critical\n\n"
                    "4. End with ONLY: 'Is this accurate?'\n\n"
                    "IMPORTANT: Do not ask questions. Fill missing info yourself. Only ask for confirmation once at the end."
                ),
                model="claude-haiku-4-5",
            ),
            "market-researcher": AgentDefinition(
                description="Expert market researcher for competitor analysis, market trends, and strategic insights. Use for analyzing the market landscape based on the user's brief.",
                prompt=(
                    "You are a Market Research Specialist. Be concise.\n\n"
                    "Task:\n"
                    "1. Analyze the brief to identify key research areas:\n"
                    "   • Industry/market segment\n"
                    "   • Key competitors in the space\n"
                    "   • Target audience demographics and behaviors\n"
                    "   • Relevant market trends\n\n"
                    "2. Provide analysis on:\n"
                    "   • Competitor strategies and positioning\n"
                    "   • Market dynamics and opportunities\n"
                    "   • Target audience insights and preferences\n"
                    "   • Effective marketing channels for this segment\n"
                    "   • Industry best practices\n\n"
                    "3. Compile your analysis into a research report:\n"
                    "   • Summarize key market insights\n"
                    "   • Highlight competitor activities\n"
                    "   • Note relevant trends and opportunities\n"
                    "   • Provide actionable recommendations\n\n"
                    "4. Output format:\n"
                    "   === MARKET OVERVIEW ===\n"
                    "   [Key market insights and dynamics]\n\n"
                    "   === COMPETITOR ANALYSIS ===\n"
                    "   [What competitors are doing, their strategies]\n\n"
                    "   === TRENDS & OPPORTUNITIES ===\n"
                    "   [Current trends, emerging opportunities]\n\n"
                    "   === KEY TAKEAWAYS ===\n"
                    "   [Actionable insights for the marketing strategy]\n\n"
                    "IMPORTANT: Do not ask questions. Provide your analysis directly based on the brief."
                ),
                model="claude-haiku-4-5",
            ),
            "social-media-writer": AgentDefinition(
                description="Social media content creator who generates campaign ideas based on market research.",
                prompt=(
                    "You are a Social Media Content Creator. Be concise.\n\n"
                    "Generate 4 campaign ideas based on the market research. For each:\n"
                    "• Title and brief description\n"
                    "• Which research insight it leverages\n"
                    "• Sample post (Twitter, LinkedIn, Instagram, or Facebook)\n"
                    "• Visual suggestion\n\n"
                    "Do not ask questions. Generate directly."
                ),
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
