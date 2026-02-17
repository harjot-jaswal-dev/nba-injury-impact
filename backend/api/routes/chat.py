"""Chat endpoint using Claude API with prediction context injection.

Routes user questions through a 5-category classification system, then
injects structured ML prediction data or player stats as context for
Claude to reference. Supports conversation history (last 3 exchanges),
keyword-proximity-based injury detection, and graceful ML fallback.

Query Classification Categories:
  SAME_TEAM_INJURY  — "What if LeBron is out?" → calls simulate_injury()
  CROSS_TEAM_IMPACT — "If Tatum is hurt, how does Luka benefit?" → player stats
  PLAYER_COMPARISON — "Compare Jokic and Embiid" → detailed stats for both
  GENERAL_NBA       — "Who are the top scorers?" → minimal context
  OFF_TOPIC         — "What's the weather?" → canned response, no API call
"""

import logging
import re
from enum import Enum
from typing import Optional

import anthropic
from fastapi import APIRouter, Depends, HTTPException

from backend.api.config import settings
from backend.api.data_access import data_store
from backend.api.database import ChatMessage, ChatUsage, User
from backend.api.dependencies import check_chat_rate_limit, get_current_user, get_db
from backend.api.player_resolver import TEAM_ALIASES, player_resolver
from backend.api.schemas import (
    ChatExamplesResponse,
    ChatRequest,
    ChatResponse,
    PlayerReference,
)

logger = logging.getLogger("chat")
router = APIRouter(prefix="/api", tags=["chat"])

# ── Anthropic Client (module-level singleton) ─────────────────────

_anthropic_client = None
if settings.ANTHROPIC_API_KEY:
    _anthropic_client = anthropic.Anthropic(
        api_key=settings.ANTHROPIC_API_KEY,
        timeout=30.0,
    )

# ── System Prompt ─────────────────────────────────────────────────
#
# This prompt defines Claude's persona and behavior for every chat
# interaction. It is injected as the `system` parameter in every
# Claude API call. Key design decisions:
#
# 1. Persona: "smart basketball analyst friend" — not formal, not
#    chatbot-generic. Uses phrases like "our model" to feel integrated.
#
# 2. Data referencing: Strict rules about when to cite numbers vs.
#    when to use general knowledge. This prevents hallucinated stats.
#
# 3. Model awareness: Claude knows the model's strengths (counting
#    stats) and weaknesses (percentage stats) so it can add appropriate
#    caveats without being asked.
#
# 4. Conciseness: 2-4 paragraphs max. Chat users want quick insight.

SYSTEM_PROMPT = """\
You are an NBA analytics expert embedded in the NBA Injury Impact Analyzer \
platform. You have access to a custom machine learning prediction model that \
analyzes how player absences ripple through team performance.

TONE: Knowledgeable, concise, and conversational — like a smart basketball \
analyst friend. Not a formal report. Use natural phrasing like "Based on our \
model's analysis..." or "The prediction model suggests..." when referencing \
model data.

WHEN YOU SEE "=== PREDICTION MODEL DATA ===" IN THE CONTEXT:
- You MUST reference specific numbers from it. Example: "Our model predicts \
Jaylen Brown would see his scoring increase from 24.2 to 26.1 points per game."
- Focus on the most impactful changes (biggest deltas in pts, ast, reb, min).
- Mention the assumed opponent/game context if provided.
- Do NOT round or modify the numbers — use them exactly as given.

WHEN YOU SEE "=== AVAILABLE PLAYER DATA ===" IN THE CONTEXT:
- Reference the season averages and recent performance provided.
- Note that you are working from general statistics, not injury-specific \
predictions: "Based on historical patterns and general basketball analysis..."

WHEN NO DATA BLOCK IS PRESENT:
- Clearly indicate you are reasoning from general basketball knowledge.
- Do NOT invent specific stat numbers. You may reference well-known player \
reputations (e.g., "Jokic is one of the best passing big men in NBA history") \
but do not fabricate exact stat lines.

DISAMBIGUATION:
- If the context mentions "Multiple players matched", ask the user to clarify \
which player they mean. List the candidates with their teams.

MODEL AWARENESS:
- The prediction model uses 3 NBA seasons of data (2022-2025).
- It is strongest for counting stats: points, assists, rebounds, minutes.
- It is weaker for percentage stats (FG%, FT%) due to high single-game variance.
- Say "based on our latest data" rather than "as of today" — you do not have \
real-time information.
- When relevant, acknowledge limitations: "Keep in mind these predictions are \
based on historical patterns, and individual game variance is high in the NBA."

RESPONSE FORMAT:
- Keep responses to 2-4 paragraphs. Users want quick insights, not essays.
- Lead with the most important finding.
- If the user asks something outside NBA/basketball, politely redirect: \
"I'm focused on NBA analytics — happy to help with player predictions, \
injury impact analysis, or matchup questions!"
"""

