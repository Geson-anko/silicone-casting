"""RNA models registered before operators and views."""

from . import color, mixture, settings

CLASSES = (
    color.SiliconeCastingColorant,
    color.SiliconeCastingColorProfile,
    mixture.SiliconeCastingMixturePart,
    mixture.SiliconeCastingMixture,
    settings.SiliconeCastingProperties,
)
