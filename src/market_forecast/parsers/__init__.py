"""Format-specific parsers producing normalized domain records."""

from .entsoe_xml import parse_price_document

__all__ = ["parse_price_document"]
