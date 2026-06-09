"""Current time tool — returns the current date and time."""

from __future__ import annotations

from datetime import datetime

from app.core.tools.base import BaseTool, ToolResult


class CurrentTimeTool(BaseTool):
    name = "current_time"
    description = (
        "获取当前的日期和时间信息。"
        "当用户询问与时间相关的问题时使用，例如'今天几号'、'现在几点'。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "timezone": {
                "type": "string",
                "description": "时区，默认 Asia/Shanghai",
                "default": "Asia/Shanghai",
            },
        },
        "required": [],
    }

    async def execute(self, **kwargs) -> ToolResult:
        tz_name = kwargs.get("timezone", "Asia/Shanghai")
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(tz_name)
        except Exception:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo("Asia/Shanghai")

        now = datetime.now(tz)
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday = weekdays[now.weekday()]

        return ToolResult(
            success=True,
            data=f"当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')} {weekday} (时区: {tz_name})",
            display_type="text",
        )