# ── Query Classification ──────────────────────────────────────────

# Injury-related keywords. We check proximity to player/team names
# rather than just presence in the message (see _check_injury_proximity).
INJURY_KEYWORDS = {
    "out", "injured", "hurt", "miss", "misses", "missed", "absent",
    "without", "sits", "rests", "injury", "sidelined", "questionable",
    "day-to-day", "ruled", "dnp", "inactive", "lose", "loses", "lost",
}

# Multi-word injury phrases checked separately
INJURY_PHRASES = {"ruled out", "day-to-day", "sits out"}

COMPARISON_KEYWORDS = {"vs", "versus", "better", "compare", "comparison"}

# Basketball-related keywords for distinguishing GENERAL_NBA from OFF_TOPIC
# when no specific player/team entities are resolved.
BASKETBALL_KEYWORDS = {
    "nba", "basketball", "player", "players", "team", "teams", "game",
    "games", "season", "playoff", "playoffs", "scoring", "scorer", "scorers",
    "points", "assists", "rebounds", "defense", "offense", "roster",
    "trade", "draft", "mvp", "all-star", "allstar", "championship",
    "finals", "conference", "division", "bench", "starter", "starters",
    "stats", "statistics", "minutes", "blocks", "steals", "turnover",
    "free throw", "three-pointer", "dunk", "court", "arena",
}


class QueryType(str, Enum):
    SAME_TEAM_INJURY = "same_team_injury"
    CROSS_TEAM_IMPACT = "cross_team_impact"
    PLAYER_COMPARISON = "player_comparison"
    GENERAL_NBA = "general_nba"
    OFF_TOPIC = "off_topic"


def _find_token_indices(text_lower: str, phrase: str) -> list[int]:
    """Find the token indices where a phrase starts in the tokenized text.

    Tokenizes text_lower into words, then finds where phrase's first word
    appears such that the full phrase matches consecutive tokens.
    Returns list of starting token indices.
    """
    tokens = text_lower.split()
    phrase_tokens = phrase.lower().split()
    indices = []
    for i in range(len(tokens) - len(phrase_tokens) + 1):
        if all(tokens[i + j] == phrase_tokens[j] for j in range(len(phrase_tokens))):
            indices.append(i)
    return indices


