"""Dependency-free chat model used only for the labelled, repeatable replay mode."""
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ReplayModel(BaseChatModel):
    @property
    def _llm_type(self):
        return "commerce-scripted-replay"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise RuntimeError("Replay must execute through CommerceBoundary; unguarded agent detected.")
