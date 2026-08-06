# FRICTION: build/testing.mdx says the module's `handle` entrypoint "receives the turn
# input and returns the tool calls the agent would make" — but never shows the input
# shape or the return shape. Everything below is guessed.

def handle(turn):
    proposal = turn.get("payload", {}).get("proposal", "")
    score = 90 if "fixed-price" in proposal else 55
    return [
        {
            "tool": "emit_assessment_drafted",
            "input": {
                "score": score,
                "summary": f"Mock assessment: scored {score} based on proposal text.",
            },
        }
    ]