def _check_injury_proximity(
    text: str, players: list[dict], teams: list[str]
) -> dict[int, bool]:
    """Check which resolved players are within ~4 tokens of an injury keyword.

    This prevents false positives like "How did the Lakers play out west?"
    where "out" is not near any injury-relevant entity. Uses a 4-token
    window to avoid catching players in separate clauses (e.g., "If Tatum
    misses the game, how does Jaylen Brown score?" — Brown is 5+ tokens
    from "misses" and correctly excluded).

    Algorithm:
    1. Tokenize the message into lowercase words.
    2. Find token indices where each player's name appears.
    3. Find token indices where injury keywords appear.
    4. A player is "near" an injury keyword if any of their name tokens
       are within 4 positions of any injury keyword token.

    Returns:
        {player_id: True/False} — True if player is near an injury keyword.
    """
    text_lower = text.lower()
    tokens = text_lower.split()

    # Strip punctuation from tokens for matching
    clean_tokens = [re.sub(r"[^\w'-]", "", t) for t in tokens]

    # Find injury keyword positions
    injury_positions = set()
    for i, tok in enumerate(clean_tokens):
        if tok in INJURY_KEYWORDS:
            injury_positions.add(i)

    # Also check multi-word injury phrases
    for phrase in INJURY_PHRASES:
        for idx in _find_token_indices(text_lower, phrase):
            injury_positions.add(idx)

    if not injury_positions:
        return {p["player_id"]: False for p in players}

    # Find each player's name positions in the token list
    proximity_map = {}
    for p in players:
        name_lower = p["player_name"].lower()
        name_parts = name_lower.split()
        player_positions = set()

        # Check for full name match (consecutive tokens)
        for i in range(len(clean_tokens) - len(name_parts) + 1):
            if all(clean_tokens[i + j] == name_parts[j] for j in range(len(name_parts))):
                for j in range(len(name_parts)):
                    player_positions.add(i + j)

        # Also check individual name parts (first name, last name)
        # This catches "LeBron" when full name is "LeBron James"
        for part in name_parts:
            if len(part) >= 3:  # Skip very short parts to avoid false matches
                for i, tok in enumerate(clean_tokens):
                    if tok == part:
                        player_positions.add(i)

        # Check proximity: is any player token within 5 positions of any injury token?
        near_injury = False
        for p_idx in player_positions:
            for i_idx in injury_positions:
                if abs(p_idx - i_idx) <= 4:
                    near_injury = True
                    break
            if near_injury:
                break

        proximity_map[p["player_id"]] = near_injury

    # Also check team name proximity (e.g., "if the Lakers are without...")
    team_near_injury = False

    for team in teams:
        # Check 3-letter abbreviation
        for i, tok in enumerate(clean_tokens):
            if tok == team.lower():
                for i_idx in injury_positions:
                    if abs(i - i_idx) <= 4:
                        team_near_injury = True
                        break

        # Check aliases
        for alias, abbr in TEAM_ALIASES.items():
            if abbr == team:
                for idx in _find_token_indices(text_lower, alias):
                    for i_idx in injury_positions:
                        if abs(idx - i_idx) <= 5:
                            team_near_injury = True
                            break

    # If a team is near an injury keyword but no specific player is,
    # mark all players on that team as injury-proximate. This handles
    # "if the Lakers lose someone" type queries.
    if team_near_injury:
        for p in players:
            if p["team_abbr"] in teams and not proximity_map.get(p["player_id"]):
                proximity_map[p["player_id"]] = True

    return proximity_map


def classify_query(
    text: str,
    players: list[dict],
    teams: list[str],
    ambiguous: bool,
) -> tuple[QueryType, list[dict], list[dict]]:
    """Classify a chat query and separate injured vs players-of-interest.

    Classification decision tree:
    1. No basketball entities at all → OFF_TOPIC
    2. Injury keywords found:
       a. Zero players/teams near injury keywords → GENERAL_NBA
       b. All nearby players on same team → SAME_TEAM_INJURY
       c. Nearby players on multiple teams → CROSS_TEAM_IMPACT
    3. Comparison keywords + multiple players → PLAYER_COMPARISON
    4. Otherwise → GENERAL_NBA

    Returns:
        (query_type, injured_players, interest_players)
        - injured_players: players near injury keywords (to pass to simulate_injury)
        - interest_players: players NOT near injury keywords (we want their predictions)
    """
    text_lower = text.lower()
    has_players = len(players) > 0
    has_teams = len(teams) > 0

    # Tokenize early — needed for keyword checks throughout
    clean_tokens = set(re.sub(r"[^\w\s'-]", "", text_lower).split())

    # Step 1: No specific player/team entities found
    if not has_players and not has_teams:
        # Check for general basketball keywords before declaring OFF_TOPIC
        if clean_tokens & BASKETBALL_KEYWORDS:
            return (QueryType.GENERAL_NBA, [], [])
        return (QueryType.OFF_TOPIC, [], [])
    has_injury_kw = bool(clean_tokens & INJURY_KEYWORDS) or any(
        phrase in text_lower for phrase in INJURY_PHRASES
    )

    # Check for comparison keywords
    has_comparison_kw = bool(clean_tokens & COMPARISON_KEYWORDS)

    # Step 2: Injury keywords present
    # Note: if we reach here, at least one of has_players/has_teams is true
    # (the no-entity case was already handled in Step 1 above).
    if has_injury_kw:
        if has_players:
            # Check proximity — which players are near injury keywords?
            proximity = _check_injury_proximity(text, players, teams)
            injured = [p for p in players if proximity.get(p["player_id"], False)]
            interest = [p for p in players if not proximity.get(p["player_id"], False)]

            # If no player is near injury keywords → GENERAL_NBA
            # Handles "How did the Lakers play out west?"
            if not injured:
                return (QueryType.GENERAL_NBA, [], players)

            # Determine teams of injured players
            injured_teams = set(p["team_abbr"] for p in injured)

            if len(injured_teams) == 1:
                return (QueryType.SAME_TEAM_INJURY, injured, interest)
            else:
                return (QueryType.CROSS_TEAM_IMPACT, injured, interest)
        else:
            # Injury keywords + teams but no resolved players
            # e.g., "What if the Lakers are without their star?"
            # Can't run simulation without a specific player → GENERAL_NBA
            return (QueryType.GENERAL_NBA, [], [])

    # Step 3: Comparison keywords + multiple players
    if has_comparison_kw and len(players) >= 2:
        return (QueryType.PLAYER_COMPARISON, [], players)

    # Step 4: Default → GENERAL_NBA
    return (QueryType.GENERAL_NBA, [], players)


