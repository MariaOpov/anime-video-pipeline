"""Application-owned humanoid rig aliases shared by planning and Blender tools.

The pipeline never lets a model-specific bone name leak into gesture or camera
code.  Importers resolve names once, then every later phase works against this
small semantic contract.
"""

from __future__ import annotations

import re


BONE_ALIASES: dict[str, tuple[str, ...]] = {
    "root": (
        "全ての親", "全親", "センター", "中心", "總親", "总亲", "root", "master",
        "center", "centre", "hips", "pelvis",
    ),
    "spine": (
        "上半身2", "上半身", "上身2", "上身", "spine", "spine_01", "upper_body",
        "upper body", "chest",
    ),
    "head": ("頭", "头", "head"),
    "arm.L": (
        "左腕", "左臂", "腕.L", "arm.L", "upper_arm.L", "upperarm_l", "left arm",
    ),
    "arm.R": (
        "右腕", "右臂", "腕.R", "arm.R", "upper_arm.R", "upperarm_r", "right arm",
    ),
    "forearm.L": ("左ひじ", "左肘", "左前臂", "ひじ.L", "forearm.L", "lower_arm.L"),
    "forearm.R": ("右ひじ", "右肘", "右前臂", "ひじ.R", "forearm.R", "lower_arm.R"),
    "hand.L": ("左手首", "左手腕", "手首.L", "hand.L", "wrist.L", "left hand"),
    "hand.R": ("右手首", "右手腕", "手首.R", "hand.R", "wrist.R", "right hand"),
    "leg.L": ("左足", "左腿", "足.L", "leg.L", "thigh.L", "upper_leg.L", "left leg"),
    "leg.R": ("右足", "右腿", "足.R", "leg.R", "thigh.R", "upper_leg.R", "right leg"),
    "knee.L": ("左ひざ", "左膝", "膝.L", "knee.L", "lower_leg.L", "shin.L"),
    "knee.R": ("右ひざ", "右膝", "膝.R", "knee.R", "lower_leg.R", "shin.R"),
    "ankle.L": ("左足首", "左脚踝", "足首.L", "ankle.L", "foot.L", "left foot"),
    "ankle.R": ("右足首", "右脚踝", "足首.R", "ankle.R", "foot.R", "right foot"),
    "eyes": ("両目", "双目", "雙目", "目", "eyes", "eye"),
    "eye.L": ("左目", "左眼", "目.L", "eye.L", "left eye"),
    "eye.R": ("右目", "右眼", "目.R", "eye.R", "right eye"),
    "leg_ik.L": ("左足ＩＫ", "左足IK", "左腿IK", "leg_ik.L", "foot_ik.L", "ik_foot.L"),
    "leg_ik.R": ("右足ＩＫ", "右足IK", "右腿IK", "leg_ik.R", "foot_ik.R", "ik_foot.R"),
    "toe_ik.L": ("左つま先ＩＫ", "左つま先IK", "左脚尖IK", "toe_ik.L", "ik_toe.L"),
    "toe_ik.R": ("右つま先ＩＫ", "右つま先IK", "右脚尖IK", "toe_ik.R", "ik_toe.R"),
}

# Phase 7 keeps this compact compatibility baseline. Phase 8 adds root, eyes,
# and IK through application-owned fallbacks when a source rig lacks them.
PHASE7_REQUIRED_BONES = ("spine", "head", "arm.L", "arm.R", "leg.L", "leg.R")
PHASE8_REQUIRED_CONTROLS = (
    "root", "spine", "head", "arm.L", "arm.R", "leg.L", "leg.R", "eyes",
    "leg_ik.L", "leg_ik.R",
)

MORPH_ALIASES: dict[str, tuple[str, ...]] = {
    "A": ("あ", "啊", "a", "mouth_a", "aa"),
    "I": ("い", "咿", "i", "mouth_i", "ih"),
    "U": ("う", "呜", "嗚", "u", "mouth_u", "ou"),
    "E": ("え", "诶", "誒", "e", "mouth_e", "eh"),
    "O": ("お", "哦", "o", "mouth_o", "oh"),
    "blink": ("まばたき", "眨眼", "blink", "eye_blink", "eyeblink"),
}

_BLENDER_SUFFIX = re.compile(r"(?:[._-]\d{3})+$")


def fold_rig_name(value: str) -> str:
    """Normalize separators and Blender duplicate suffixes for alias matching."""
    without_suffix = _BLENDER_SUFFIX.sub("", value.strip())
    return re.sub(r"[\s_.\-:]+", "", without_suffix.casefold())


def match_aliases(
    names: list[str], aliases: dict[str, tuple[str, ...]]
) -> dict[str, str | None]:
    """Resolve semantic aliases using exact, then normalized matches."""
    exact = {name.casefold(): name for name in names}
    folded = {fold_rig_name(name): name for name in names}
    result: dict[str, str | None] = {}
    for alias, candidates in aliases.items():
        match = next(
            (exact[candidate.casefold()] for candidate in candidates
             if candidate.casefold() in exact),
            None,
        )
        if match is None:
            match = next(
                (folded[fold_rig_name(candidate)] for candidate in candidates
                 if fold_rig_name(candidate) in folded),
                None,
            )
        result[alias] = match
    return result


def canonical_controls(bone_mapping: dict[str, str | None], *, runtime_probe: bool) -> dict[str, str]:
    """Return a complete Phase 8 control map with explicit safe fallbacks."""
    probe = "__RUNTIME_PROBE__"
    controls: dict[str, str] = {}
    for alias in PHASE8_REQUIRED_CONTROLS:
        mapped = bone_mapping.get(alias)
        if mapped:
            controls[alias] = mapped
        elif alias == "root":
            controls[alias] = "__PIPE_ROOT__"
        elif alias == "eyes" and (bone_mapping.get("eye.L") or bone_mapping.get("eye.R")):
            controls[alias] = "__PIPE_EYES_PAIR__"
        elif alias == "eyes":
            controls[alias] = probe if runtime_probe else "__PIPE_EYES__"
        elif alias == "leg_ik.L":
            controls[alias] = bone_mapping.get("ankle.L") or "__PIPE_FOOT_LOCK_L__"
        elif alias == "leg_ik.R":
            controls[alias] = bone_mapping.get("ankle.R") or "__PIPE_FOOT_LOCK_R__"
        elif runtime_probe:
            controls[alias] = probe
    return controls
