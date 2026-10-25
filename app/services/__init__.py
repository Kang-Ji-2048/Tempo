"""Compatibility service exports, loaded only when explicitly requested."""
from importlib import import_module

_EXPORTS = {
    'GeminiAnalyzer': 'gemini_analyzer', 'get_gemini_analyzer': 'gemini_analyzer',
    'set_gemini_analyzer': 'gemini_analyzer', 'SaintCadenceService': 'saint_cadence',
    'SDUIGenerator': 'sdui_generator', 'CloudStorageService': 'storage',
    'LocalStorageService': 'storage', 'StorageService': 'storage',
    'get_storage_service': 'storage', 'set_storage_service': 'storage',
    'process_session_biomechanics': 'tasks', 'VectorMatcher': 'vector_matcher',
    'compute_cosine_similarity': 'vector_matcher',
}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    return getattr(import_module(f'{__name__}.{_EXPORTS[name]}'), name)