# ── Context Formatting ────────────────────────────────────────────
#
# These functions format ML prediction data and player stats into
# structured text blocks that Claude can parse and reference naturally.
# The format uses delimiters (=== ... ===) so the system prompt can
# instruct Claude on exactly how to handle each type of data.

def _format_ripple_context(
    result: dict, game_note: str = ""
) -> str:
    """Format simulate_injury() / get_ripple_effect() output for Claude.

    Matches the ACTUAL return structure from predict.py:
    {
        "team": "LAL",
        "absent_players": [{"player_id": int, "player_name": str}],
        "injury_context": {...},
        "player_predictions": [
            {
                "player_id": int,
                "player_name": str,
                "baseline": {"pts": float, "ast": float, ...},
                "with_injuries": {"pts": float, "ast": float, ...},
                "ripple_effect": {"pts": float, "ast": float, ...}
            }, ...
        ]
    }

    Processing rules:
    - Filter: only players where abs(ripple_effect) > 0.05 for pts/ast/reb/min
    - Sort: by sum of absolute ripple_effect across pts/ast/reb/min (desc)
    - Limit: top 8 most affected players
    - Round: all numbers to 1 decimal place
    """
    team = result.get("team", "")
    absent = result.get("absent_players", [])
    predictions = result.get("player_predictions", [])

    absent_names = ", ".join(
        f"{p['player_name']} ({team})" for p in absent
    )

    # Filter to players with meaningful changes
    KEY_STATS = ("pts", "ast", "reb", "minutes")
    filtered = []
    for pred in predictions:
        ripple = pred.get("ripple_effect", {})
        if any(abs(ripple.get(s, 0) or 0) > 0.05 for s in KEY_STATS):
            # Compute total impact for sorting
            total_impact = sum(abs(ripple.get(s, 0) or 0) for s in KEY_STATS)
            filtered.append((pred, total_impact))

    # Sort by total impact descending, limit to top 8
    filtered.sort(key=lambda x: x[1], reverse=True)
    filtered = filtered[:8]

    if not filtered:
        return (
            f"=== PREDICTION MODEL DATA ===\n"
            f"Scenario: {absent_names} out\n"
            f"{game_note}\n"
            f"The model predicts minimal statistical impact on remaining teammates.\n"
            f"=== END MODEL DATA ==="
        )

    # Compute team impact summary
    total_pts_added = sum(
        pred.get("ripple_effect", {}).get("pts", 0) or 0
        for pred, _ in filtered
        if (pred.get("ripple_effect", {}).get("pts", 0) or 0) > 0
    )
    # Find player with largest pts impact
    max_pts_player = max(
        filtered,
        key=lambda x: abs(x[0].get("ripple_effect", {}).get("pts", 0) or 0),
    )
    max_pts_name = max_pts_player[0]["player_name"]
    max_pts_delta = max_pts_player[0].get("ripple_effect", {}).get("pts", 0) or 0

    lines = [
        "=== PREDICTION MODEL DATA ===",
        f"Scenario: {absent_names} out",
    ]
    if game_note:
        lines.append(game_note)

    lines.extend([
        "",
        "Team Impact Summary:",
        f"- Total scoring redistribution: +{round(total_pts_added, 1)} points across {len(filtered)} teammates",
        f"- Largest individual impact: {max_pts_name} projected {'+' if max_pts_delta >= 0 else ''}{round(max_pts_delta, 1)} pts",
        "",
        "Player-by-Player Predictions:",
    ])

    def _r(val):
        """Round to 1 decimal for context display. None → 0.0."""
        return round(val, 1) if val is not None else 0.0

    def _delta(val):
        """Format a delta value with +/- prefix."""
        v = _r(val)
        return f"+{v}" if v >= 0 else str(v)

    for i, (pred, _) in enumerate(filtered, 1):
        baseline = pred.get("baseline", {})
        with_inj = pred.get("with_injuries", {})
        ripple = pred.get("ripple_effect", {})
        name = pred["player_name"]

        lines.append(f"{i}. {name}")
        lines.append(
            f"   Baseline: {_r(baseline.get('pts'))} pts / "
            f"{_r(baseline.get('ast'))} ast / "
            f"{_r(baseline.get('reb'))} reb / "
            f"{_r(baseline.get('minutes'))} min"
        )

        absent_label = " / ".join(p["player_name"] for p in absent)
        lines.append(
            f"   With {absent_label} out: {_r(with_inj.get('pts'))} pts / "
            f"{_r(with_inj.get('ast'))} ast / "
            f"{_r(with_inj.get('reb'))} reb / "
            f"{_r(with_inj.get('minutes'))} min"
        )
        lines.append(
            f"   Change: {_delta(ripple.get('pts'))} pts / "
            f"{_delta(ripple.get('ast'))} ast / "
            f"{_delta(ripple.get('reb'))} reb / "
            f"{_delta(ripple.get('minutes'))} min"
        )
        lines.append("")

    lines.append("=== END MODEL DATA ===")
    return "\n".join(lines)


