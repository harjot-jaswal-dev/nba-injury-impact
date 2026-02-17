"""Chat endpoint using Claude API with prediction context injection.

Routes user questions through the ML prediction pipeline when relevant,
injecting structured data as context for Claude to reference. Handles
player name ambiguity by surfacing all matches rather than guessing.
"""

import logging

import anthropic
from fastapi import APIRouter, Depends, HTTPException

from backend.api.config import settings
from backend.api.data_access import data_store
from backend.api.database import ChatUsage, User
from backend.api.dependencies import check_chat_rate_limit, get_current_user, get_db
from backend.api.player_resolver import player_resolver
from backend.api.schemas import ChatRequest, ChatResponse, PlayerReference

logger = logging.getLogger("chat")
router = APIRouter(prefix="/api", tags=["chat"])

# Create client once at module level (reused across requests)
_anthropic_client = None
if settings.ANTHROPIC_API_KEY:
    _anthropic_client = anthropic.Anthropic(
        api_key=settings.ANTHROPIC_API_KEY,
        timeout=30.0,
    )

SYSTEM_PROMPT = (
    "You are an NBA analytics assistant for the NBA Injury Impact Analyzer. "
    "You help users understand how player injuries affect team performance "
    "and individual player stats. When prediction data is provided in the "
    "context, reference specific numbers in your response. Be concise but "
    "insightful. Focus on the most impactful findings."
)


@router.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    user: User = Depends(get_current_user),
    usage: ChatUsage = Depends(check_chat_rate_limit),
    db=Depends(get_db),
):
    """Process a chat message with Claude, injecting ML prediction context.

    Routing logic:
    - Extract player names and team names from the message
    - If all mentioned players are on the same team → query predictions, inject as context
    - If cross-team or open-ended → inject season averages as context
    - If ambiguous player names → pass all matches to Claude for disambiguation
    """
    # Graceful degradation: return 503 if API key not configured
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(
            503, "Chat service not configured. Set ANTHROPIC_API_KEY to enable."
        )

    # Resolve players and teams from the message
    players, ambiguous = player_resolver.resolve_players(req.message)
    teams = player_resolver.resolve_teams(req.message)

    context_used = "direct"
    context_text = ""

    if players:
        # Determine if same-team or cross-team
        player_teams = set()
        for p in players:
            player_teams.add(p["team_abbr"])

        # Build ambiguity note if needed
        ambiguity_note = ""
        if ambiguous:
            names_with_teams = [
                f"{p['player_name']} ({p['team_abbr']})" for p in players
            ]
            ambiguity_note = (
                f"Note: Multiple players matched the query: "
                f"{', '.join(names_with_teams)}. "
                f"Disambiguate based on context.\n\n"
            )

        if len(player_teams) == 1 and not ambiguous:
            # Same-team query: get prediction data
            try:
                from backend.ml.predict import predict_baseline  # noqa: deferred import to avoid circular

                predictions_context = []
                for p in players:
                    pred = predict_baseline(
                        player_id=p["player_id"],
                        opponent_team=teams[0] if teams else "",
                        home_or_away="HOME",
                    )
                    predictions_context.append(
                        f"{pred['player_name']}: {pred['predictions']}"
                    )
                context_text = (
                    f"{ambiguity_note}"
                    f"Based on our prediction model, here are the projected stats:\n"
                    + "\n".join(predictions_context)
                )
                context_used = "prediction_data"
            except Exception as e:
                logger.warning(f"Failed to get predictions for chat: {e}")
                context_used = "general_stats"

        if context_used != "prediction_data":
            # Cross-team or fallback: inject season averages
            stats_parts = []
            for p in players:
                avgs = data_store.get_player_season_averages(p["player_id"])
                if avgs:
                    stats_parts.append(
                        f"{p['player_name']} ({p['team_abbr']}): {avgs}"
                    )
            if stats_parts:
                context_text = (
                    f"{ambiguity_note}"
                    f"Player season averages:\n" + "\n".join(stats_parts)
                )
                context_used = "general_stats"

    # Build Claude message
    if context_text:
        user_message = (
            f"Context data:\n{context_text}\n\nUser question: {req.message}"
        )
    else:
        user_message = req.message

    # Call Claude API with error handling
    try:
        response = _anthropic_client.messages.create(
            model=settings.CHAT_MODEL,
            max_tokens=settings.CHAT_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        if not response.content:
            logger.error("Claude returned empty response")
            raise HTTPException(500, "Chat service returned an empty response")

        answer = response.content[0].text

    except anthropic.RateLimitError:
        raise HTTPException(
            503, "Chat service temporarily unavailable. Try again shortly."
        )
    except anthropic.APITimeoutError:
        raise HTTPException(504, "Chat response timed out. Please try again.")
    except anthropic.APIError as e:
        logger.error(f"Anthropic API error: {e}")
        raise HTTPException(502, "Chat service encountered an error")
    except HTTPException:
        raise  # Re-raise our own HTTP exceptions
    except Exception as e:
        logger.error(f"Unexpected chat error: {e}")
        raise HTTPException(500, "An unexpected error occurred with the chat service")

    # Increment usage counter after successful response
    usage.question_count += 1
    db.commit()

    remaining = settings.CHAT_DAILY_LIMIT - usage.question_count
    return ChatResponse(
        response=answer,
        context_used=context_used,
        players_referenced=[
            PlayerReference(
                player_id=p["player_id"],
                player_name=p["player_name"],
                team_abbr=p["team_abbr"],
            )
            for p in players
        ],
        usage={
            "used": usage.question_count,
            "limit": settings.CHAT_DAILY_LIMIT,
            "remaining": remaining,
        },
    )
