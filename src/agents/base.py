from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseAgent(ABC):
    """Base interface for all browser-use agents."""
    
    def __init__(self, rera_number: str):
        self.rera_number = rera_number

    @abstractmethod
    async def run(self, context_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Run the agent.
        :param context_data: Optional data from previous agents (e.g., promoter name from MahaRERA)
        :return: A dictionary representing the PartialBrief
        """
        pass
