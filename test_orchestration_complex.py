from mnemosyne.core.beam import BeamMemory

# Initialize
beam = BeamMemory()

# Complex queries to test orchestration (logic gate/decomposition)
queries = [
    ("What was the outcome of our benchmark evaluation after we patched core/memory.py?", "MR"),
    ("Why did AJ decide against joining the Qwen Ambassador program?", "TR"),
    ("List all files I've modified in the last 24 hours related to Mnemosyne core components?", "IE")
]

print("--- ORCHESTRATOR TEST RUN ---")
for q, category in queries:
    print(f"\nQUERY: {q} [{category}]")
    try:
        results = beam.recall(q)
        print(f"Retrieved {len(results)} memory blocks.")
        # Print snippet of first result to verify
        if results:
            print("Snippet:", results[0].get('content', '')[:150] + "...")
    except Exception as e:
        print(f"FAILED: {e}")
