from utils.logger import setup_logger
from utils.config import Config


class BaseAgent:
    def __init__(self, config: Config, name: str):
        self.config = config
        self.name = name
        self.logger = setup_logger(name)

    def log_info(self, msg: str) -> None:
        self.logger.info(f"[{self.name}] {msg}")

    def log_error(self, msg: str) -> None:
        self.logger.error(f"[{self.name}] {msg}")

    def log_warn(self, msg: str) -> None:
        self.logger.warning(f"[{self.name}] {msg}")
