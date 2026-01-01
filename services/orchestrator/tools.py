"""Tool definitions for voice AI providers (OpenAI Realtime & Nova 2 Sonic).

Defines 4 separate search tools matching the n8n workflow structure:
- search_products: Legal service products with eligibility criteria
- search_needs: Client needs mapped to suitable products
- search_service_providers: Lawyer profiles and matching
- search_guardrails: Compliance rules and tone guidelines

Each tool is defined in both OpenAI and Nova formats for compatibility.
"""

# ============================================================================
# OpenAI Realtime Tool Definitions (Function Calling Format)
# ============================================================================

SEARCH_PRODUCTS_TOOL_OPENAI = {
    "type": "function",
    "name": "search_products",
    "description": ("A database of product information that must be used to form eligibility questions."),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Description of the client's situation or product type. "
                    "Examples: '30-minute consultation eligibility', "
                    "'road injury compensation Queensland', 'no-win no-fee products'"
                ),
            }
        },
        "required": ["query"],
    },
}

SEARCH_NEEDS_TOOL_OPENAI = {
    "type": "function",
    "name": "search_needs",
    "description": ("A database of client needs and associated products that may suit."),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Description of the client's legal need or situation. "
                    "Examples: 'car accident injury compensation', "
                    "'work injury claim', 'medical negligence consultation'"
                ),
            }
        },
        "required": ["query"],
    },
}

SEARCH_PROVIDERS_TOOL_OPENAI = {
    "type": "function",
    "name": "search_service_providers",
    "description": (
        "A database of possible service providers who can provision a product "
        "and be matched to a client need and product."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Search criteria for lawyers. "
                    "Examples: 'lawyer in Brisbane', 'Queensland road injury specialist', "
                    "'senior associate personal injury', 'Spanish speaking lawyer'"
                ),
            }
        },
        "required": ["query"],
    },
}

SEARCH_GUARDRAILS_TOOL_OPENAI = {
    "type": "function",
    "name": "search_guardrails",
    "description": ("A database of guardrails for tone, security, brand voice and regulatory compliance."),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": ("User input or prompt output"),
            }
        },
        "required": ["query"],
    },
}

# List of all OpenAI tools for easy import
OPENAI_TOOLS = [
    SEARCH_PRODUCTS_TOOL_OPENAI,
    SEARCH_NEEDS_TOOL_OPENAI,
    SEARCH_PROVIDERS_TOOL_OPENAI,
    SEARCH_GUARDRAILS_TOOL_OPENAI,
]


# ============================================================================
# Nova 2 Sonic Tool Definitions (Tool Use Format)
# ============================================================================

SEARCH_PRODUCTS_TOOL_NOVA = {
    "toolSpec": {
        "name": "search_products",
        "description": ("A database of product information that must be used to form eligibility questions."),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Description of the client's situation or product type. "
                            "Examples: '30-minute consultation eligibility', "
                            "'road injury compensation Queensland', 'no-win no-fee products'"
                        ),
                    }
                },
                "required": ["query"],
            }
        },
    }
}

SEARCH_NEEDS_TOOL_NOVA = {
    "toolSpec": {
        "name": "search_needs",
        "description": ("A database of client needs and associated products that may suit."),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Description of the client's legal need or situation. "
                            "Examples: 'car accident injury compensation', "
                            "'work injury claim', 'medical negligence consultation'"
                        ),
                    }
                },
                "required": ["query"],
            }
        },
    }
}

SEARCH_PROVIDERS_TOOL_NOVA = {
    "toolSpec": {
        "name": "search_service_providers",
        "description": (
            "A database of possible service providers who can provision a product "
            "and be matched to a client need and product."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Search criteria for lawyers. "
                            "Examples: 'lawyer in Brisbane', 'Queensland road injury specialist', "
                            "'senior associate personal injury', 'Spanish speaking lawyer'"
                        ),
                    }
                },
                "required": ["query"],
            }
        },
    }
}

SEARCH_GUARDRAILS_TOOL_NOVA = {
    "toolSpec": {
        "name": "search_guardrails",
        "description": (
            "A database of product information that must be used to form eligibility questions. "
            "You must always provide a description of the user's input when querying this dataset."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Topic or situation requiring guardrail guidance. "
                            "Examples: 'pricing disclosure requirements', "
                            "'tone for discussing injury details', 'compliance for union members'"
                        ),
                    }
                },
                "required": ["query"],
            }
        },
    }
}

# List of all Nova tools for easy import
NOVA_TOOLS = [
    SEARCH_PRODUCTS_TOOL_NOVA,
    SEARCH_NEEDS_TOOL_NOVA,
    SEARCH_PROVIDERS_TOOL_NOVA,
    SEARCH_GUARDRAILS_TOOL_NOVA,
]
