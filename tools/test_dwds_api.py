#!/usr/bin/env python3
"""Test the DWDS frequency API to understand its response format."""

import json
import urllib.request
import urllib.parse


def test_dwds_frequency(word: str) -> dict:
    """Call the DWDS frequency API for a given word and return the response."""
    url = f"https://www.dwds.de/api/frequency/?q={urllib.parse.quote(word)}"
    print(f"Calling: {url}")
    
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "DeutscheStudy/0.1 (frequency fetcher)"},
    )
    
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
            print(f"Status: {response.status}")
            print(f"Response: {json.dumps(data, ensure_ascii=False, indent=2)}")
            return data
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} - {e.reason}")
        print(f"Response body: {e.read().decode('utf-8', errors='replace')}")
        return {}
    except urllib.error.URLError as e:
        print(f"URL Error: {e.reason}")
        return {}


if __name__ == "__main__":
    # Test with a few words of different types
    test_words = ["Haus", "Auto", "gehen", "schön", "der"]
    
    for word in test_words:
        print(f"\n{'='*60}")
        print(f"Testing word: {word}")
        print('='*60)
        result = test_dwds_frequency(word)
        print()
