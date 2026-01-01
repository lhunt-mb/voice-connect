"""Transform Airtable records to Bedrock Knowledge Base documents.

Implements table-specific markdown formatting templates matching the
n8n workflow document structure for optimal vector search retrieval.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class DocumentTransformer:
    """Transform Airtable records to markdown documents for Bedrock KB.

    Each table type gets a specific document format template designed for:
    - Natural language comprehension
    - Optimal semantic search retrieval
    - Voice-friendly responses

    Supported table types:
    - Products: Legal service products with eligibility criteria
    - Needs: Client needs mapped to suitable products
    - Service Providers: Lawyer profiles with specializations
    - Guardrails: Compliance rules and tone guidelines
    """

    # Map Airtable table IDs to friendly names
    TABLE_TEMPLATES = {
        "tblHRgg8ntGwJzbg0": "products",  # Products table
        "tblUwjFzHhcCae0EE": "needs",  # Needs table
        "tbl0Qp8t6CDe7SLzd": "providers",  # Service Providers table
        "tblpiWbvxAlMJsnTf": "guardrails",  # Guardrails table
    }

    # Whitelist of non-PII fields safe for metadata (excludes phone, email, personal profiles)
    SAFE_METADATA_FIELDS = {
        "products": ["Name", "Jurisdiction", "Pricing model", "Delivery model", "Initial consult length"],
        "needs": ["Client need"],
        "providers": ["Seniority", "Location", "Jurisdiction coverage", "Languages"],
        "guardrails": ["Guardrail type", "Topic", "Relevant Jurisdiction"],
    }

    def transform_record(
        self,
        record: dict[str, Any],
        table_id: str,
    ) -> dict[str, Any]:
        """Transform Airtable record to Bedrock KB document.

        Args:
            record: Airtable record with 'id', 'fields', 'createdTime'
            table_id: Airtable table ID (e.g., 'tblHRgg8ntGwJzbg0')

        Returns:
            Document dict with:
            - id: Record ID
            - content: Markdown-formatted content
            - metadata: Record metadata with table type
            - table_type: Friendly table type name
        """
        record_id = record["id"]
        fields = record["fields"]
        table_type = self.TABLE_TEMPLATES.get(table_id, "unknown")

        # Create markdown content using table-specific template
        content = self._create_markdown(fields, table_type)

        # Filter metadata to only include whitelisted non-PII fields
        safe_fields = {k: v for k, v in fields.items() if k in self.SAFE_METADATA_FIELDS.get(table_type, [])}

        # Create metadata with table type for filtering (no PII)
        metadata = {
            "airtable_record_id": record_id,
            "airtable_table_id": table_id,
            "table_type": table_type,
            "source": "airtable",
            **safe_fields,
        }

        return {
            "id": record_id,
            "content": content,
            "metadata": metadata,
            "table_type": table_type,  # Used for S3 path organization
        }

    def _create_markdown(self, fields: dict[str, Any], table_type: str) -> str:
        """Convert fields to markdown using table-specific templates.

        Args:
            fields: Airtable record fields
            table_type: Table type (products, needs, providers, guardrails)

        Returns:
            Markdown-formatted document content
        """
        if table_type == "products":
            return self._format_product(fields)
        elif table_type == "needs":
            return self._format_need(fields)
        elif table_type == "providers":
            return self._format_provider(fields)
        elif table_type == "guardrails":
            return self._format_guardrail(fields)
        else:
            # Fallback: generic key-value format
            logger.warning("Unknown table type, using generic format", extra={"table_type": table_type})
            return "\n".join(f"**{k}**: {v}" for k, v in fields.items())

    def _format_product(self, fields: dict[str, Any]) -> str:
        """Format Products table record.

        Template focuses on:
        - Product name and duration
        - Inclusions and exclusions
        - Eligibility and ineligibility criteria
        - Pricing, delivery, jurisdiction
        """
        jurisdiction = fields.get("Jurisdiction", [])
        jurisdiction_str = jurisdiction[0] if isinstance(jurisdiction, list) and jurisdiction else str(jurisdiction)

        serviceable_by = fields.get("Serviceable by", [])
        serviceable_by_str = (
            serviceable_by[0] if isinstance(serviceable_by, list) and serviceable_by else str(serviceable_by)
        )

        return f"""This product is called {fields.get("Name", "Unknown")} and is a {fields.get("Initial consult length", "Unknown")} consultation.
