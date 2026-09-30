"""Plain-language descriptions of terrain position, for map popups and reports."""

NEAR_CHANNEL_M = 1.0      # HAND below this: effectively part of the drainage corridor
RAISED_M = 5.0            # HAND at/above this: clearly above any channel
HOLLOW_M = -0.5           # at least this far below surroundings counts as a local hollow


def describe_position(hand_m: float, hollow_m: float) -> str:
    """hand_m: height above nearest drainage; hollow_m: ground height minus local median."""
    if hand_m < 0:
        raise ValueError(f"HAND cannot be negative, got {hand_m}")
    if hand_m < NEAR_CHANNEL_M:
        position = "beside a drainage channel"
    elif hand_m < RAISED_M:
        position = "slightly above the nearest channel"
    else:
        position = "well above the nearest channel"
    if hollow_m <= HOLLOW_M:
        position += ", in a local hollow"
    return position
