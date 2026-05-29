from __future__ import annotations


class OutputValidator:
    def __init__(self, data: dict) -> None:
        self.data = data

    def summary(self) -> dict:
        inventory_counts = self.data.get("inventory", {}).get("counts", {})

        checks = {
            "slidesMatchInventory": len(self.data.get("slides", [])) == inventory_counts.get("slides"),
            "layoutsMatchInventory": len(self.data.get("layouts", [])) == inventory_counts.get("layouts"),
            "mastersMatchInventory": len(self.data.get("masters", [])) == inventory_counts.get("masters"),
            "assetsMatchInventory": len(self.data.get("assets", [])) == inventory_counts.get("media"),
            "themeParsed": bool(self.data.get("theme", {}).get("colors")),
        }

        return {
            "passed": all(checks.values()),
            "checks": checks,
            "counts": {
                "slides": len(self.data.get("slides", [])),
                "layouts": len(self.data.get("layouts", [])),
                "masters": len(self.data.get("masters", [])),
                "assets": len(self.data.get("assets", [])),
            },
        }
