import collections
import logging
from typing import Callable, DefaultDict, List

logger = logging.getLogger(__name__)

class EventBus:
    def __init__(self):
        self._subscribers: DefaultDict[str, List[Callable]] = collections.defaultdict(list)
        
    def subscribe(self, event_type: str, callback: Callable):
        self._subscribers[event_type].append(callback)
        
    def publish(self, event_type: str, **kwargs):
        logger.info(f"Event published: {event_type}")
        for callback in self._subscribers.get(event_type, []):
            try:
                callback(**kwargs)
            except Exception as e:
                logger.error(f"Error in event subscriber for {event_type}: {e}")

bus = EventBus()
