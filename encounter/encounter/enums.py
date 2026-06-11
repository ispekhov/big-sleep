"""Shared enumerations for the Encounter domain model."""

from __future__ import annotations

import enum


class VerificationStatus(str, enum.Enum):
    """Lifecycle of a record through the verification pipeline.

    Raw user labels must never directly train the model. They move:
    submitted -> ai_validated -> human_review -> verified (-> rejected).
    Only ``verified`` records are eligible to become training data.
    """

    submitted = "submitted"
    ai_validated = "ai_validated"
    human_review = "human_review"
    verified = "verified"
    rejected = "rejected"


class ImageType(str, enum.Enum):
    """Provenance / capture context of an image."""

    official_product_image = "official_product_image"
    retailer_image = "retailer_image"
    catalogue_image = "catalogue_image"
    field_capture_verified = "field_capture_verified"
    field_capture_unverified = "field_capture_unverified"
    user_query_image = "user_query_image"


class SourceType(str, enum.Enum):
    """Where a record originated."""

    brand_site = "brand_site"
    retailer = "retailer"
    catalogue = "catalogue"
    field_capture = "field_capture"
    user_upload = "user_upload"
    manual = "manual"
