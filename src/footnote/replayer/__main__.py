"""Run the replayer: python -m footnote.replayer.

Settings come from the environment (set by infra/replayer.bicep in Azure):

    EVENTHUB_NAMESPACE, EVENTHUB_NAME   the feed hub (fully qualified namespace)
    AZURE_CLIENT_ID                     the replayer's managed identity
    PORT                                default 8000
"""

from __future__ import annotations

import logging
import os

import uvicorn

from footnote.replayer.app import create_app

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("azure").setLevel(logging.WARNING)
    uvicorn.run(create_app(), host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), log_config=None)
