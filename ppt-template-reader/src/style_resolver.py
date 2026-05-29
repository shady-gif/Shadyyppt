from __future__ import annotations

from copy import deepcopy


THEME_COLOR_ALIASES = {
    "tx1": "dk1",
    "tx2": "dk2",
    "bg1": "lt1",
    "bg2": "lt2",
}


class StyleResolver:
    def __init__(self, theme: dict) -> None:
        self.theme = theme

    def resolve(self, data: dict) -> dict:
        resolved = deepcopy(data)
        self._resolve_masters(resolved.get("masters", []))
        self._resolve_slides(resolved.get("slides", []))
        return resolved

    def _resolve_masters(self, masters: list[dict]) -> None:
        for master in masters:
            text_styles = master.get("textStyles", {})
            for style_group in text_styles.values():
                for level in style_group.values():
                    level["resolved"] = {
                        "font": self._resolve_font(level.get("font", {})),
                        "color": self._resolve_color(level.get("color", {})),
                    }

    def _resolve_slides(self, slides: list[dict]) -> None:
        for slide in slides:
            for shape in slide.get("shapes", []):
                shape["resolved"] = {
                    "fillColor": self._resolve_color(shape.get("fill", {}).get("color", {})),
                    "lineColor": self._resolve_color(shape.get("line", {}).get("color", {})),
                }

            for text_box in slide.get("texts", []):
                for paragraph in text_box.get("paragraphs", []):
                    for run in paragraph.get("runs", []):
                        run["resolved"] = {
                            "font": self._resolve_font(run.get("font", {})),
                            "color": self._resolve_color(run.get("color", {})),
                        }

    def _resolve_font(self, font: dict) -> dict:
        latin = font.get("latin")

        if latin == "+mj-lt":
            return {
                "latin": self.theme.get("fonts", {}).get("major", {}).get("latin"),
                "source": "theme.major.latin",
            }
        if latin == "+mn-lt":
            return {
                "latin": self.theme.get("fonts", {}).get("minor", {}).get("latin"),
                "source": "theme.minor.latin",
            }
        if latin:
            return {
                "latin": latin,
                "source": "direct",
            }
        return {}

    def _resolve_color(self, color: dict) -> dict:
        if not color:
            return {}

        color_type = color.get("type")
        if color_type == "srgb":
            return {
                "hex": color.get("hex"),
                "source": "direct",
            }

        if color_type == "scheme":
            scheme_value = color.get("value")
            theme_key = THEME_COLOR_ALIASES.get(scheme_value, scheme_value)
            theme_color = self.theme.get("colors", {}).get(theme_key, {})

            return {
                "hex": theme_color.get("hex") or theme_color.get("lastColor"),
                "source": f"theme.colors.{theme_key}",
                "schemeValue": scheme_value,
            }

        return {
            "source": "unresolved",
            "raw": color,
        }
