"""Methods to set up appropriate reflow config from file."""


# Until we have a proper structure this will work.
# TODO: Migrate this to the config file.
from dataclasses import dataclass
from typing import AbstractSet, Dict, Set, Optional

from sqlfluff.core.config import FluffConfig
from sqlfluff.utils.reflow.depthmap import DepthInfo

ConfigElementType = Dict[str, str]
ConfigDictType = Dict[str, ConfigElementType]


@dataclass()
class BlockConfig:
    """Holds spacing config for a block and allows easy manipulation."""

    spacing_before: str = "single"
    spacing_after: str = "single"
    spacing_within: Optional[str] = None
    line_position: Optional[str] = None

    def incorporate(
        self,
        before: Optional[str] = None,
        after: Optional[str] = None,
        within: Optional[str] = None,
        line_position: Optional[str] = None,
        config: Optional[ConfigElementType] = None,
    ):
        """Mutate the config based on additional information."""
        config = config or {}
        self.spacing_before = (
            before or config.get("spacing_before", None) or self.spacing_before
        )
        self.spacing_after = (
            after or config.get("spacing_after", None) or self.spacing_after
        )
        self.spacing_within = (
            within or config.get("spacing_within", None) or self.spacing_within
        )
        self.line_position = (
            line_position or config.get("line_position", None) or self.line_position
        )


@dataclass(frozen=True)
class ReflowConfig:
    """An interface onto the configuration of how segments should reflow.

    This acts as the primary translation engine between configuration
    held either in dicts for testing, or in the FluffConfig in live
    usage, and the configuration used during reflow operations.
    """

    _config_dict: ConfigDictType
    config_types: Set[str]

    @classmethod
    def from_dict(cls, config_dict: ConfigDictType):
        """Construct a ReflowConfig from a dict."""
        config_types = set(config_dict.keys())
        # Enrich any of the "align" keys with what they're aligning with.
        for seg_type in config_dict:
            for key in ("spacing_before", "spacing_after"):
                if config_dict[seg_type].get(key, None) == "align":
                    new_key = "align:" + seg_type
                    # Is there a limiter or boundary?
                    # NOTE: A `boundary` is only applicable if `within` is present.
                    if config_dict[seg_type].get("align_within", None):
                        new_key += ":" + config_dict[seg_type]["align_within"]
                        if config_dict[seg_type].get("align_boundary", None):
                            new_key += ":" + config_dict[seg_type]["align_boundary"]
                    config_dict[seg_type][key] = new_key
        return cls(_config_dict=config_dict, config_types=config_types)

    @classmethod
    def from_fluff_config(cls, config: FluffConfig):
        """Constructs a ReflowConfig from a FluffConfig."""
        return cls.from_dict(config.get_section(["layout", "type"]))

    def get_block_config(
        self,
        block_class_types: AbstractSet[str],
        depth_info: Optional[DepthInfo] = None,
    ) -> BlockConfig:
        """Given the class types of a ReflowBlock return spacing config.

        When fetching the config for a single class type for a simple block
        we should just get an appropriate simple config back.
        >>> cfg = ReflowConfig.from_dict({"comma": {"spacing_before": "touch"}})
        >>> cfg.get_block_config({"comma"})  # doctest: +ELLIPSIS
        BlockConfig(spacing_before='touch', spacing_after='single', ...)
        """
        # set intersection to get the class types which matter
        configured_types = self.config_types.intersection(block_class_types)
        # Start with a default config.
        block_config = BlockConfig()

        # Update with the config from any specific classes.

        # First: With the types of any parent segments where
        # we're at one end (if depth info provided).
        if depth_info:
            parent_start, parent_end = True, True
            for idx, key in enumerate(depth_info.stack_hashes[::-1]):
                # Work out if we're allowed to claim the parent.
                if depth_info.stack_positions[key].type not in ("solo", "start"):
                    parent_start = False
                if depth_info.stack_positions[key].type not in ("solo", "end"):
                    parent_end = False
                if not (parent_start or parent_end):
                    break
                # Get corresponding classes.
                parent_classes = depth_info.stack_class_types[-1 - idx]
                configured_parent_types = self.config_types.intersection(parent_classes)
                # Claim the _before_ config if at the start.
                if parent_start:
                    for seg_type in configured_parent_types:
                        block_config.incorporate(
                            before=self._config_dict[seg_type].get("spacing_before")
                        )
                # Claim the _after_ config if at the end.
                if parent_end:
                    for seg_type in configured_parent_types:
                        block_config.incorporate(
                            after=self._config_dict[seg_type].get("spacing_after")
                        )

        # Second: With the types of the raw segment itself.
        # Unless someone is doing something complicated with their configuration
        # there should only be one.
        # TODO: Extend (or at least harden) this code to handle multiple
        # configured (and matched) types much better.
        for seg_type in configured_types:
            block_config.incorporate(config=self._config_dict[seg_type])
        return block_config
