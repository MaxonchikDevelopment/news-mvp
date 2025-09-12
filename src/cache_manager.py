"""Simple caching system to reduce API calls and improve performance."""

import hashlib
import json
import os
import pickle
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional


class CacheManager:
    def __init__(
        self,
        max_size: int = 1000,
        ttl_seconds: int = 3600,
        cache_file: str = "news_cache.pkl",
    ):
        """
        Initialize cache manager with persistent storage.

        Args:
            max_size: Maximum number of items in cache
            ttl_seconds: Time to live in seconds (default: 1 hour)
            cache_file: File to persist cache between runs
        """
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._cache_file = cache_file
        self._cache: Dict[str, Dict[str, Any]] = {}

        # Load cache from file if exists
        self._load_cache()

        print(f"CacheManager initialized with max_size={max_size}, ttl={ttl_seconds}s")
        print(f"Loaded {len(self._cache)} items from persistent cache")

    def _load_cache(self):
        """Load cache from persistent storage."""
        try:
            if os.path.exists(self._cache_file):
                with open(self._cache_file, "rb") as f:
                    self._cache = pickle.load(f)
                print(f"Cache loaded from {self._cache_file}")
        except Exception as e:
            print(f"Failed to load cache from file: {e}")
            self._cache = {}

    def _save_cache(self):
        """Save cache to persistent storage."""
        try:
            with open(self._cache_file, "wb") as f:
                pickle.dump(self._cache, f)
            print(f"Cache saved to {self._cache_file}")
        except Exception as e:
            print(f"Failed to save cache to file: {e}")

    def _generate_key(self, text: str, operation: str) -> str:
        """Generate cache key from text and operation."""
        content = f"{operation}:{text}"
        return hashlib.md5(content.encode()).hexdigest()

    def _is_expired(self, item: Dict[str, Any]) -> bool:
        """Check if cache item is expired."""
        if "timestamp" not in item:
            return True
        expiry_time = item["timestamp"] + timedelta(seconds=self._ttl_seconds)
        return datetime.now() > expiry_time

    def _cleanup_expired(self):
        """Remove expired items from cache."""
        expired_keys = [
            key for key, item in self._cache.items() if self._is_expired(item)
        ]
        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            print(f"Cache cleaned up, removed {len(expired_keys)} expired items")
            self._save_cache()

    def get(self, text: str, operation: str) -> Optional[Any]:
        """Get cached result."""
        # Cleanup expired items first
        self._cleanup_expired()

        key = self._generate_key(text, operation)

        if key in self._cache:
            item = self._cache[key]
            if not self._is_expired(item):
                print(f"✅ Cache HIT for {operation}")
                return item["data"]
            else:
                # Remove expired item
                del self._cache[key]
                print(f"⏰ Cache EXPIRED for {operation}")

        print(f"❌ Cache MISS for {operation}")
        return None

    def set(self, text: str, operation: str, value: Any):
        """Cache result with persistence."""
        # Cleanup expired items
        self._cleanup_expired()

        # Manage cache size
        if len(self._cache) >= self._max_size:
            # Remove oldest items (simple FIFO)
            keys_to_remove = list(self._cache.keys())[: self._max_size // 4]
            for key in keys_to_remove:
                del self._cache[key]
            print(f"Cache cleaned up, removed {len(keys_to_remove)} old items")

        key = self._generate_key(text, operation)
        self._cache[key] = {"data": value, "timestamp": datetime.now()}

        print(f"💾 Cache SET for {operation}")
        self._save_cache()  # Save to persistent storage


# Global cache instance (singleton pattern)
_cache_instance = None


def get_cache_manager():
    """Get singleton cache manager instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = CacheManager()
    return _cache_instance


# For backward compatibility
global_cache = get_cache_manager()
