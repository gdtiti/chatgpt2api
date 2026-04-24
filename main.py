from __future__ import annotations

import uvicorn
from api import create_app
from services.config import config

app = create_app()


def run() -> None:
    uvicorn.run(app, host="0.0.0.0", port=config.listen_port, access_log=True, log_level="info")


if __name__ == "__main__":
    run()
