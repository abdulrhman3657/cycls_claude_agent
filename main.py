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
2. Once confirmed, delegate to 'market-researcher' → get 4 ideas
3. Present the 4 ideas and ask user to choose one
4. Once chosen, delegate to 'social-media-writer' with the chosen idea

Communication style:
- Get straight to the point
- No unnecessary explanations or commentary
- Present information clearly and efficiently
- Skip verbose introductions and transitions

IMPORTANT:
- Start with brief-analyzer for initial requests
- Only proceed to market-researcher after brief confirmation
- Only proceed to social-media-writer after user chooses an idea
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
        allowed_tools=["Task"],  # used for subagent invocation
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
                description="Expert market research specialist for competitor analysis. Use for analyzing competitors, market trends, and generating marketing ideas.",
                prompt=(
                    "You are a Market Research Specialist. Be concise.\n\n"
                    "Task:\n"
                    "1. Analyze the brief and target market\n"
                    "2. Consider:\n"
                    "   • Competitor strategies & tactics\n"
                    "   • Market trends\n"
                    "   • Successful campaigns\n"
                    "   • Positioning & USPs\n"
                    "   • Marketing channels\n\n"
                    "3. Generate exactly 4 distinct marketing ideas:\n"
                    "   • Each idea must be completely different from the others\n"
                    "   • Base ideas on market insights and opportunities\n"
                    "   • Cover: differentiation, trends, channels, tactics\n"
                    "   • Number each idea (1-4)\n"
                    "   • Make each idea actionable and specific\n\n"
                    "4. Output format:\n"
                    "   [Brief market context]\n\n"
                    "   Idea 1: [Title]\n"
                    "   [Description]\n\n"
                    "   Idea 2: [Title]\n"
                    "   [Description]\n\n"
                    "   Idea 3: [Title]\n"
                    "   [Description]\n\n"
                    "   Idea 4: [Title]\n"
                    "   [Description]\n\n"
                    "IMPORTANT: Do not ask questions. Generate all 4 ideas directly based on the brief."
                ),
                model="claude-haiku-4-5",
            ),
            "social-media-writer": AgentDefinition(
                description="Social media content creator specializing in engaging posts. Use for generating social media content based on chosen marketing idea.",
                prompt=(
                    "You are a Social Media Content Creator. Be concise.\n\n"
                    "Task:\n"
                    "1. You will receive a chosen marketing idea\n"
                    "2. Generate exactly 4 social media posts for these platforms (in order):\n"
                    "   • Twitter/X: Punchy, hashtags, 280 chars\n"
                    "   • LinkedIn: Professional, value-driven\n"
                    "   • Instagram: Visual hooks, emojis, caption\n"
                    "   • Facebook: Conversational, engaging\n\n"
                    "3. Each post must include:\n"
                    "   • Strong hook\n"
                    "   • Relevant hashtags\n"
                    "   • Visual/video suggestion\n"
                    "   • Platform-specific formatting\n\n"
                    "4. Output format:\n"
                    "   === TWITTER/X ===\n"
                    "   [Post content]\n"
                    "   Visual: [suggestion]\n\n"
                    "   === LINKEDIN ===\n"
                    "   [Post content]\n"
                    "   Visual: [suggestion]\n\n"
                    "   === INSTAGRAM ===\n"
                    "   [Post content]\n"
                    "   Visual: [suggestion]\n\n"
                    "   === FACEBOOK ===\n"
                    "   [Post content]\n"
                    "   Visual: [suggestion]\n\n"
                    "IMPORTANT: Do not ask questions. Generate all 4 posts directly based on the chosen idea."
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

        # Check for subagent invocation in message content
        if hasattr(message, 'content') and message.content:
            for block in message.content:
                if getattr(block, 'type', None) == 'tool_use' and getattr(block, 'name', None) == 'Task':
                    subagent_type = block.input.get('subagent_type', 'unknown')
                    print(f"\n Subagent invoked: {subagent_type}")

        # Check if this message is from within a subagent's context
        if hasattr(message, 'parent_tool_use_id') and message.parent_tool_use_id:
            print("  (running inside subagent)")

        # Stream text chunks
        for text in extract_stream_text(message):
            yield text


# agent.deploy(prod=False)
agent.local()
# agent.deploy(prod=True)
