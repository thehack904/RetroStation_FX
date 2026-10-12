from __future__ import annotations

# Declarative composition definitions for the built-in broadcast layouts.
# Coordinates are normalized to the rendered overlay region (0.0-1.0).
# The renderer and browser preview consume the same semantic layout data.

COMPOSITIONS = {
    "classic-cable": {
        "id": "classic-cable",
        "panels": [
            {"kind": "round_rect", "x": 0.00, "y": 0.00, "w": 1.00, "h": 1.00, "fill": "panel", "radius": 0.08},
            {"kind": "rect", "x": 0.00, "y": 0.00, "w": 0.018, "h": 1.00, "fill": "accent"},
        ],
        "regions": {
            "channel": {"x": 0.055, "y": 0.07, "w": 0.90, "h": 0.16, "align": "left", "color": "accent"},
            "now": {"x": 0.055, "y": 0.25, "w": 0.90, "h": 0.48, "align": "left", "color": "light"},
            "next": {"x": 0.055, "y": 0.76, "w": 0.90, "h": 0.17, "align": "left", "color": "muted"},
        },
    },
    "broadcast-1980s": {
        "id": "broadcast-1980s",
        "panels": [
            {"kind": "rect", "x": 0.00, "y": 0.10, "w": 0.92, "h": 0.90, "fill": "navy"},
            {"kind": "rect", "x": 0.00, "y": 0.00, "w": 0.74, "h": 0.16, "fill": "accent"},
            {"kind": "polygon", "points": [[0.74,0.00],[1.00,0.00],[0.92,0.34],[0.66,0.34]], "fill": "hot"},
        ],
        "regions": {
            "channel": {"x": 0.04, "y": 0.015, "w": 0.60, "h": 0.13, "align": "left", "color": "dark"},
            "now": {"x": 0.05, "y": 0.28, "w": 0.80, "h": 0.42, "align": "left", "color": "light"},
            "next": {"x": 0.05, "y": 0.73, "w": 0.80, "h": 0.16, "align": "left", "color": "accent"},
        },
    },
    "cable-1990s": {
        "id": "cable-1990s",
        "panels": [
            {"kind": "polygon", "points": [[0.05,0.08],[0.96,0.08],[0.88,0.70],[0.00,0.70]], "fill": "purple"},
            {"kind": "polygon", "points": [[0.00,0.00],[0.18,0.00],[0.10,1.00],[0.00,1.00]], "fill": "accent"},
            {"kind": "rect", "x": 0.12, "y": 0.72, "w": 0.78, "h": 0.23, "fill": "dark"},
        ],
        "regions": {
            "channel": {"x": 0.20, "y": 0.13, "w": 0.65, "h": 0.14, "align": "left", "color": "accent"},
            "now": {"x": 0.18, "y": 0.30, "w": 0.68, "h": 0.34, "align": "left", "color": "light"},
            "next": {"x": 0.16, "y": 0.76, "w": 0.68, "h": 0.14, "align": "left", "color": "muted"},
        },
    },
    "digital-cable-2000s": {
        "id": "digital-cable-2000s",
        "panels": [
            {"kind": "round_rect", "x": 0.00, "y": 0.08, "w": 1.00, "h": 0.88, "fill": "glass", "radius": 0.16},
            {"kind": "round_rect", "x": 0.02, "y": 0.02, "w": 0.96, "h": 0.22, "fill": "accent_soft", "radius": 0.12},
        ],
        "regions": {
            "channel": {"x": 0.07, "y": 0.055, "w": 0.86, "h": 0.15, "align": "left", "color": "light"},
            "now": {"x": 0.07, "y": 0.34, "w": 0.86, "h": 0.34, "align": "left", "color": "light"},
            "next": {"x": 0.07, "y": 0.72, "w": 0.86, "h": 0.15, "align": "left", "color": "muted"},
        },
    },
    "retro-local": {
        "id": "retro-local",
        "panels": [
            {"kind": "rect", "x": 0.00, "y": 0.06, "w": 0.24, "h": 0.88, "fill": "accent"},
            {"kind": "rect", "x": 0.24, "y": 0.06, "w": 0.76, "h": 0.88, "fill": "cream"},
            {"kind": "rect", "x": 0.235, "y": 0.06, "w": 0.012, "h": 0.88, "fill": "dark"},
        ],
        "regions": {
            "channel": {"x": 0.025, "y": 0.30, "w": 0.19, "h": 0.30, "align": "center", "color": "light"},
            "now": {"x": 0.29, "y": 0.22, "w": 0.66, "h": 0.40, "align": "left", "color": "ink"},
            "next": {"x": 0.29, "y": 0.66, "w": 0.66, "h": 0.16, "align": "left", "color": "ink_muted"},
        },
    },
    "saturday-morning": {
        "id": "saturday-morning",
        "panels": [
            {"kind": "round_rect", "x": 0.06, "y": 0.16, "w": 0.88, "h": 0.76, "fill": "purple", "radius": 0.22},
            {"kind": "round_rect", "x": 0.00, "y": 0.00, "w": 0.33, "h": 0.34, "fill": "accent", "radius": 0.28},
            {"kind": "ellipse", "x": 0.83, "y": 0.00, "w": 0.22, "h": 0.38, "fill": "hot"},
        ],
        "regions": {
            "channel": {"x": 0.055, "y": 0.09, "w": 0.22, "h": 0.15, "align": "center", "color": "dark"},
            "now": {"x": 0.12, "y": 0.38, "w": 0.72, "h": 0.30, "align": "left", "color": "light"},
            "next": {"x": 0.12, "y": 0.72, "w": 0.72, "h": 0.13, "align": "left", "color": "accent"},
        },
    },
    "movie-channel": {
        "id": "movie-channel",
        "panels": [
            {"kind": "rect", "x": 0.00, "y": 0.18, "w": 1.00, "h": 0.66, "fill": "black"},
            {"kind": "rect", "x": 0.12, "y": 0.18, "w": 0.76, "h": 0.018, "fill": "accent"},
        ],
        "regions": {
            "channel": {"x": 0.12, "y": 0.25, "w": 0.76, "h": 0.12, "align": "center", "color": "accent"},
            "now": {"x": 0.10, "y": 0.40, "w": 0.80, "h": 0.28, "align": "center", "color": "light"},
            "next": {"x": 0.16, "y": 0.71, "w": 0.68, "h": 0.11, "align": "center", "color": "muted"},
        },
    },
    "sports-info": {
        "id": "sports-info",
        "panels": [
            {"kind": "rect", "x": 0.00, "y": 0.16, "w": 0.18, "h": 0.70, "fill": "accent"},
            {"kind": "rect", "x": 0.18, "y": 0.16, "w": 0.82, "h": 0.70, "fill": "dark"},
            {"kind": "rect", "x": 0.18, "y": 0.16, "w": 0.82, "h": 0.09, "fill": "light"},
            {"kind": "rect", "x": 0.62, "y": 0.25, "w": 0.008, "h": 0.61, "fill": "accent_soft"},
        ],
        "regions": {
            "channel": {"x": 0.02, "y": 0.35, "w": 0.14, "h": 0.24, "align": "center", "color": "dark"},
            "now": {"x": 0.22, "y": 0.36, "w": 0.36, "h": 0.30, "align": "left", "color": "light"},
            "next": {"x": 0.66, "y": 0.36, "w": 0.30, "h": 0.30, "align": "left", "color": "muted"},
        },
    },
    "modern-minimal": {
        "id": "modern-minimal",
        "panels": [
            {"kind": "round_rect", "x": 0.00, "y": 0.10, "w": 1.00, "h": 0.78, "fill": "charcoal", "radius": 0.05},
            {"kind": "rect", "x": 0.06, "y": 0.82, "w": 0.42, "h": 0.018, "fill": "accent"},
        ],
        "regions": {
            "channel": {"x": 0.06, "y": 0.20, "w": 0.88, "h": 0.12, "align": "left", "color": "muted"},
            "now": {"x": 0.06, "y": 0.38, "w": 0.88, "h": 0.27, "align": "left", "color": "light"},
            "next": {"x": 0.06, "y": 0.68, "w": 0.88, "h": 0.12, "align": "left", "color": "muted"},
        },
    },
}


def get_composition(composition_id: str) -> dict:
    return COMPOSITIONS.get(composition_id) or COMPOSITIONS["classic-cable"]