def _format_player_context(player_details: list[dict]) -> str:
    """Format player detail data for Claude context injection.

    Uses output from data_store.get_player_detail() which returns:
    {
        "player_name", "team_abbr", "position",
        "season_averages": {"pts", "ast", "reb", "minutes", ...},
        "last_5_games": [{"pts", "ast", "reb", "minutes", ...}, ...]
    }
    """
    if not player_details:
        return ""

    lines = ["=== AVAILABLE PLAYER DATA ==="]

    for detail in player_details:
        name = detail.get("player_name", "Unknown")
        team = detail.get("team_abbr", "")
        pos = detail.get("position", "")
        pos_str = f", {pos}" if pos else ""

        avgs = detail.get("season_averages", {})
        lines.append(f"{name} ({team}{pos_str})")
        lines.append(
            f"Season averages: {_rv(avgs.get('pts'))} pts / "
            f"{_rv(avgs.get('ast'))} ast / "
            f"{_rv(avgs.get('reb'))} reb / "
            f"{_rv(avgs.get('minutes'))} min"
        )

        # Compute last 5 games average
        last5 = detail.get("last_5_games", [])
        if last5:
            l5_pts = _avg_stat(last5, "pts")
            l5_ast = _avg_stat(last5, "ast")
            l5_reb = _avg_stat(last5, "reb")
            l5_min = _avg_stat(last5, "minutes")
            lines.append(
                f"Last 5 games avg: {l5_pts} pts / {l5_ast} ast / "
                f"{l5_reb} reb / {l5_min} min"
            )
        lines.append("")

    lines.append("=== END PLAYER DATA ===")
    return "\n".join(lines)


def _rv(val) -> str:
    """Round a value to 1 decimal place for display."""
    if val is None:
        return "N/A"
    return str(round(float(val), 1))


def _avg_stat(games: list[dict], key: str) -> str:
    """Average a stat across a list of game dicts, rounded to 1 decimal."""
    vals = [g.get(key) for g in games if g.get(key) is not None]
    if not vals:
        return "N/A"
    return str(round(sum(float(v) for v in vals) / len(vals), 1))


