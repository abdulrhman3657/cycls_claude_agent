import os
from pathlib import Path
import cycls


# Env helper
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


# cycls==0.0.2.62
agent = cycls.Agent(
    pip=["anthropic", "claude-agent-sdk", "python-dotenv"],
    copy=[".env"],
    key=get_env("CYCLS_API_KEY")
)

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


@agent("marketing-agent", title="Creative Marketing Agent", auth=False)
async def chat(context):
    from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, AgentDefinition, AssistantMessage, TextBlock
    import os

    # Ensure ANTHROPIC_API_KEY is in environment (Claude Agent SDK reads from env)
    api_key = get_env("ANTHROPIC_API_KEY")
    if api_key:
        os.environ["ANTHROPIC_API_KEY"] = api_key

    # Get the user's latest message
    user_message = context.messages[-1]["content"] if context.messages else ""

    # Configure main marketing agent with subagent definitions
    options = ClaudeAgentOptions(
        model="claude-haiku-4-5-20251001",
        system_prompt=MAIN_AGENT_PROMPT,
        # Task tool is required for subagent invocation
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
                model="claude-haiku-4-5-20251001",
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
                model="claude-haiku-4-5-20251001",
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
                model="claude-haiku-4-5-20251001",
            ),
        },
    )

    # Use ClaudeSDKClient for conversation memory
    # ClaudeSDKClient maintains session state across queries in the same session
    async with ClaudeSDKClient(options=options) as client:
        # Send all previous messages to rebuild conversation history
        for msg in context.messages[:-1]:  # All messages except the current one
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content and role == "user":
                # Send previous user messages to rebuild context
                await client.query(content)
                # Drain assistant responses (don't yield them, just rebuild state)
                async for _ in client.receive_response():
                    pass

        # Send the current user message
        await client.query(user_message)

        # Stream the response
        async for message in client.receive_response():
            # Check for subagent invocation in message content
            if hasattr(message, 'content') and message.content:
                for block in message.content:
                    if getattr(block, 'type', None) == 'tool_use' and getattr(block, 'name', None) == 'Task':
                        subagent_type = block.input.get('subagent_type', 'unknown')
                        print(f"\n🤖 Subagent invoked: {subagent_type}")

            # Check if this message is from within a subagent's context
            if hasattr(message, 'parent_tool_use_id') and message.parent_tool_use_id:
                print("  (running inside subagent)")

            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        yield block.text
            elif hasattr(message, 'text'):
                yield message.text
            elif isinstance(message, str):
                yield message


# agent.deploy(prod=False)
agent.local()
# agent.deploy(prod=True)
