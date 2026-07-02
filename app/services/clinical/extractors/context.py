import re
from typing import Dict, List, Optional, Any, Union
from threading import RLock

class ContextManager:
    def __init__(self, max_turns: int = 3, timeout_seconds: float = 60.0):
        self.max_turns = max_turns
        self.timeout_seconds = timeout_seconds
        self._session_contexts: Dict[str, List[Dict[str, Any]]] = {}
        self._last_sections: Dict[str, str] = {}
        self._lock = RLock()

    def add_entity(self, session_id: str, entity_type: str, name: str, entity_id: str, timestamp: float, section: str):
        """
        Pushes a newly extracted entity to the context queue for the session.
        If a new symptom is introduced, we place it at the front of the queue.
        """
        with self._lock:
            # Check if section changed; if so, expire context first
            last_section = self._last_sections.get(session_id)
            if last_section and last_section != section:
                # Section changed! Expire memory.
                self._session_contexts[session_id] = []
            
            self._last_sections[session_id] = section
            
            context = self._session_contexts.setdefault(session_id, [])
            
            # Remove any existing instance of the same entity to avoid duplication
            context[:] = [e for e in context if not (e["entity_type"] == entity_type and e["name"].lower() == name.lower())]
            
            # Insert at the beginning (most recent)
            context.insert(0, {
                "entity_type": entity_type,
                "name": name,
                "entity_id": entity_id,
                "timestamp": timestamp,
                "turns_ago": 0,
                "section": section
            })
            
            # Keep only the last 5 active entities
            if len(context) > 5:
                context.pop()

    def update_turns(self, session_id: str, current_section: str):
        """
        Increments the turn counter for all active entities and filters out expired ones.
        """
        with self._lock:
            context = self._session_contexts.get(session_id, [])
            
            # Check for section change during update
            last_section = self._last_sections.get(session_id)
            if last_section and last_section != current_section:
                context.clear()
                self._last_sections[session_id] = current_section
                return
            
            # Increment turns
            for entity in context:
                entity["turns_ago"] += 1
                
            # Filter by max turns
            context[:] = [e for e in context if e["turns_ago"] <= self.max_turns]

    def resolve_pronoun(self, session_id: str, pronoun: str, timestamp: float) -> Optional[Dict[str, Any]]:
        """
        Resolves basic pronouns ('it', 'they', 'this', 'that') to the most recent active entity.
        Returns the entity dict if resolved and not expired, else None.
        """
        pronoun_lower = pronoun.lower().strip()
        if pronoun_lower not in ["it", "they", "this", "that"]:
            return None
            
        with self._lock:
            context = self._session_contexts.get(session_id, [])
            if not context:
                return None
                
            # Grab the most recent entity (index 0)
            candidate = context[0]
            
            # Check timeout
            if timestamp - candidate["timestamp"] > self.timeout_seconds:
                return None
                
            return candidate

    def get_modifier_target(self, session_id: str, modifier_type: str, timestamp: float) -> Optional[Union[str, Dict[str, Any]]]:
        """
        Determines which active entity in context the incoming modifier should associate with.
        
        Ambiguity detection:
        If there are multiple active entities of target type (e.g. multiple symptoms)
        in the context queue, return 'Needs clarification' to prevent incorrect guessing.
        """
        with self._lock:
            context = self._session_contexts.get(session_id, [])
            if not context:
                return None
                
            # Filter non-expired entities by timeout
            active_entities = [
                e for e in context 
                if (timestamp - e["timestamp"]) <= self.timeout_seconds
            ]
            
            if not active_entities:
                return None
                
            # Typically symptoms are the ones receiving duration/severity modifiers
            target_entities = [e for e in active_entities if e["entity_type"] == "symptom"]
            
            # If no symptoms, fall back to other entity types
            if not target_entities:
                target_entities = active_entities
                
            if len(target_entities) > 1:
                # Ambiguity detected: multiple active candidates
                return "Needs clarification"
                
            return target_entities[0]

    def clear_session(self, session_id: str) -> None:
        with self._lock:
            self._session_contexts.pop(session_id, None)
            self._last_sections.pop(session_id, None)

context_manager = ContextManager()