def _format_season_averages_context(players: list[dict]) -> str:
    """Lightweight fallback context using just season averages.

    Used when ML prediction fails or for general queries.
    """
    parts = []
    for p in players:
        avgs = data_store.get_player_season_averages(p["player_id"])
        if avgs:
            parts.append(
                f"{p['player_name']} ({p['team_abbr']}): "
                f"{_rv(avgs.get('pts'))} pts / "
                f"{_rv(avgs.get('ast'))} ast / "
                f"{_rv(avgs.get('reb'))} reb / "
                f"{_rv(avgs.get('minutes'))} min"
            )
    if not parts:
        return ""
    return "=== AVAILABLE PLAYER DATA ===\n" + "\n".join(parts) + "\n=== END PLAYER DATA ==="


# ── Response Post-Processing ──────────────────────────────────────

# Phrases that indicate system prompt leakage
_LEAKAGE_MARKERS = [
    "system:", "instructions:", "you are an nba analytics",
    "=== prediction model data ===", "=== available player data ===",
    "=== end model data ===", "=== end player data ===",
]


def _postprocess_response(text: str, max_tokens_used: int, max_tokens_limit: int) -> str:
    """Clean up Claude's response.

    - Strip system prompt leakage
    - Handle truncated responses
    """
    # Strip leakage lines
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        line_lower = line.lower().strip()
        if any(marker in line_lower for marker in _LEAKAGE_MARKERS):
            continue
        cleaned.append(line)
    text = "\n".join(cleaned).strip()

    # Handle truncation: if near max_tokens and doesn't end with sentence punctuation
    if max_tokens_used >= max_tokens_limit - 10:
        if text and text[-1] not in ".!?\"'":
            text += "..."

    return text


# ── Game Context Resolution ───────────────────────────────────────

def _resolve_game_context(team_abbr: str) -> tuple[str, str, str]:
    """Determine opponent, home/away, and a display note for the game context.

    Never hardcodes HOME — derives from schedule/processed data.

    Returns:
        (opponent_team, home_or_away, game_note)
    """
    game_info = data_store.get_next_game_for_team(team_abbr)
    if game_info:
        opponent = game_info["opponent"]
        home_or_away = game_info["home_or_away"]
        game_date = game_info.get("game_date", "")
        side_label = "home" if home_or_away == "HOME" else "away"
        note = f"Assuming next game vs {opponent} ({side_label})"
        if game_date:
            note += f" on {game_date}"
        return (opponent, home_or_away, note)

    # Absolute fallback — should rarely happen
    return ("", "HOME", "")


