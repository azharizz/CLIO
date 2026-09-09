"""Deploy one CLIO ADK agent model to Gemini Enterprise Agent Runtime.

Run once per model in the ordered fallback chain. Each Agent Runtime resource
includes managed Sessions and Memory Bank; Cloud Run records which resource
and model served each run in ClickHouse.
"""

from __future__ import annotations

import argparse
import os

import vertexai
from vertexai import agent_engines, types


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", default="us-central1")
    parser.add_argument("--staging-bucket", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--api-base-url", required=True, help="Public Cloud Run URL exposing CLIO's read-only agent tools")
    parser.add_argument("--access-token", default=os.getenv("CLIO_GCLOUD_ACCESS_TOKEN"), help="Optional short-lived gcloud OAuth token for non-ADC deployers")
    args = parser.parse_args()

    # The ADK definition reads the model at import time. Keeping each model
    # deployment as a separate Agent Runtime resource makes failover explicit
    # and auditable from Cloud Run.
    os.environ["CLIO_AGENT_MODEL"] = args.model
    os.environ["CLIO_AGENT_API_BASE_URL"] = args.api_base_url.rstrip("/")
    from agent_runtime.clio_agent.agent import root_agent
    credentials = None
    if args.access_token:
        from google.oauth2.credentials import Credentials

        credentials = Credentials(token=args.access_token)
    # Desktop gcloud login does not necessarily create ADC.  Initializing the
    # SDK explicitly makes a short-lived `gcloud auth print-access-token`
    # deployment usable without writing credentials into the repository.
    vertexai.init(project=args.project, location=args.location, credentials=credentials)
    client = vertexai.Client(project=args.project, location=args.location, credentials=credentials)
    app = agent_engines.AdkApp(agent=root_agent)
    remote_agent = client.agent_engines.create(
        agent=app,
        config={
            "display_name": args.display_name,
            "description": "CLIO screenplay continuity and lineage agent",
            # Agent Runtime validates all packages imported by the ADK app.
            # Keep these pinned at a compatible minimum in requirements.txt
            # and explicit here because this SDK deployment path serializes
            # the in-memory app rather than reading the file automatically.
            "requirements": [
                "google-cloud-aiplatform[agent_engines,adk]>=1.112.0",
                "google-adk>=1.27.0",
                "cloudpickle>=3.0.0",
                "pydantic>=2.8.0",
            ],
            "staging_bucket": args.staging_bucket,
            "env_vars": {
                "CLIO_AGENT_VERTEX_LOCATION": "global",
                "CLIO_AGENT_API_BASE_URL": args.api_base_url.rstrip("/"),
            },
            # Memory Bank retains cross-run editorial context by user id. It
            # is intentionally scoped to durable preferences and decisions,
            # not an unbounded copy of screenplay text held in ClickHouse.
            "context_spec": {
                "memory_bank_config": {
                    "customization_configs": [
                        {
                            "scope_keys": ["user_id"],
                            "memory_topics": [
                                {
                                    "custom_memory_topic": {
                                        "label": "editorial-preferences",
                                        "description": "Human-approved continuity decisions and review preferences.",
                                    }
                                }
                            ],
                        }
                    ]
                }
            },
            # The ADK object is serialized with its module path
            # (agent_runtime.clio_agent.agent). Ship that package alongside the pickle so
            # the managed runtime can import it when it starts.
            "extra_packages": ["agent_runtime"],
            "identity_type": types.IdentityType.AGENT_IDENTITY,
        },
    )
    print(remote_agent.api_resource.name)


if __name__ == "__main__":
    main()
