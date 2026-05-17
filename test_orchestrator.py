
from mnemosyne.core.orchestrator import orchestrate_recall
from mnemosyne.core.beam import BeamMemory
import os

def test():
    # Setup mock beam
    beam = BeamMemory(session_id="test")
    # This should return a list without error
    try:
        results = orchestrate_recall("date deadline sprint", "TR", beam)
        print(f"SUCCESS: Retrieved {len(results)} memories")
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    test()
