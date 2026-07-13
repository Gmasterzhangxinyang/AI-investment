from __future__ import annotations

from typing import Any, Mapping

from ..linkage import score_dynamic_linkage


class DynamicV2Overlay:
    overlay_id = "dynamic_v2"
    version = "2.0.0"
    display_name = "动态辅助"

    def evaluate(
        self,
        row: Mapping[str, Any],
        settings: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        result = score_dynamic_linkage(row, settings)
        state = result["dynamic_state"]
        if result["dynamic_data_quality"] != "OK":
            state = "数据不足"
        return {
            "auxiliary_score": result["dynamic_score"],
            "auxiliary_state": state,
            "auxiliary_note": result["dynamic_note"],
            "auxiliary_data_quality": result["dynamic_data_quality"],
            "auxiliary_components": result["dynamic_components"],
        }