# ── Main Chat Endpoint ────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    user: User = Depends(get_current_user),
    usage: ChatUsage = Depends(check_chat_rate_limit),
    db=Depends(get_db),
):
    """Process a chat message with Claude, injecting ML prediction context.

    Routing:
    1. Resolve player/team names from the message
    2. Classify query type using keyword proximity
    3. Build context (ripple predictions, player stats, or none)
    4. Load conversation history (last 3 exchanges)
    5. Call Claude API with structured messages
    6. Post-process and return response
    """
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(
            503, "Chat service not configured. Set ANTHROPIC_API_KEY to enable."
        )

    # ── Step 1: Resolve entities ──────────────────────────────────
    players, ambiguous = player_resolver.resolve_players(req.message)
    teams = player_resolver.resolve_teams(req.message)

    # ── Step 2: Classify query ────────────────────────────────────
    query_type, injured_players, interest_players = classify_query(
        req.message, players, teams, ambiguous
    )
    logger.info(
        f"Chat classification: {query_type.value} | "
        f"players={[p['player_name'] for p in players]} | "
        f"injured={[p['player_name'] for p in injured_players]} | "
        f"teams={teams} | ambiguous={ambiguous}"
    )

    # ── Step 3: OFF_TOPIC early return (no Claude API call) ───────
    if query_type == QueryType.OFF_TOPIC:
        usage.question_count += 1
        db.commit()
        remaining = settings.CHAT_DAILY_LIMIT - usage.question_count
        return ChatResponse(
            response=(
                "I'm focused on NBA analytics — happy to help with "
                "player predictions, injury impact analysis, or matchup "
                "questions!"
            ),
            context_used="none",
            players_referenced=[],
            usage={
                "used": usage.question_count,
                "limit": settings.CHAT_DAILY_LIMIT,
                "remaining": remaining,
            },
        )

    # ── Step 4: Build context based on query type ─────────────────
    context_used = "direct"
    context_text = ""

    if query_type == QueryType.SAME_TEAM_INJURY:
        context_text, context_used = _build_injury_context(
            injured_players, interest_players, players, teams, ambiguous
        )
    elif query_type in (QueryType.CROSS_TEAM_IMPACT, QueryType.PLAYER_COMPARISON):
        context_text, context_used = _build_player_detail_context(players)
    elif query_type == QueryType.GENERAL_NBA:
        if players:
            context_text = _format_season_averages_context(players)
            if context_text:
                context_used = "general_stats"

    # ── Step 5: Build Claude message with conversation history ────
    if context_text:
        user_message = (
            f"Context data:\n{context_text}\n\nUser question: {req.message}"
        )
    else:
        user_message = req.message

    # Load last 3 exchanges (6 messages) for conversation continuity
    recent_messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(6)
        .all()
    )
    recent_messages.reverse()  # Chronological order

    messages = []
    for msg in recent_messages:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": user_message})

    # Adaptive max_tokens: injury queries need more room to discuss data
    max_tokens = 1500 if query_type == QueryType.SAME_TEAM_INJURY else 1024

    # ── Step 6: Call Claude API ───────────────────────────────────
    try:
        response = _anthropic_client.messages.create(
            model=settings.CHAT_MODEL,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            messages=messages,
        )

        if not response.content:
            logger.error("Claude returned empty response")
            raise HTTPException(500, "Chat service returned an empty response")

        answer = response.content[0].text
        tokens_used = response.usage.output_tokens if response.usage else 0

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
        raise
    except Exception as e:
        logger.error(f"Unexpected chat error: {e}")
        raise HTTPException(
            500, "An unexpected error occurred with the chat service"
        )

    # ── Step 7: Post-process response ─────────────────────────────
    answer = _postprocess_response(answer, tokens_used, max_tokens)

    # ── Step 8: Save conversation history ─────────────────────────
    # Store the raw user message (without injected context) for cleaner history
    db.add(ChatMessage(user_id=user.id, role="user", content=req.message))
    db.add(ChatMessage(user_id=user.id, role="assistant", content=answer))
    db.flush()  # Flush so prune query sees the new rows (autoflush=False)

    # Prune old messages — keep at most 6 (3 exchanges)
    all_msgs = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.created_at.desc())
        .all()
    )
    if len(all_msgs) > 6:
        for old in all_msgs[6:]:
            db.delete(old)

    # ── Step 9: Increment usage and return ────────────────────────
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


# ── Context Builders (per query type) ─────────────────────────────

def _build_injury_context(
    injured_players: list[dict],
    interest_players: list[dict],
    all_players: list[dict],
    teams: list[str],
    ambiguous: bool,
) -> tuple[str, str]:
    """Build context for SAME_TEAM_INJURY queries.

    Handles:
    - Ambiguous player resolution → asks Claude to disambiguate
    - Single vs multi-player injury → simulate_injury vs get_ripple_effect
    - ML errors → graceful fallback to season averages

    Returns:
        (context_text, context_used)
    """
    # Ambiguity guard: do NOT call simulation if we're unsure which player
    # the user means. Instead, surface all candidates for Claude to ask.
    if ambiguous:
        names_with_teams = [
            f"{p['player_name']} ({p['team_abbr']})" for p in all_players
        ]
        fallback_stats = _format_season_averages_context(all_players)
        context = (
            f"Multiple players matched the query: {', '.join(names_with_teams)}.\n"
            f"Please ask the user to clarify which player they mean.\n\n"
            f"{fallback_stats}"
        )
        return (context, "general_stats")

    if not injured_players:
        # Shouldn't reach here (classify_query guards), but be safe
        return (_format_season_averages_context(all_players), "general_stats")

    # Determine team from injured players
    team_abbr = injured_players[0]["team_abbr"]

    # Resolve game context (opponent + home/away) from schedule data
    opponent, home_or_away, game_note = _resolve_game_context(team_abbr)

    # Attempt ML prediction with full error handling
    try:
        # Deferred import to avoid circular dependency
        from backend.ml.predict import simulate_injury, get_ripple_effect

        if len(injured_players) == 1:
            result = simulate_injury(
                player_id_to_injure=injured_players[0]["player_id"],
                game_context={
                    "opponent": opponent,
                    "home_or_away": home_or_away,
                },
            )
        else:
            absent_ids = [p["player_id"] for p in injured_players]
            result = get_ripple_effect(
                team=team_abbr,
                absent_player_ids=absent_ids,
                opponent_team=opponent,
                home_or_away=home_or_away,
            )

        context_text = _format_ripple_context(result, game_note)
        return (context_text, "prediction_data")

    except Exception as e:
        # Graceful fallback: inject whatever stats are available
        logger.warning(f"ML prediction failed for chat injury query: {e}")
        fallback = _format_season_averages_context(all_players)
        fallback += (
            "\n\nNote: Prediction model data unavailable for this query. "
            "Please respond using the season statistics provided."
        )
        return (fallback, "general_stats")