This product includes: {fields.get("Product Inclusions", "Not specified")}.
This product does not include support for {fields.get("Product exclusions", "Not specified")}.
Clients will be eligible for this product if: {fields.get("Eligibility Requirements", "Not specified")}.
Clients are ineligible for this product if ANY of the following are true: {fields.get("Ineligibility", "Not specified")}.
The product can be described as: {fields.get("Description", "Not specified")}.
The product is offered via a {fields.get("Pricing model", "Not specified")} structure.
This product can be delivered via: {fields.get("Delivery model", "Not specified")}.
This product can only be offered to clients in {jurisdiction_str}.
This product can only be provisioned by {serviceable_by_str} with an experience level of {fields.get("Lawyer seniority", "Not specified")}.
"""

    def _format_need(self, fields: dict[str, Any]) -> str:
        """Format Needs table record.

        Template focuses on:
        - Client situation description
        - Associated products that may be suitable
        """
        associated = fields.get("Associated Products", [])
        associated_str = ", ".join(associated) if isinstance(associated, list) else str(associated)

        return f"""If a client's situation sounds similar to {fields.get("Client need", "Unknown")}, then they may be eligible for {associated_str}, each of which will have distinct eligibility requirements."""

    def _format_provider(self, fields: dict[str, Any]) -> str:
        """Format Service Providers table record.

        Template focuses on:
        - Lawyer name, gender, seniority, location
        - Jurisdiction coverage and practice areas
        - Languages spoken
        - Education, professional bio, personal profile
        - Contact information
        """
        needs = fields.get("Client need (from Client Need coverage)", [])
        needs_str = '", "'.join(needs) if isinstance(needs, list) else str(needs)

        jurisdiction = fields.get("Jurisdiction coverage", [])
        jurisdiction_str = ", ".join(jurisdiction) if isinstance(jurisdiction, list) else str(jurisdiction)

        return f"""{fields.get("name", "Unknown")} is a {fields.get("Gender", "Unknown")} {fields.get("Seniority", "Unknown")} located in {fields.get("Location", "Unknown")} and serves {jurisdiction_str}.
They have experience helping clients with issues like "{needs_str}".
They operate in {jurisdiction_str} and can speak {fields.get("Languages", "Not specified")}.
They have the following education and qualifications: {fields.get("Education and Qualifications", "Not specified")}.
Their professional bio is: {fields.get("Professional bio", "Not specified")}.
Outside of work: {fields.get("Personal profile", "Not specified")}.
{fields.get("name", "Unknown")}'s Unique lawyer email ID is: {fields.get("Unique lawyer email ID", "Not specified")}
For more information, please see: {fields.get("Profile link", "Not specified")}.
"""

    def _format_guardrail(self, fields: dict[str, Any]) -> str:
        """Format Guardrails table record.

        Template focuses on:
        - Guardrail type and name
        - Topic and jurisdiction
        - Rule description
        - Compliant and non-compliant examples
        """
        jurisdiction = fields.get("Relevant Jurisdiction", [])
        jurisdiction_str = jurisdiction[0] if isinstance(jurisdiction, list) and jurisdiction else str(jurisdiction)

        return f"""This guardrail is a {fields.get("Guardrail type", "Unknown")} guardrail called {fields.get("Name", "Unknown")}.
It relates to {fields.get("Topic", "Unknown")}, and applies to {jurisdiction_str}.
Description: {fields.get("Description of rule", "Not specified")}.
Examples of when this guardrail is adhered to: {fields.get("Compliant examples", "Not specified")}.
Examples of when this guardrail is not adhered to: {fields.get("Non-Compliant examples", "Not specified")}
"""
