"""
VADG follow-up module — multi-agent question flow.

Agents:
  1. Analyzer  — update_state_with_answer (orchestrator)
  2. Strategist — plan_next_question (rules-first)
  3. Writer    — build_followup_writer_prompt + LLM
  4. Critic    — QuestionCritic gate before send
"""

from followup.constants import MAX_FOLLOWUP_QUESTIONS, MIN_FOLLOWUP_QUESTIONS
from followup.orchestrator import get_next_followup_question, update_state_with_answer
from followup.selection import select_question_candidate
from followup.websocket_handler import handle_followup_websocket

__all__ = [
    "MAX_FOLLOWUP_QUESTIONS",
    "MIN_FOLLOWUP_QUESTIONS",
    "get_next_followup_question",
    "update_state_with_answer",
    "select_question_candidate",
    "handle_followup_websocket",
]