def _build_player_detail_context(
    players: list[dict],
) -> tuple[str, str]:
    """Build detailed player context for comparison/cross-team queries.

    Returns:
        (context_text, context_used)
    """
    details = []
    for p in players:
        detail = data_store.get_player_detail(p["player_id"])
        if detail:
            details.append(detail)

    if details:
        return (_format_player_context(details), "general_stats")

    # Fallback to season averages if get_player_detail fails
    return (_format_season_averages_context(players), "general_stats")


# ── Examples Endpoint ─────────────────────────────────────────────

# Teams to pull star players from for example queries
_EXAMPLE_TEAMS = ["LAL", "BOS", "DEN", "DAL", "GSW", "MIL"]


@router.get("/chat/examples", response_model=ChatExamplesResponse)
def chat_examples():
    """Return example chat queries with real player names from the dataset.

    Dynamically generates examples using top players from popular teams.
    Falls back to hardcoded examples if data is unavailable.
    No authentication required — this is a public endpoint.
    """
    # Gather top player from each example team
    star_map: dict[str, Optional[str]] = {}
    for team in _EXAMPLE_TEAMS:
        top = data_store.get_top_players_by_team(team, limit=1)
        star_map[team] = top[0]["player_name"] if top else None

    # Team display names for templates
    team_names = {
        "LAL": "Lakers", "BOS": "Celtics", "DEN": "Nuggets",
        "DAL": "Mavericks", "GSW": "Warriors", "MIL": "Bucks",
    }

    examples = []

    # Template 1: Same-team injury (LAL)
    if star_map.get("LAL"):
        examples.append(
            f"What happens to the {team_names['LAL']}' offense if "
            f"{star_map['LAL']} sits out?"
        )

    # Template 2: Same-team injury (BOS)
    if star_map.get("BOS"):
        examples.append(
            f"How would the {team_names['BOS']} adjust if "
            f"{star_map['BOS']} misses a game?"
        )

    # Template 3: Player comparison (DEN vs DAL)
    if star_map.get("DEN") and star_map.get("DAL"):
        examples.append(
            f"Compare {star_map['DEN']} and {star_map['DAL']}'s "
            f"numbers this season"
        )

    # Template 4: Same-team injury (GSW)
    if star_map.get("GSW"):
        examples.append(
            f"If the {team_names['GSW']} lose {star_map['GSW']}, "
            f"who picks up the scoring?"
        )

    # Template 5: General player query (MIL)
    if star_map.get("MIL"):
        examples.append(
            f"How has {star_map['MIL']} been performing lately?"
        )

    # Template 6: General NBA (always included)
    examples.append(
        "What's the biggest injury impact in the league right now?"
    )

    # Fallback if we couldn't generate enough examples
    if len(examples) < 4:
        examples = [
            "What happens to the Lakers' offense if their top scorer sits out?",
            "How would the Celtics adjust if their star misses a game?",
            "Compare the top scorers from the Nuggets and Mavericks",
            "Who are the most impactful players in the league?",
            "How does a team's bench production change when starters are out?",
            "What's the biggest injury impact in the league right now?",
        ]

    return ChatExamplesResponse(examples=examples)
