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
You are a Creative Marketing Strategist. Be concise and direct.

Workflow:
1. Delegate to 'brief-analyzer' → wait for user confirmation
2. Delegate to 'market-researcher' → analyze findings
3. Generate exactly 4 distinct marketing ideas:
   • Each idea must be different from the others
   • Cover: differentiation, trends, channels, tactics
   • Based on research gaps and opportunities
4. Present ideas concisely (numbered list)
5. Ask: "Generate social media posts?"
6. If yes → delegate to 'social-media-writer'

Communication style:
- Get straight to the point
- No unnecessary explanations or commentary
- Present information clearly and efficiently
- Skip verbose introductions and transitions

IMPORTANT:
- Start with brief-analyzer for initial requests
- Only proceed after brief confirmation
- Generate exactly 4 distinct ideas
- Only use social-media-writer after user confirms
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
        model="claude-sonnet-4-5",
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
                    "2. Fill missing info with smart assumptions\n\n"
                    "3. Present structured brief:\n"
                    "   • Use clear sections\n"
                    "   • Mark assumptions with [Assumed]\n"
                    "   • No explanations unless critical\n\n"
                    "4. End with: 'Is this accurate?'\n\n"
                    "Be direct. No unnecessary text."
                ),
                model="sonnet",
            ),
            "market-researcher": AgentDefinition(
                description="Expert market research specialist for competitor analysis. Use for researching competitors, market trends, and industry insights.",
                prompt=(
                    "You are a Market Research Specialist. Be concise.\n\n"
                    "Task:\n"
                    "1. Research competitors via web search\n"
                    "2. Find:\n"
                    "   • Competitor strategies & tactics\n"
                    "   • Market trends\n"
                    "   • Successful campaigns\n"
                    "   • Positioning & USPs\n"
                    "   • Marketing channels\n\n"
                    "3. Report format:\n"
                    "   • Key findings per competitor\n"
                    "   • Trends & opportunities\n"
                    "   • Strategy gaps\n"
                    "   • Sources (brief citations)\n\n"
                    "Be direct. Skip fluff. Focus on actionable insights."
                ),
                tools=["WebSearch", "WebFetch"],
                model="sonnet",
            ),
            "social-media-writer": AgentDefinition(
                description="Social media content creator specializing in engaging posts. Use for generating social media content based on market research and brand positioning.",
                prompt=(
                    "You are a Social Media Content Creator. Be concise.\n\n"
                    "Task:\n"
                    "1. Create platform-optimized posts:\n"
                    "   • Twitter/X: Punchy, hashtags\n"
                    "   • LinkedIn: Professional, value-driven\n"
                    "   • Instagram: Visual hooks, emojis\n"
                    "   • Facebook: Conversational\n\n"
                    "2. Each post:\n"
                    "   • Strong hook\n"
                    "   • Relevant hashtags\n"
                    "   • Visual suggestion\n"
                    "   • Competitor differentiation\n\n"
                    "3. Provide 3-5 variations per platform\n\n"
                    "4. Brief posting strategy (timing, frequency)\n\n"
                    "No explanations. Just deliver the posts."
                ),
                model="sonnet",
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
