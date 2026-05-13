from .base import BaseTagger, TagResult
from .camie_v2 import CamieV2Tagger
from .dghs import WD14Tagger

__all__ = ["BaseTagger", "TagResult", "WD14Tagger", "CamieV2Tagger"]
