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
1. When the user provides their initial request, use the Task tool to delegate to the 'brief-analyzer' subagent
   - This subagent will structure the brief and fill in any missing details
   - Wait for the user to confirm the structured brief before proceeding
2. Once the brief is confirmed, use the Task tool to delegate competitor research to the 'market-researcher' subagent
3. Analyze the research findings from the subagent
4. Generate creative marketing ideas that:
   - Differentiate from competitors
   - Align with current trends
   - Are innovative and actionable
   - Include specific channels, messaging, and tactics
   - Leverage gaps found in competitor strategies
5. Present your marketing ideas to the user
6. Ask the user: "Would you like me to generate social media posts for these ideas?"
7. ONLY if the user confirms, then use the Task tool to delegate social media content creation to the 'social-media-writer' subagent
   - Pass the market research findings, user brief, and your marketing ideas to this subagent

Be creative, strategic, and provide concrete actionable ideas with clear rationale based on the research.

IMPORTANT:
- Always start by delegating to the brief-analyzer subagent for initial requests
- Only proceed with research after the brief is confirmed
- Always delegate research to the market-researcher subagent using the Task tool
- Only delegate to the social-media-writer subagent AFTER the user confirms they want social media posts
- Wait for explicit user confirmation before generating social media content
""".strip()


@agent("marketing-agent", title="Creative Marketing Agent")
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
        allowed_tools=["Task", "Read", "Write", "Bash"],
        agents={
            "brief-analyzer": AgentDefinition(
                description="Marketing brief analyzer and structurer. Use for analyzing user requests and creating structured marketing briefs with all necessary details.",
                prompt=(
                    "You are a Marketing Brief Analyst specializing in structuring marketing requests.\n\n"
                    "Your task:\n"
                    "1. Analyze the user's marketing request/brief\n"
                    "2. Extract and structure the following information:\n"
                    "   - Product/Service: What is being marketed\n"
                    "   - Target Audience: Who are the customers (demographics, psychographics, behaviors)\n"
                    "   - Marketing Goals: What the user wants to achieve (awareness, leads, sales, etc.)\n"
                    "   - Budget Constraints: If mentioned\n"
                    "   - Timeline: If mentioned\n"
                    "   - Preferred Channels: If mentioned\n"
                    "   - Unique Selling Points: Key differentiators\n"
                    "   - Competitors: Known competitors if mentioned\n"
                    "3. If critical information is missing, make reasonable assumptions based on:\n"
                    "   - Industry best practices\n"
                    "   - Common patterns for similar products/services\n"
                    "   - Typical target audiences for the category\n"
                    "4. Present a structured brief with:\n"
                    "   - Clearly labeled sections\n"
                    "   - Assumptions you made (clearly marked)\n"
                    "   - Any questions or clarifications needed\n"
                    "5. Ask the user: 'Is this structured brief accurate? Please confirm or provide corrections.'\n"
                    "6. Wait for user confirmation before completing\n\n"
                    "Be thorough, make intelligent assumptions, but always be transparent about what you've assumed vs. what was explicitly stated."
                ),
                tools=["Read", "Write"],
                model="sonnet",
            ),
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
            "social-media-writer": AgentDefinition(
                description="Social media content creator specializing in engaging posts. Use for generating social media content based on market research and brand positioning.",
                prompt=(
                    "You are a Social Media Content Creator specializing in crafting engaging, platform-optimized posts.\n\n"
                    "Your task:\n"
                    "1. Analyze the market research findings provided\n"
                    "2. Understand the product/service and target audience\n"
                    "3. Create compelling social media posts for multiple platforms:\n"
                    "   - Twitter/X (concise, punchy, with hashtags)\n"
                    "   - LinkedIn (professional, value-focused)\n"
                    "   - Instagram (visual-friendly with emoji, hooks)\n"
                    "   - Facebook (conversational, community-building)\n"
                    "4. For each post:\n"
                    "   - Write attention-grabbing hooks\n"
                    "   - Include relevant hashtags\n"
                    "   - Suggest visual/media ideas\n"
                    "   - Optimize for platform-specific best practices\n"
                    "   - Incorporate insights from the market research\n"
                    "   - Differentiate from competitors\n"
                    "5. Provide 3-5 post variations per platform\n"
                    "6. Include posting strategy recommendations (timing, frequency, engagement tactics)\n\n"
                    "Be creative, authentic, and ensure posts align with current trends while standing out from competitors."
                ),
                tools=["Read", "Write"],
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


agent.deploy(prod=False)

# agent.local()
# agent.deploy(prod=True)
