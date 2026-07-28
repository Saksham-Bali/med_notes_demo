"""
Ontology-grounded entity resolution utilities.
"""

from .entity_grounder import EntityGrounder, GroundedEntity
from .radlex_loader import RadLexLoader, OntologyConcept
from .snomed_loader import SNOMEDLoader
from .grounding_cache import GroundingCache

__all__ = [
    "EntityGrounder",
    "GroundedEntity",
    "RadLexLoader",
    "SNOMEDLoader",
    "OntologyConcept",
    "GroundingCache",
]
