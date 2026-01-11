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
You are a Creative Marketing Strategist powered by Claude.

Your workflow:
1. Understand the user's marketing brief (product/service, target audience, and goals)
2. Use the Task tool to delegate competitor research to the 'market-researcher' subagent
3. Analyze the research findings from the subagent
4. Generate creative marketing ideas that:
   - Differentiate from competitors
   - Align with current trends
   - Are innovative and actionable
   - Include specific channels, messaging, and tactics
   - Leverage gaps found in competitor strategies

Be creative, strategic, and provide concrete actionable ideas with clear rationale based on the research.

IMPORTANT: Always delegate research to the market-researcher subagent using the Task tool before generating ideas.
""".strip()


@agent("marketing-agent", title="Creative Marketing Agent")
async def chat(context):
    from claude_agent_sdk import query, ClaudeAgentOptions, AgentDefinition
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
        allowed_tools=["Task", "Read", "Write", "Bash"],
        agents={
            "market-researcher": AgentDefinition(
                description="Expert market research specialist for competitor analysis. Use for researching competitors, market trends, and industry insights.",
                prompt=(
                    "You are a Market Research Specialist focused on competitor analysis.\n\n"
                    "Your task:\n"
                    "1. Research competitors on the internet using web search\n"
                    "2. Gather insights about:\n"
                    "   - Competitor marketing strategies and tactics\n"
                    "   - Current market trends in the industry\n"
                    "   - Successful campaigns and messaging\n"
                    "   - Common positioning and unique selling points\n"
                    "   - Marketing channels being used\n"
                    "3. Provide a comprehensive research report with:\n"
                    "   - Key findings about each competitor\n"
                    "   - Market trends and opportunities\n"
                    "   - Gaps in competitor strategies\n"
                    "   - Data sources and citations\n\n"
                    "Be thorough, objective, and cite your sources."
                ),
                tools=["WebSearch", "WebFetch"],
                model="sonnet",
            ),
        },
    )

    # Stream responses from Claude Agent SDK
    async for message in query(
        prompt=user_message,
        options=options
    ):
        # Extract text content from message objects
        if hasattr(message, 'text'):
            yield message.text
        elif hasattr(message, 'content'):
            # Handle different message formats
            if isinstance(message.content, str):
                yield message.content
            elif isinstance(message.content, list):
                # Extract text from content blocks
                for block in message.content:
                    if hasattr(block, 'text'):
                        yield block.text
                    elif isinstance(block, dict) and 'text' in block:
                        yield block['text']
        elif isinstance(message, str):
            yield message


agent.deploy(prod=False)

# agent.local()
# agent.deploy(prod=True)
