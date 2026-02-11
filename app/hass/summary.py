"""Domain summaries and system overview."""

import logging
from typing import Dict, Any

from app.config import HA_URL, get_ha_headers
from app.hass.client import _rate_limiter, get_client
from app.hass.constants import DOMAIN_IMPORTANT_ATTRIBUTES
from app.hass.decorators import handle_api_errors
from app.hass.entities import get_entities, filter_fields
from app.hass.validation import validate_ha_identifier

logger = logging.getLogger(__name__)


@handle_api_errors
async def summarize_domain(domain: str, example_limit: int = 3) -> Dict[str, Any]:
    """
    Generate a summary of entities in a domain

    Args:
        domain: The domain to summarize (e.g., 'light', 'switch')
        example_limit: Maximum number of examples to include for each state

    Returns:
        Dictionary with summary information
    """
    validate_ha_identifier(domain, "domain")

    entities = await get_entities(domain=domain)

    # Check if we got an error response
    if isinstance(entities, dict) and "error" in entities:
        return entities  # Just pass through the error

    try:
        # Initialize summary data
        total_count = len(entities)
        state_counts = {}
        state_examples = {}
        attributes_summary = {}

        # Process entities to build the summary
        for entity in entities:
            state = entity.get("state", "unknown")

            # Count states
            if state not in state_counts:
                state_counts[state] = 0
                state_examples[state] = []
            state_counts[state] += 1

            # Add examples (up to the limit)
            if len(state_examples[state]) < example_limit:
                example = {
                    "entity_id": entity["entity_id"],
                    "friendly_name": entity.get("attributes", {}).get("friendly_name", entity["entity_id"])
                }
                state_examples[state].append(example)

            # Collect attribute keys for summary
            for attr_key in entity.get("attributes", {}):
                if attr_key not in attributes_summary:
                    attributes_summary[attr_key] = 0
                attributes_summary[attr_key] += 1

        # Create the summary
        summary = {
            "domain": domain,
            "total_count": total_count,
            "state_distribution": state_counts,
            "examples": state_examples,
            "common_attributes": sorted(
                [(k, v) for k, v in attributes_summary.items()],
                key=lambda x: x[1],
                reverse=True
            )[:10]  # Top 10 most common attributes
        }

        return summary
    except Exception as e:
        logger.error("Error generating domain summary: %s", e)
        return {"error": "Error generating domain summary"}


@handle_api_errors
async def get_system_overview() -> Dict[str, Any]:
    """
    Get a comprehensive overview of the entire Home Assistant system

    Returns:
        A dictionary containing:
        - total_entities: Total count of all entities
        - domains: Dictionary of domains with their entity counts and state distributions
        - domain_samples: Representative sample entities for each domain (2-3 per domain)
        - domain_attributes: Common attributes for each domain
        - area_distribution: Entities grouped by area (if available)
    """
    try:
        # Get ALL entities with minimal fields for efficiency
        await _rate_limiter.acquire()
        client = await get_client()
        response = await client.get(f"{HA_URL}/api/states", headers=get_ha_headers())
        response.raise_for_status()
        all_entities_raw = response.json()

        # Apply lean formatting to reduce token usage in the response
        all_entities = []
        for entity in all_entities_raw:
            domain = entity["entity_id"].split(".")[0]

            # Start with basic lean fields
            lean_fields = ["entity_id", "state", "attr.friendly_name"]

            # Add domain-specific important attributes
            if domain in DOMAIN_IMPORTANT_ATTRIBUTES:
                for attr in DOMAIN_IMPORTANT_ATTRIBUTES[domain]:
                    lean_fields.append(f"attr.{attr}")

            # Filter and add to result
            all_entities.append(filter_fields(entity, lean_fields))

        # Initialize overview structure
        overview = {
            "total_entities": len(all_entities),
            "domains": {},
            "domain_samples": {},
            "domain_attributes": {},
            "area_distribution": {}
        }

        # Group entities by domain
        domain_entities = {}
        for entity in all_entities:
            domain = entity["entity_id"].split(".")[0]
            if domain not in domain_entities:
                domain_entities[domain] = []
            domain_entities[domain].append(entity)

        # Process each domain
        for domain, entities in domain_entities.items():
            # Count entities in this domain
            count = len(entities)

            # Collect state distribution
            state_distribution = {}
            for entity in entities:
                state = entity.get("state", "unknown")
                if state not in state_distribution:
                    state_distribution[state] = 0
                state_distribution[state] += 1

            # Store domain information
            overview["domains"][domain] = {
                "count": count,
                "states": state_distribution
            }

            # Select representative samples (2-3 per domain)
            sample_limit = min(3, count)
            samples = []
            for i in range(sample_limit):
                entity = entities[i]
                samples.append({
                    "entity_id": entity["entity_id"],
                    "state": entity.get("state", "unknown"),
                    "friendly_name": entity.get("attributes", {}).get("friendly_name", entity["entity_id"])
                })
            overview["domain_samples"][domain] = samples

            # Collect common attributes for this domain
            attribute_counts = {}
            for entity in entities:
                for attr in entity.get("attributes", {}):
                    if attr not in attribute_counts:
                        attribute_counts[attr] = 0
                    attribute_counts[attr] += 1

            # Get top 5 most common attributes for this domain
            common_attributes = sorted(attribute_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            overview["domain_attributes"][domain] = [attr for attr, count in common_attributes]

            # Group by area if available
            for entity in entities:
                area_id = entity.get("attributes", {}).get("area_id", "Unknown")
                area_name = entity.get("attributes", {}).get("area_name", area_id)

                if area_name not in overview["area_distribution"]:
                    overview["area_distribution"][area_name] = {}

                if domain not in overview["area_distribution"][area_name]:
                    overview["area_distribution"][area_name][domain] = 0

                overview["area_distribution"][area_name][domain] += 1

        # Add summary information
        overview["domain_count"] = len(domain_entities)
        overview["most_common_domains"] = sorted(
            [(domain, len(entities)) for domain, entities in domain_entities.items()],
            key=lambda x: x[1],
            reverse=True
        )[:5]

        return overview
    except Exception as e:
        logger.error("Error generating system overview: %s", e)
        return {"error": "Error generating system overview"}
