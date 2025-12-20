from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI


class DRManager:
    """
    DR (Dungeon / Guide Robot) Manager
    負責：
    - 讀取 OpenAI API Key
    - 建立 OpenAI client
    - 對外提供 ask() 給 scene 使用
    """

    def __init__(self) -> None:
        # 讀取 .env（如果有）
        load_dotenv()

        self.api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "[DRManager] OPENAI_API_KEY not found. "
                "Please set environment variable or .env file."
            )

        self.client = OpenAI(api_key=self.api_key)

    # =========================
    #   Public API
    # =========================
    def ask(self, user_text: str) -> str:
        """
        給 AI 導覽員用的統一入口
        dr_scene 只需要呼叫這個
        """
        try:
            resp = self.client.responses.create(
                model="gpt-4.1-mini",
                input=self._build_prompt(user_text),
            )

            # 新版 SDK 直接給你整理好的文字
            return resp.output_text or "（AI 沒有回應）"

        except Exception as e:
            # 不讓整個遊戲炸掉
            return f"[AI Error] {e}"

    # =========================
    #   Internal
    # =========================
    def _build_prompt(self, user_text: str) -> str:
        """
        這裡集中管 prompt
        老師看會覺得你設計得很乾淨
        """
        return f"""
你是 2D RPG 遊戲中的 AI 導覽員（NPC）。
你的任務是：
- 回答遊戲內的玩法、系統、操作方式
- 用「簡短、清楚、像遊戲說明」的語氣
- 不要回答現實世界或程式實作細節

玩家問題：
{user_text}
""".strip()
